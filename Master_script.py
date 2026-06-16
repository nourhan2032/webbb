import os
import cv2
import json
import torch
import torchvision
import numpy as np
import pandas as pd
import psycopg2
from pathlib import Path
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.models.detection.mask_rcnn import MaskRCNNPredictor
from torchvision.transforms import functional as F
import torchvision.ops as ops
from datetime import datetime, timedelta
import sys
import io

# إصلاح مشكلة الطباعة باللغة العربية في الكونسول
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ==========================================================
# 1. DATABASE & SYSTEM SETTINGS
# ==========================================================
DB_URI = 'postgresql://postgres.fjubdwibycchdqfgjsco:kksS8JWstgxvCC.@aws-0-eu-west-1.pooler.supabase.com:5432/postgres'

VIDEO_CAM1 = r"scene22.mp4"
VIDEO_CAM2 = r"scene11.mp4"
MODEL_PATH = r"c:/Users/DELL/Desktop/mask_rcnn_custom.pth"
OUTPUT_FOLDER = r"c:/Users/DELL/Videos/New folder/Outputs"

CONF_THRESHOLD = 0.7 
NMS_IOU_THRESHOLD = 0.3
FRAMES_TO_SKIP = 17  # من أداة المعايرة

# إعدادات الحادثة
OVERLAP_AREA_THRESHOLD = 10
NEAR_DISTANCE_THRESHOLD = 5

# إعدادات التتبع
MAX_TRACK_DISTANCE = 400  # زودنا المسافة عشان التنقل بين الكاميرتين
MAX_MISSING_FRAMES = 30
SUDDEN_STOP_SPEED_THRESHOLD = 3.0    
LOW_SPEED_THRESHOLD = 0.8            

output_dir = Path(OUTPUT_FOLDER)
output_dir.mkdir(parents=True, exist_ok=True)

# ==========================================================
# 2. DATABASE HELPERS
# ==========================================================
def get_latest_logged_in_car_id():
    """بتجيب car_id لآخر عربية سجلت دخول بعد قراءة النمرة"""
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        query = """
            SELECT r.car_id 
            FROM logs l
            JOIN reservations r ON l.reserv_id = r.reserv_id
            ORDER BY l.log_in_t DESC
            LIMIT 1;
        """
        cursor.execute(query)
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return result[0]
        return None
    except Exception as e:
        print(f"[DB Error] مقدرتش أقرأ من قاعدة البيانات: {e}")
        return None

def send_accident_notification(car_id_1, car_id_2):
    """بتروح تدور على أصحاب العربيات اللي عملوا حادثة وتبعتبهم إشعار في الداتابيز"""
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()
        
        # جلب الـ user_id الخاص بكل عربية من المتورطين في الحادثة
        cursor.execute("SELECT car_id, user_id FROM cars WHERE car_id IN (%s, %s)", (car_id_1, car_id_2))
        users = cursor.fetchall()
        
        # توقيت مصر الحركي للسيستم
        now = datetime.utcnow() + timedelta(hours=3)
        
        for car_id, user_id in users:
            if user_id:
                title = "⚠️ Accident Alert!"
                message = f"Emergency: An accident involving your car (ID: {car_id}) was just detected in the smart garage."
                
                # إدخال الإشعار كـ Unread (False)
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, is_read, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                """, (user_id, title, message, False, now))
                
        conn.commit()
        conn.close()
        print(f"🚨 [Notification Sent] تم إرسال إشعار حادثة بنجاح لأصحاب السيارات: {car_id_1} و {car_id_2}")
    except Exception as e:
        print(f"[DB Error] مشكلة في إرسال إشعار الحادثة: {e}")

# ==========================================================
# 3. MATH & MASK HELPERS
# ==========================================================
def euclidean_distance(p1, p2):
    return float(np.linalg.norm(np.array(p1) - np.array(p2)))

def mask_overlap_area(mask_a, mask_b):
    overlap = np.logical_and(mask_a, mask_b)
    return int(np.sum(overlap))

def mask_area(mask):
    return int(np.sum(mask))

def mask_min_distance(mask_a, mask_b):
    if np.logical_and(mask_a, mask_b).any():
        return 0.0
    mask_a_uint8 = mask_a.astype(np.uint8)
    mask_b_uint8 = mask_b.astype(np.uint8)
    if mask_a_uint8.sum() == 0 or mask_b_uint8.sum() == 0:
        return 999999.0
    inv_b = 1 - mask_b_uint8
    dist_to_b = cv2.distanceTransform(inv_b, cv2.DIST_L2, 5)
    distances = dist_to_b[mask_a_uint8.astype(bool)]
    if len(distances) == 0:
        return 999999.0
    return float(np.min(distances))

def get_mask_centroid(mask):
    ys, xs = np.where(mask)
    if len(xs) == 0: return None
    return np.array([np.mean(xs), np.mean(ys)], dtype=np.float32)

def box_center(box):
    x1, y1, x2, y2 = box
    return np.array([(x1 + x2) / 2, (y1 + y2) / 2], dtype=np.float32)

# ==========================================================
# 4. GLOBAL TRACKER (مدمج مع الداتابيز)
# ==========================================================
class GlobalTracker:
    def __init__(self, max_distance=400, max_missing=30):
        self.tracks = {}
        self.max_distance = max_distance
        self.max_missing = max_missing
        self.fallback_id = 9000  

    def update(self, detections):
        for tid in self.tracks:
            self.tracks[tid]["updated"] = False

        for det in detections:
            center = det["center"]
            best_track_id = None
            best_distance = float("inf")

            for tid, track in self.tracks.items():
                if track["missing"] > self.max_missing:
                    continue
                dist = euclidean_distance(center, track["center"])
                if dist < best_distance:
                    best_distance = dist
                    best_track_id = tid

            if best_track_id is not None and best_distance <= self.max_distance:
                track = self.tracks[best_track_id]
                prev_center = track["center"]
                prev_speed = track.get("speed", 0.0)
                speed = euclidean_distance(center, prev_center)
                sudden_stop = (prev_speed >= SUDDEN_STOP_SPEED_THRESHOLD and speed <= LOW_SPEED_THRESHOLD)
                
                track["prev_center"] = prev_center
                track["center"] = center
                track["speed"] = speed
                track["prev_speed"] = prev_speed
                track["missing"] = 0
                track["updated"] = True
                
                det["track_id"] = best_track_id
                det["speed"] = speed
                det["prev_speed"] = prev_speed
                det["sudden_stop"] = sudden_stop
            else:
                db_car_id = get_latest_logged_in_car_id()
                
                if db_car_id is not None and db_car_id not in self.tracks:
                    tid = db_car_id
                else:
                    tid = self.fallback_id
                    self.fallback_id += 1
                    
                self.tracks[tid] = {
                    "center": center, "prev_center": center,
                    "speed": 0.0, "prev_speed": 0.0,
                    "missing": 0, "updated": True
                }
                det["track_id"] = tid
                det["speed"] = 0.0
                det["prev_speed"] = 0.0
                det["sudden_stop"] = False

        for tid in list(self.tracks.keys()):
            if not self.tracks[tid]["updated"]:
                self.tracks[tid]["missing"] += 1
            if self.tracks[tid]["missing"] > self.max_missing:
                del self.tracks[tid]

        return detections

# ==========================================================
# 5. MODEL LOADER
# ==========================================================
def get_model_instance_segmentation(num_classes):
    model = torchvision.models.detection.maskrcnn_resnet50_fpn(weights=None)
    in_features = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_features, num_classes)
    in_features_mask = model.roi_heads.mask_predictor.conv5_mask.in_channels
    hidden_layer = 256
    model.roi_heads.mask_predictor = MaskRCNNPredictor(in_features_mask, hidden_layer, num_classes)
    return model

# ==========================================================
# 6. MAIN EXECUTION
# ==========================================================
def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    print("جاري تحميل الموديل...")
    model = get_model_instance_segmentation(2)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    if device.type == 'cuda':
        model = model.half()
        torch.backends.cudnn.benchmark = True
    model.to(device).eval()

    tracker = GlobalTracker(max_distance=MAX_TRACK_DISTANCE, max_missing=MAX_MISSING_FRAMES)
    
    cap1 = cv2.VideoCapture(VIDEO_CAM1)
    cap2 = cv2.VideoCapture(VIDEO_CAM2)
    
    print(f"جاري تخطي {FRAMES_TO_SKIP} فريم من الكاميرا الأولى لضبط التزامن...")
    for _ in range(FRAMES_TO_SKIP):
        cap1.read()

    print("بدء معالجة الشاشتين المدمجتين... اضغطي 'q' للخروج")
    frame_index = 0
    alerted_pairs = set()  # مجموعة لتخزين الكوبلز اللي اتبعتلهم نوتيفيكشن منعاً للتكرار فكل فريم
    
    while cap1.isOpened() or cap2.isOpened():
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()
        
        if not ret1 and not ret2: 
            break
            
        frame_index += 1
        target_width, target_height = 640, 480

        if not ret1:
            frame1 = np.zeros((target_height, target_width, 3), dtype=np.uint8)
        else:
            frame1 = cv2.resize(frame1, (target_width, target_height))

        if not ret2:
            frame2 = np.zeros((target_height, target_width, 3), dtype=np.uint8)
        else:
            frame2 = cv2.resize(frame2, (target_width, target_height))
        
        combined_frame = np.hstack((frame2, frame1))
        
        rgb = cv2.cvtColor(combined_frame, cv2.COLOR_BGR2RGB)
        tensor = F.to_tensor(rgb).unsqueeze(0).to(device)
        if device.type == 'cuda': tensor = tensor.half()
        
        with torch.no_grad():
            preds = model(tensor)[0]
            
        keep = ops.nms(preds['boxes'], preds['scores'], NMS_IOU_THRESHOLD)
        boxes = preds['boxes'][keep].cpu().numpy()
        scores = preds['scores'][keep].cpu().numpy()
        masks = preds['masks'][keep].cpu().numpy()
        
        detections = []
        for i in range(len(boxes)):
            if scores[i] > CONF_THRESHOLD:
                box = boxes[i].astype(int)
                mask_prob = masks[i, 0]
                binary_mask = mask_prob > 0.5
                
                center = get_mask_centroid(binary_mask)
                if center is None: center = box_center(box)
                    
                detections.append({
                    "box": box, "mask": binary_mask, "score": scores[i],
                    "center": center, "area": mask_area(binary_mask)
                })

        detections = tracker.update(detections)

        for det in detections:
            box = det["box"]
            mask = det["mask"]
            track_id = det["track_id"]
            
            color_mask = np.zeros_like(combined_frame, dtype=np.uint8)
            color_mask[mask] = [0, 255, 0]
            combined_frame = cv2.addWeighted(combined_frame, 1.0, color_mask, 0.4, 0)
            cv2.rectangle(combined_frame, (box[0], box[1]), (box[2], box[3]), (255, 255, 0), 2)
            
            label = f"CAR ID: {track_id}"
            cv2.putText(combined_frame, label, (box[0], box[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

        # لوجيك الحادثة
        for i in range(len(detections)):
            for j in range(i + 1, len(detections)):
                a, b = detections[i], detections[j]
                
                overlap_area = mask_overlap_area(a["mask"], b["mask"])
                distance = mask_min_distance(a["mask"], b["mask"])

                if overlap_area > OVERLAP_AREA_THRESHOLD or distance < NEAR_DISTANCE_THRESHOLD:
                    ca, cb = a["center"].astype(int), b["center"].astype(int)
                    cv2.line(combined_frame, tuple(ca), tuple(cb), (0, 0, 255), 3)
                    
                    mid = ((ca + cb) // 2).astype(int)
                    alert = "ACCIDENT DETECTED!"
                    (tw, th), _ = cv2.getTextSize(alert, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
                    cv2.rectangle(combined_frame, (mid[0]-5, mid[1]-th-5), (mid[0]+tw+5, mid[1]+5), (0, 0, 0), -1)
                    cv2.putText(combined_frame, alert, (mid[0], mid[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    
                    # سحب الـ IDs الحقيقية لإرسال الإشعار لمرة واحدة فقط
                    car_a_id = a["track_id"]
                    car_b_id = b["track_id"]
                    
                    if car_a_id != 9000 and car_b_id != 9000:
                        pair = tuple(sorted([car_a_id, car_b_id]))
                        if pair not in alerted_pairs:
                            send_accident_notification(car_a_id, car_b_id)
                            alerted_pairs.add(pair)

        cv2.line(combined_frame, (640, 0), (640, 480), (255, 255, 255), 1)
        cv2.putText(combined_frame, "CAM 2 (Left)", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(combined_frame, "CAM 1 (Right)", (660, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        cv2.imshow("Smart Parking - Master Node", combined_frame)
        
        if cv2.waitKey(30) & 0xFF == ord('q'): 
            break
            
    cap1.release()
    cap2.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()