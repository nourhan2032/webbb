from datetime import datetime, timedelta

def calculate_live_parking(log_in_time, log_out_time, hourly_price):
    # لو مفيش وقت دخول
    if not log_in_time:
        return "0h 0m", float(hourly_price)
        
    # نشيل الـ Timezone لو موجود 
    if log_in_time.tzinfo:
        log_in_time = log_in_time.replace(tzinfo=None)
        
    # =======================================================
    # 💡 التعديل السحري: هل نعد لايف ولا نثبت الوقت؟
    # =======================================================
    if log_out_time:
        # لو فيه وقت خروج (يعني الخلية مش NULL)، نثبت الحسبة عليه
        if log_out_time.tzinfo:
            log_out_time = log_out_time.replace(tzinfo=None)
        end_time = log_out_time
    else:
        # لو الخلية لسه NULL، نحسب على توقيت دلوقتي (Live)
        end_time = datetime.utcnow() + timedelta(hours=3)
    # =======================================================

    # نحسب الفرق بينهم بالدقائق
    delta = end_time - log_in_time
    total_minutes = int(delta.total_seconds() // 60)
    
    if total_minutes <= 0:
        return "0h 0m", float(hourly_price)
        
    hours = total_minutes // 60
    mins = total_minutes % 60
    
    # نجهز الوقت كـ Text
    time_str = f"{hours}h {mins}m"
    
    # لوجيك الحساب: كسر الـ 30 دقيقة بساعة
    billed_hours = hours
    if mins >= 30:
        billed_hours += 1
        
    billed_hours = max(1, billed_hours)
    
    # حساب السعر النهائي
    final_price = billed_hours * float(hourly_price)
    
    return time_str, final_price