import requests  # 💡 Added for ESP32 Gate Communication
import re
import time  # 💡 Added for Cooldown Timer
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from models import db, Car, Garage, Reservation, Slot
from DynamicPricing import get_all_dynamic_prices

reservation_bp = Blueprint('reservation_bp', __name__)

# 💡 قاموس لتخزين وقت آخر فتح للبوابة لكل لوحة لمنع التكرار
recent_gate_opens = {}
COOLDOWN_PERIOD = 10  # مدة الانتظار بالثواني
# ==========================================
# 1. API to fetch user cars for reservation
# ==========================================
@reservation_bp.route('/api/get_user_cars', methods=['GET'])
@login_required
def get_user_cars():
    try:
        user_cars = Car.query.filter_by(user_id=current_user.user_id).all()
        cars_list = [{"id": car.car_id, "plate_no": car.plate_no} for car in user_cars]
        
        return jsonify({"status": "success", "cars": cars_list})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ==========================================
# 2. API to fetch dynamic garage prices by ID
# ==========================================
@reservation_bp.route('/api/get_garage_prices', methods=['GET'])
def get_garage_prices():
    try:
        garage_id = request.args.get('garage_id')
        if not garage_id:
            return jsonify({"status": "error", "message": "Garage ID required"})

        garage = Garage.query.filter_by(garage_id=int(garage_id)).first()
        if not garage:
            return jsonify({"status": "error", "message": f"Garage with ID {garage_id} not found"})
            
        is_occupied = False 
        calculated_prices = get_all_dynamic_prices(garage.fixed_price, occupancy_high=is_occupied)

        return jsonify({"status": "success", "prices": calculated_prices})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ==========================================
# 3. API to create a new reservation & secure slot
# ==========================================
@reservation_bp.route('/api/create_reservation', methods=['POST'])
@login_required
def create_reservation():
    try:
        data = request.get_json()
        
        # 1. Receive incoming data
        car_id = data.get('car_id')
        spot_type = data.get('spot_type')
        hour_price = data.get('hour_price')
        duration = data.get('duration', 1)
        garage_id = data.get('garage_id')  
        slot_name = data.get('slot_name')  

        if not all([car_id, spot_type, hour_price, garage_id, slot_name]):
            return jsonify({"status": "error", "message": "Missing required data"})

        # Prevent double booking for the same car
        existing_booking = Reservation.query.filter(
            Reservation.car_id == int(car_id),
            Reservation.reserv_status.in_(['reserved', 'active', 'occupied'])
        ).first()
        
        if existing_booking:
            return jsonify({
                "status": "error", 
                "message": "Sorry, this car already has an active reservation! Please use another car or end the current reservation."
            })

        # 2. Search for the requested Slot
        slot = Slot.query.filter_by(garage_id=int(garage_id), slot_name=slot_name).first()
        
        if not slot:
            return jsonify({"status": "error", "message": "The selected slot does not exist in this garage."})
            
        # =================================================================
        # 💡 NEW MODIFICATION: Real-time slot availability check
        # =================================================================
        # Search if this slot currently has any "active" reservation
        active_slot_booking = Reservation.query.filter(
            Reservation.slot_id == slot.slot_id,
            Reservation.reserv_status.in_(['reserved', 'active', 'occupied'])
        ).first()

        # If it has an active reservation, reject. If not, proceed.
        if active_slot_booking:
            return jsonify({"status": "error", "message": "This slot was just taken! Please choose another one."})
        # =================================================================

        # 3. Create the reservation
        new_reservation = Reservation(
            car_id=int(car_id),
            slot_id=slot.slot_id,        
            Spot_Type=spot_type,
            Reserved_hour_price=float(hour_price),
            Duration_T=int(duration),     
            reserv_status='reserved' 
        )
        
        # 4. Formally close the slot in the slots table to update the map UI
        slot.status = 'not available'
        
        db.session.add(new_reservation)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Reservation saved and slot secured!",
            "reserv_id": new_reservation.reserv_id 
        })
        
    except Exception as e:
        db.session.rollback() 
        return jsonify({"status": "error", "message": str(e)})


# ==========================================
# 4. Gate API (Step 1: Authorization & Open Command)
# ==========================================
@reservation_bp.route('/api/check_plate', methods=['POST'])
def check_plate():
    try:
        data = request.get_json()
        raw_plate = data.get('plate_number') 

        print(f"\n🚗 [Backend Alert] Received plate: {raw_plate}")

        if not raw_plate:
            return jsonify({"status": "error", "message": "No plate number provided"})

        # Plate Format Normalization
        numbers = re.findall(r'\d', raw_plate)
        letters = re.findall(r'[ء-ي]', raw_plate)
        
        arabic_numbers_map = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')
        arabic_numbers = [n.translate(arabic_numbers_map) for n in numbers]
        
        reversed_letters = list(reversed(letters))
        reversed_arabic_numbers = list(reversed(arabic_numbers))
        
        possible_formats = [
            raw_plate,                                             
            " ".join(reversed_letters + reversed_arabic_numbers),  
            " ".join(arabic_numbers + reversed_letters),           
            " ".join(reversed_letters + arabic_numbers),           
            "".join(reversed_letters + reversed_arabic_numbers)    
        ]
        
        car = Car.query.filter(Car.plate_no.in_(possible_formats)).first()
        if not car:
            return jsonify({"status": "denied", "message": "Car is not registered in the system."})

        # Check for active/reserved reservation
        active_reservation = Reservation.query.filter(
            Reservation.car_id == car.car_id,
            Reservation.reserv_status.in_(['reserved', 'active'])
        ).first()

        if active_reservation:
            slot = Slot.query.get(active_reservation.slot_id)
            
            # Cooldown logic to protect ESP32 motor
            current_time = time.time()
            last_open_time = recent_gate_opens.get(car.plate_no, 0)
            
            if current_time - last_open_time < COOLDOWN_PERIOD:
                print(f"⏳ [COOLDOWN] Ignored request for {raw_plate}. Gate recently opened.")
                return jsonify({"status": "ignored", "message": "Gate is already open."}), 200

            recent_gate_opens[car.plate_no] = current_time
            
            # 💡 100% Clean: We DO NOT change the database status here to avoid side effects.
            # We explicitly pass the reserv_id to the ESP32 in the query string!
            ESP32_IP = "10.19.162.169" # ⚠️ Make sure this matches your exact ESP32 IP address
            try:
                requests.get(f"http://{ESP32_IP}/open?reserv_id={active_reservation.reserv_id}", timeout=3)
                print(f"🚪 [COMMAND SENT] /open?reserv_id={active_reservation.reserv_id} sent to ESP32.")
            except Exception as e:
                print(f"⚠️ [ESP32 ERROR] Failed to connect to ESP32: {e}")

            return jsonify({
                "status": "granted",
                "message": "Access Granted. Gate Opening...",
                "slot_name": slot.slot_name if slot else "Unknown"
            })
        else:
            return jsonify({"status": "denied", "message": "Car is registered but has no active reservation."})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


# ==========================================
# 4.1 Gate API (Step 2: Confirm Physical Entry & Create Log)
# ==========================================
@reservation_bp.route('/api/gate/confirm_entry', methods=['POST'])
def confirm_entry():
    try:
        from models import get_cairo_time, ParkingLog, Slot
        
        data = request.get_json()
        reserv_id = data.get('reserv_id') # سحب رقم الحجز المرسل من الـ ESP32
        
        print(f"\n✅ [GATE CONFIRMATION] ESP32 confirmed physical entry for Reservation ID: {reserv_id}")

        if not reserv_id:
            return jsonify({"status": "error", "message": "Missing reserv_id payload."}), 400

        reservation = Reservation.query.get(int(reserv_id))
        
        if reservation and reservation.reserv_status in ['reserved', 'active']:
            # تحويل الحالة لـ occupied فقط عند تأكيد العبور الفعلي
            reservation.reserv_status = 'occupied'
            
            if reservation.slot_id:
                slot = Slot.query.get(reservation.slot_id)
                if slot:
                    slot.status = 'occupied'
            
            # 🎯 هنا بالضبط يتم إنشاء الـ Row الجديد في جدول الـ logs
            new_log = ParkingLog(
                reserv_id=reservation.reserv_id,
                log_in_t=get_cairo_time()
            )
            db.session.add(new_log)
            db.session.commit()
            
            print(f"📝 [DATABASE LOG INSERTED] Row created for Reservation ID: {reserv_id}")
            return jsonify({"status": "success", "message": "Entry confirmed and log row created successfully."}), 200
        else:
            return jsonify({"status": "error", "message": "Reservation not found or already occupied."}), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# 5. API لجلب حالة السلوتس الحية من الداتا بيز للخريطة
# ==========================================
@reservation_bp.route('/api/get_garage_slots', methods=['GET'])
@login_required
def get_garage_slots():
    try:
        garage_id = request.args.get('garage_id')
        if not garage_id:
            return jsonify({"status": "error", "message": "Garage ID required"})

        # جلب كل السلوتس الخاصة بالجراج ده
        slots = Slot.query.filter_by(garage_id=int(garage_id)).all()
        
        # تجهيز الداتا كقاموس (Dictionary) يربط اسم السلوت بحالته
        # مثال: {"V-01": "available", "V-02": "not available"}
        slots_data = {slot.slot_name: slot.status for slot in slots}

        return jsonify({"status": "success", "slots": slots_data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})