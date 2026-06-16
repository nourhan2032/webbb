from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
# هنحتاج نستورد JSONB عشان نوع الداتا الجديد اللي هاجر ضافته
from sqlalchemy.dialects.postgresql import JSONB

db = SQLAlchemy()

# الدالة دي بتجيب توقيت مصر وتجهزه عشان يتحفظ في الداتابيز صح
def get_cairo_time():
    return datetime.utcnow() + timedelta(hours=3)

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=True) 
    password = db.Column(db.String(255), nullable=False)
    balance = db.Column(db.Numeric(10, 2), default=50.00)
    
    # Relationships
    cars = db.relationship('Car', backref='owner', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)
    transactions = db.relationship('Transaction', backref='user_owner', lazy=True)

    def get_id(self):
        return str(self.user_id)

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.BigInteger, primary_key=True) # int8
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'))
    title = db.Column(db.Text)
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=get_cairo_time)

class Car(db.Model):
    __tablename__ = 'cars'
    car_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE'))
    plate_no = db.Column(db.String(20), unique=True, nullable=False)
    tire_condition = db.Column(JSONB) # تعديل النوع
    
    # Relationships
    reservations = db.relationship('Reservation', backref='car', lazy=True)

class Garage(db.Model):
    __tablename__ = 'garages'
    garage_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    fixed_price = db.Column(db.Numeric(10, 2), nullable=False) # تعديل الاسم
    latitude = db.Column(db.Numeric(10, 8), nullable=False)
    longitude = db.Column(db.Numeric(11, 8), nullable=False)
    address = db.Column(db.Text) 
    
    slots = db.relationship('Slot', backref='garage', lazy=True)
    sensors = db.relationship('Sensor', backref='garage', lazy=True) # علاقة جديدة

class Slot(db.Model):
    __tablename__ = 'slots'
    slot_id = db.Column(db.Integer, primary_key=True)
    garage_id = db.Column(db.Integer, db.ForeignKey('garages.garage_id', ondelete='CASCADE'))
    slot_name = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(50), default='empty')
    coordinates = db.Column(JSONB) # عمود جديد
    
    # تم إزالة علاقة السينسور من هنا ونقلها للجراج

class Sensor(db.Model):
    __tablename__ = 'sensors'
    sensor_id = db.Column(db.Integer, primary_key=True)
    garage_id = db.Column(db.Integer, db.ForeignKey('garages.garage_id', ondelete='CASCADE')) # تعديل الربط
    status = db.Column(db.Text) # تعديل النوع
    sensor_type = db.Column(db.Text) # عمود جديد

class Reservation(db.Model):
    __tablename__ = 'reservations'
    reserv_id = db.Column(db.Integer, primary_key=True)
    car_id = db.Column(db.Integer, db.ForeignKey('cars.car_id', ondelete='CASCADE'))
    slot_id = db.Column(db.Integer, db.ForeignKey('slots.slot_id'))
    
    reserv_status = db.Column(db.Text, default='active') 
    created_at = db.Column(db.DateTime(timezone=True), default=get_cairo_time)
    
    # الأعمدة الجديدة بدل start_t و end_t
    Duration_T = db.Column(db.Integer) 
    Spot_Type = db.Column(db.Text) 
    Reserved_hour_price = db.Column(db.Float) 

    # Relationships
    logs = db.relationship('ParkingLog', backref='reservation', lazy=True)
    transactions = db.relationship('Transaction', backref='reservation', lazy=True)
    slot = db.relationship('Slot', backref='reservations', lazy=True)


class ParkingLog(db.Model):
    __tablename__ = 'logs'
    log_id = db.Column(db.Integer, primary_key=True)
    reserv_id = db.Column(db.Integer, db.ForeignKey('reservations.reserv_id', ondelete='CASCADE'))
    
    log_in_t = db.Column(db.DateTime(timezone=True), default=get_cairo_time)
    log_out_t = db.Column(db.DateTime(timezone=True))
    tire_condition = db.Column(db.JSON)
class Transaction(db.Model):
    __tablename__ = 'transactions'
    trans_id = db.Column(db.Integer, primary_key=True)
    reserv_id = db.Column(db.Integer, db.ForeignKey('reservations.reserv_id'))
    fees = db.Column(db.Numeric(10, 2))
    status = db.Column(db.String(50), default='deducted') 
    created_at = db.Column(db.DateTime(timezone=True), default=get_cairo_time)
    
    # أعمدة جديدة
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))
    amount = db.Column(db.Float)
    trans_type = db.Column(db.Text)