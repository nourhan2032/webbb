# taskkill /F /IM python.exe

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
# تأكدي إنك عاملة Import لكل الجداول من models
from models import db, User, Car, Reservation, Garage, Sensor, Slot, ParkingLog, Transaction, Notification
from Reservation import reservation_bp
from datetime import datetime, timedelta
from sqlalchemy import event
import json
from current_pricing import calculate_live_parking
import threading
from emergency_system import run_emergency_loop


app = Flask(__name__, template_folder='.')

app.config['SECRET_KEY'] = 'smart-park-ai-super-secret-2026'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,  # بيعمل اختبار للاتصال قبل ما يبعت الاستعلام
    'pool_recycle': 300,    # بيجدد الاتصال بالداتا بيز كل 5 دقايق أوتوماتيك
}
# تم تحديث رابط قاعدة البيانات لـ Supabase باستخدام بورت 6543 (Connection Pooler)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.fjubdwibycchdqfgjsco:kksS8JWstgxvCC.@aws-0-eu-west-1.pooler.supabase.com:5432/postgres'

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'index'
app.register_blueprint(reservation_bp)
# ----------------- منع الكاش -----------------
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------- دالة جلب توقيت مصر -----------------
def get_cairo_time():
    return datetime.utcnow() + timedelta(hours=3)

# ----------------- دالة تنظيف الحجوزات المنتهية -----------------
def release_expired_reservations():
    try:
        now = get_cairo_time()
        # هنجيب كل الحجوزات الـ active
        active_reservations = Reservation.query.filter_by(reserv_status='active').all()

        for reservation in active_reservations:
            # بما إن end_t اتشال، هنحسب وقت الانتهاء من (وقت الإنشاء + عدد الساعات)
            duration_hours = reservation.Duration_T if reservation.Duration_T else 1
            if reservation.created_at:
                # إزالة الـ timezone info للمقارنة بشكل سليم
                created_time = reservation.created_at.replace(tzinfo=None)
                end_time = created_time + timedelta(hours=duration_hours)
                
                if end_time < now:
                    reservation.reserv_status = 'cancelled'
                    if reservation.slot_id:
                        slot = Slot.query.get(reservation.slot_id)
                        if slot:
                            slot.status = 'available'
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error in releasing expired reservations: {str(e)}")
        
        
        
# 💡 دالة مراقبة السينسور وتحديث الحسابات تلقائياً عند الخروج
def sync_external_sensor_checkout(user_id):
    try:
        # البحث عن أي حجز بحالة 'occupied' للمستخدم الحالي
        active_occupied = Reservation.query.join(Car).filter(
            Car.user_id == user_id,
            Reservation.reserv_status == 'occupied'
        ).all()

        for reservation in active_occupied:
            # جلب سجل الدخول والخروج من جدول الـ logs
            parking_log = ParkingLog.query.filter_by(reserv_id=reservation.reserv_id).first()
            
            # 🎯 الشرط السحري: لو السينسور ملأ خانة الخروج ومبقتش NULL
            if parking_log and parking_log.log_out_t:
                
                # 1. حساب المدة والسعر النهائي بناءً على وقت السينسور
                time_str, final_price = calculate_live_parking(
                    parking_log.log_in_t, 
                    parking_log.log_out_t, 
                    reservation.Reserved_hour_price
                )
                
                # 2. خصم المبلغ من رصيد المستخدم
                current_user.balance = float(current_user.balance or 0.0) - final_price
                
                # 3. تسجيل المعاملة المالية في جدول Transactions لتوثيق الدفع
                new_tx = Transaction(
                    reserv_id=reservation.reserv_id,
                    fees=final_price,
                    status='deducted',
                    user_id=user_id,
                    amount=final_price,
                    trans_type='Parking Fee'
                )
                db.session.add(new_tx)
                
                # 4. تغيير حالة الحجز إلى completed (Checked Out)
                # تلقائياً الـ Event Listener اللي في آخر الكود عندك هيفضي السلوت ويخليه available
                reservation.reserv_status = 'completed'
                
                db.session.commit()
                print(f"🔔 [Sensor Sync] Car exited! Auto-debited {final_price} EGP and freed slot.")
                
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Error in Sensor Sync: {str(e)}")

# ----------------- الصفحات الأساسية -----------------
@app.route('/')
@app.route('/index.html')
def index():
    return render_template('index.html')

@app.route('/signup')
@app.route('/signup.html')
def signup():
    return render_template('signup.html')

@app.route('/<path:filename>')
def serve_files(filename):
    return send_from_directory('.', filename)

# ----------------- كود تسجيل الدخول -----------------
@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    next_page = request.form.get('next_page', '/')

    user = User.query.filter_by(email=email).first()

    if not user:
        flash("This Email does not exist.", "login_error")
        return redirect(url_for('index'))

    if check_password_hash(user.password, password):
        login_user(user)
        return redirect(next_page)
    else:
        flash("Incorrect password.", "login_error")
        return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user() 
    return redirect(url_for('index'))   

@app.route('/check_login', methods=['POST'])
def check_login():
    email = request.form.get('email')
    password = request.form.get('password')
    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({"status": "error", "message": "This Email does not exist."})
    if check_password_hash(user.password, password):
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "error", "message": "Incorrect password."})

# ----------------- كود إنشاء حساب -----------------
@app.route('/register', methods=['POST'])
def register():
    try:
        name = request.form.get('full_name')
        email = request.form.get('email')
        phone = request.form.get('phone') 
        plate = request.form.get('plate_number')
        password = request.form.get('password')

        if not email or not password or not plate or not name or not phone:
            flash("Please fill all fields.", "danger")
            return redirect(url_for('signup'))
            
        plate = plate.strip().upper()
        phone = phone.strip()

        if User.query.filter_by(email=email).first():
            flash("This email is already registered. Please sign in.", "danger")
            return redirect(url_for('signup'))
            
        if User.query.filter_by(phone=phone).first():
            flash("This phone number is already registered.", "danger")
            return redirect(url_for('signup'))
            
        if Car.query.filter_by(plate_no=plate).first():
            flash("This license plate is already registered to another account.", "danger")
            return redirect(url_for('signup'))

        new_user = User(
            name=name,
            email=email,
            phone=phone,
            password=generate_password_hash(password, method='pbkdf2:sha256'),
            balance=0.0
        )
        db.session.add(new_user)
        db.session.flush() 

        # تم إزالة accident وتمرير tire_condition كـ JSON (Dictionary)
        new_car = Car(
            user_id=new_user.user_id,
            plate_no=plate,
            tire_condition={"status": "Good"} 
        )
        db.session.add(new_car)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('index'))
    
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {str(e)}", "danger")
        return redirect(url_for('signup'))


# ----------------- تحديث إعدادات الحساب وكلمة المرور -----------------

# ----------------- صفحة الإعدادات الجديدة -----------------
@app.route('/settings')
@app.route('/settings.html')
@login_required
def settings_page():
    return render_template('settings.html', user=current_user)


@app.route('/api/update_settings', methods=['POST'])
@login_required
def update_settings():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')

        if not name or not phone:
            return jsonify({"status": "error", "message": "الاسم ورقم الهاتف حقول مطلوبة."})

        # تحديث البيانات الأساسية للمستخدم الحالي
        current_user.name = name
        current_user.phone = phone

        # في حال رغبة المستخدم في تغيير كلمة المرور
        if new_password:
            if not check_password_hash(current_user.password, current_password):
                return jsonify({"status": "error", "message": "كلمة المرور الحالية غير صحيحة."})
            
            if len(new_password) < 6:
                return jsonify({"status": "error", "message": "يجب ألا تقل كلمة المرور الجديدة عن 6 أحرف."})
                
            current_user.password = generate_password_hash(new_password, method='pbkdf2:sha256')

        db.session.commit()
        return jsonify({"status": "success", "message": "تم تحديث إعدادات الحساب بنجاح! ⚙️✨"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"حدث خطأ أثناء الحفظ: {str(e)}"})


# ----------------- صفحة المحفظة -----------------
@app.route('/wallet')
@app.route('/wallet.html')
@login_required
def wallet():
    user_reservations = Reservation.query.join(Car).filter(Car.user_id == current_user.user_id).all()
    user_cars = Car.query.filter_by(user_id=current_user.user_id).all()
    return render_template('wallet.html', user=current_user, logs=user_reservations, cars=user_cars)

# ----------------- صفحة الداشبورد -----------------
@app.route('/user-dashboard')
@app.route('/user-dashboard.html')
@login_required
def user_dashboard():
    sync_external_sensor_checkout(current_user.user_id)
    all_garages = Garage.query.all()
    garages_data = []
    
    for g in all_garages:
        free_spots = Slot.query.filter_by(garage_id=g.garage_id, status='available').count()
        total_spots = Slot.query.filter_by(garage_id=g.garage_id).count()
        
        garages_data.append({
            'name': g.name,
            'price': float(g.fixed_price) if g.fixed_price else 0.0,
            'free_spots': free_spots,
            'total_spots': total_spots,
            # 💡 ضفنا السطرين دول عشان نسحب الإحداثيات من الداتا بيز
            'lat': float(g.latitude) if g.latitude else 0.0,
            'lng': float(g.longitude) if g.longitude else 0.0
        })
    
    user_cars = Car.query.filter_by(user_id=current_user.user_id).all()
        
    return render_template('user-dashboard.html', user=current_user, garages=garages_data, cars=user_cars)

# ----------------- صفحة الحجوزات -----------------
@app.route('/reservations')
@app.route('/Reservations_page.html')
@login_required
def reservations():
    sync_external_sensor_checkout(current_user.user_id)
    user_reservations = Reservation.query.join(Car).filter(Car.user_id == current_user.user_id).all()
    
    for log in user_reservations:
        # قيم افتراضية
        log.live_duration = "--"
        log.live_price = float(log.Reserved_hour_price * log.Duration_T) if log.Duration_T else 0.0
        log.log_in_t = None
        log.log_out_t = None
        log.tire_condition = {} # <-- متغير جديد لحفظ حالة الكاوتش

        # هنجيب السجل بتاع العربية من جدول logs
        parking_log = ParkingLog.query.filter_by(reserv_id=log.reserv_id).first()
        
        if parking_log:
            # 1. سحب وتجهيز حالة الكاوتش للـ UI
            if parking_log.tire_condition:
                tc = parking_log.tire_condition
                try:
                    log.tire_condition = json.loads(tc) if isinstance(tc, str) else tc
                except:
                    log.tire_condition = {}

            # 2. حساب الوقت والسعر
            if parking_log.log_in_t:
                log.log_in_t = parking_log.log_in_t
                log.log_out_t = parking_log.log_out_t
                time_str, price = calculate_live_parking(parking_log.log_in_t, parking_log.log_out_t, log.Reserved_hour_price)
                log.live_duration = time_str
                log.live_price = price

    from datetime import timedelta
    return render_template('Reservations_page.html', user=current_user, logs=user_reservations, macros={'timedelta': timedelta})


# ----------------- متحكم تأكيد الحجز -----------------
@app.route('/api/confirm_booking', methods=['POST'])
@login_required
def confirm_booking():
    try:
        release_expired_reservations()
        
        data = request.get_json()
        selected_car_id = data.get('car_id')
        duration = data.get('duration', 1) # افتراضي ساعة لو مفيش
        spot_type = data.get('spot_type', 'standard')

        if not selected_car_id:
            return jsonify({"status": "error", "message": "Please select a vehicle first."})

        user_balance = float(current_user.balance)

        if user_balance >= 50.0:
            car = Car.query.filter_by(car_id=selected_car_id, user_id=current_user.user_id).first()
            if not car:
                return jsonify({"status": "error", "message": "Invalid vehicle selected."})

            garage = Garage.query.first()
            if not garage:
                return jsonify({"status": "error", "message": "No garage available in the system."})
            
            slot = Slot.query.filter_by(garage_id=garage.garage_id, status='available').first()
            if not slot:
                return jsonify({"status": "error", "message": "Sorry, no available slots available right now."})

            slot.status = 'reserved'

            # الحجز الجديد بناءً على الأعمدة الجديدة
            new_reservation = Reservation(
                car_id=car.car_id,
                slot_id=slot.slot_id,
                reserv_status='active',
                Duration_T=int(duration),
                Spot_Type=spot_type,
                Reserved_hour_price=float(garage.fixed_price)
            )
            db.session.add(new_reservation)
            db.session.commit()
            
            return jsonify({
                "status": "success",
                "message": "✅ Payment Successful! Your spot is reserved."
            })
        else:
            return jsonify({
                "status": "error",
                "message": "Cannot confirm booking. Your wallet balance is less than 50 EGP."
            })
            
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})

# ----------------- بوابة الدخول الفعلية للسيارة -----------------
@app.route('/api/gate/entry', methods=['POST'])
def gate_entry():
    try:
        data = request.get_json()
        recognized_plate = data.get('plate_number', '').strip().upper()

        if not recognized_plate:
            return jsonify({"status": "error", "message": "No plate number provided."})

        car = Car.query.filter_by(plate_no=recognized_plate).first()
        if not car:
            return jsonify({"status": "error", "message": "Car not registered. Access Denied."})

        now = get_cairo_time()
        
        # هنجيب الحجوزات النشطة ونشيك وقتها
        active_reservations = Reservation.query.filter_by(car_id=car.car_id, reserv_status='active').all()
        valid_reservation = None
        
        for res in active_reservations:
            duration = res.Duration_T if res.Duration_T else 1
            if res.created_at:
                created_time = res.created_at.replace(tzinfo=None)
                end_time = created_time + timedelta(hours=duration)
                if end_time >= now:
                    valid_reservation = res
                    break

        if valid_reservation:
            valid_reservation.reserv_status = 'occupied'

            if valid_reservation.slot_id:
                slot = Slot.query.get(valid_reservation.slot_id)
                if slot:
                    slot.status = 'occupied'

            new_log = ParkingLog(
                reserv_id=valid_reservation.reserv_id,
                log_in_t=now
            )
            db.session.add(new_log)

            # ========= الكود الجديد لربط الإشعارات =========
            new_notif = Notification(
                user_id=car.user_id,
                title="License Plate Detected",
                message=f"Welcome! Your car plate {recognized_plate} was successfully scanned. Gate is opening.",
                is_read=False,
                # استخدمنا دالة الوقت اللي إنتي عملاها
                created_at=now 
            )
            db.session.add(new_notif)
            # ===============================================

            db.session.commit()

            return jsonify({
                "status": "success", 
                "message": f"Welcome {car.owner.name}! Your spot is secured. Gate Opening...",
                "open_gate": True
            });

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})

# ----------------- صفحة الدفع -----------------
@app.route('/payment')
@app.route('/payment.html')
@login_required
def payment():
    return render_template('payment.html', user=current_user)

# ----------------- معالجة الدفع -----------------
@app.route('/api/process_payment', methods=['POST'])
@login_required
def process_payment():
    try:
        data = request.get_json()
        amount_to_pay = float(data.get('amount', 0.0))
        user_balance = float(current_user.balance)

        if user_balance < amount_to_pay:
            return jsonify({"status": "error", "message": "Insufficient balance. Please recharge your wallet."})

        car = Car.query.filter_by(user_id=current_user.user_id).first()
        if not car:
            return jsonify({"status": "error", "message": "No car registered."})

        reservation = Reservation.query.filter_by(
            car_id=car.car_id,
            reserv_status='occupied'
        ).first()

        if not reservation:
            return jsonify({"status": "error", "message": "No active parking session found to checkout."})

        current_user.balance = user_balance - amount_to_pay

        # إضافة الداتا للأعمدة الجديدة
        new_tx = Transaction(
            reserv_id=reservation.reserv_id,
            fees=amount_to_pay,
            status='deducted',
            user_id=current_user.user_id,
            amount=amount_to_pay,
            trans_type='Parking Fee'
        )
        db.session.add(new_tx)

        parking_log = ParkingLog.query.filter_by(reserv_id=reservation.reserv_id).first()
        if parking_log and not parking_log.log_out_t:
            parking_log.log_out_t = get_cairo_time()

        reservation.reserv_status = 'completed'
        db.session.commit()

        return jsonify({"status": "success", "message": "Withdrawal completed successfully","new_balance": float(current_user.balance)})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})


# ----------------- شحن المحفظة -----------------
@app.route('/api/add_balance', methods=['POST'])
@login_required
def add_balance():
    try:
        data = request.get_json()
        amount_to_add = float(data.get('amount', 0.0))

        if amount_to_add <= 0:
            return jsonify({"status": "error", "message": "Invalid amount."})

        # تحديث رصيد المستخدم في جدول الـ users فقط
        current_balance = float(current_user.balance if current_user.balance else 0.0)
        current_user.balance = current_balance + amount_to_add
        
        # حفظ التعديل في الداتابيز
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Balance added successfully",
            "new_balance": float(current_user.balance)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})
    
    
# ----------------- صفحة العربيات -----------------
@app.route('/vehicles')
@app.route('/vehicles.html')
@login_required
def vehicles():
    user_cars = Car.query.filter_by(user_id=current_user.user_id).all()
    return render_template('vehicles.html', user=current_user, cars=user_cars)

@app.route('/api/add_vehicle', methods=['POST'])
@login_required
def add_vehicle():
    try:
        data = request.get_json()
        plate_no = data.get('plate_number', '').strip().upper()

        if not plate_no:
            return jsonify({"status": "error", "message": "الرجاء إدخال رقم اللوحة بشكل صحيح."})

        existing_car = Car.query.filter_by(plate_no=plate_no).first()
        if existing_car:
            return jsonify({"status": "error", "message": "هذه اللوحة مسجلة بالفعل في النظام."})

        new_car = Car(
            user_id=current_user.user_id,
            plate_no=plate_no,
            tire_condition={"status": "Good"}
        )
        db.session.add(new_car)
        db.session.commit()

        return jsonify({"status": "success", "message": "تم إضافة السيارة بنجاح! 🚗"})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})

@event.listens_for(Reservation, 'before_update')
def update_slot_on_reservation_status_change(mapper, connection, target):
    if target.reserv_status in ['cancelled', 'completed']:
        if target.slot_id:
            connection.execute(
                Slot.__table__.update()
                .where(Slot.__table__.c.slot_id == target.slot_id)
                .values(status='available')
            )
            
            
# ----------------- إلغاء الحجز -----------------
@app.route('/api/cancel_reservation', methods=['POST'])
@login_required
def cancel_reservation():
    try:
        data = request.get_json()
        reserv_id = data.get('reserv_id')

        if not reserv_id:
            return jsonify({"status": "error", "message": "Reservation ID is missing."})

        reservation = Reservation.query.get(reserv_id)
        if not reservation:
            return jsonify({"status": "error", "message": "Reservation not found."})

        # 1. تغيير حالة الحجز لـ ملغي
        reservation.reserv_status = 'cancelled'
        
        # 2. تحديث وقت الـ created_at لوقت الإلغاء (زي ما طلبتي)
        reservation.created_at = get_cairo_time()

        # ملاحظة: الفانكشن بتاعت update_slot_on_reservation_status_change 
        # اللي إنتي عملاها تحت في app.py هتفضي الركنة (Slot) تلقائياً بمجرد ما الحالة تتغير.

        db.session.commit()

        return jsonify({"status": "success", "message": "Reservation cancelled successfully."})

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})
    
# ----------------- جلب الإشعارات للمستخدم -----------------
@app.route('/api/get_notifications', methods=['GET'])
@login_required
def get_notifications():
    try:
        # هنجيب آخر 10 إشعارات لليوزر ده ونرتبهم من الأحدث للأقدم
        user_notifs = Notification.query.filter_by(user_id=current_user.user_id)\
                                        .order_by(Notification.created_at.desc())\
                                        .limit(10).all()
        
        notifs_data = []
        unread_count = 0
        
        for notif in user_notifs:
            notifs_data.append({
                "id": notif.id,
                "title": notif.title,
                "message": notif.message,
                "is_read": notif.is_read,
                "time": notif.created_at.strftime('%I:%M %p') if notif.created_at else ""
            })
            if not notif.is_read:
                unread_count += 1
                
        return jsonify({
            "status": "success",
            "notifications": notifs_data,
            "unread_count": unread_count
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ----------------- جعل الإشعارات مقروءة -----------------
# ----------------- جعل إشعار محدد مقروء -----------------
@app.route('/api/mark_notification_read', methods=['POST'])
@login_required
def mark_notification_read():
    try:
        data = request.get_json()
        notif_id = data.get('notif_id')
        
        if notif_id:
            # هنجيب الإشعار ده بالظبط من الداتابيز
            notif = Notification.query.filter_by(id=notif_id, user_id=current_user.user_id).first()
            if notif and not notif.is_read:
                notif.is_read = True
                db.session.commit()
                
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})
    
    
    
    # ----------------- جعل كل الإشعارات دفعة واحدة مقروءة -----------------
@app.route('/api/mark_all_notifications_read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    try:
        # جلب كل الإشعارات غير المقروءة للمستخدم الحالي
        unread_notifs = Notification.query.filter_by(user_id=current_user.user_id, is_read=False).all()
        
        for notif in unread_notifs:
            notif.is_read = True
            
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})
    
@app.route('/api/update_sensors', methods=['POST'])
@app.route('/api/update_sensors/', methods=['POST'])
def update_sensors():
    try:
        data = request.get_json()

        print("\n========== SENSOR DATA ==========")
        print("Received:", data)

        if not data:
            return jsonify({
                "status": "error",
                "message": "No data received"
            }), 400

        flame_val = data.get('flame_status', 'Normal')
        gas_val = data.get('gas_status', 'Normal')
        temp = data.get('temperature')
        hum = data.get('humidity')

        print("Flame =", flame_val)
        print("Gas =", gas_val)
        print("Temperature =", temp)
        print("Humidity =", hum)

        TARGET_GARAGE_ID = 1	

        flame_sensor = Sensor.query.filter_by(
            garage_id=TARGET_GARAGE_ID,
            sensor_type='Flame'
        ).first()

        smoke_sensor = Sensor.query.filter_by(
            garage_id=TARGET_GARAGE_ID,
            sensor_type='Smoke'
        ).first()

        temp_sensor = Sensor.query.filter_by(
            garage_id=TARGET_GARAGE_ID,
            sensor_type='Temp'
        ).first()

        hum_sensor = Sensor.query.filter_by(
            garage_id=TARGET_GARAGE_ID,
            sensor_type='Humidity'
        ).first()

        print("Flame Sensor Found:", flame_sensor)
        print("Smoke Sensor Found:", smoke_sensor)
        print("Temp Sensor Found:", temp_sensor)
        print("Humidity Sensor Found:", hum_sensor)

        # تحديث الفليم
        if flame_sensor:
            flame_sensor.status = str(flame_val)

        # تحديث السموك
        if smoke_sensor:
            smoke_sensor.status = str(gas_val)

        # تحديث الحرارة
        if temp_sensor and temp is not None:
            temp_sensor.status = str(temp)
            print("Saving Temp =", temp_sensor.status)

        # تحديث الرطوبة
        if hum_sensor and hum is not None:
            hum_sensor.status = str(hum)
            print("Saving Humidity =", hum_sensor.status)

        db.session.commit()

        print("✅ DATABASE UPDATED SUCCESSFULLY")
        print("================================\n")

        return jsonify({
            "status": "success",
            "message": "Sensors updated successfully"
        })

    except Exception as e:
        db.session.rollback()

        print("❌ DATABASE ERROR:")
        print(repr(e))

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
    
if __name__ == '__main__':
    emergency_thread = threading.Thread(target=run_emergency_loop, daemon=True)
    emergency_thread.start()

    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)