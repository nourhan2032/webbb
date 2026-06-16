from datetime import datetime

def get_all_dynamic_prices(fixed_price, occupancy_high=False):
    # 1. قائمة إجازات مصر 2026
    egypt_holidays_2026 = [
        "07-01", "25-01", "20-03", "21-03", "22-03", "13-04", 
        "25-04", "01-05", "27-05", "28-05", "29-05", "16-06", 
        "30-06", "23-07", "25-08", "06-10"
    ]
    
    now = datetime.now()
    current_hour = now.hour
    current_day = now.strftime('%A') 
    current_date = now.strftime('%d-%m')

    is_holiday = current_date in egypt_holidays_2026
    is_weekend = current_day in ['Friday', 'Saturday']

    # 2. حساب الفاكتور الديناميكي للركنة العادية فقط
    factor = 0.7  # القيمة المبدئية للفاكتور
    
    if is_holiday: factor += 0.2
    if is_weekend: factor += 0.2

    # شرط الذروة
    if is_holiday or is_weekend:
        if 17 <= current_hour <= 23: factor += 0.2
    else:
        if 8 <= current_hour <= 10: factor += 0.2

    # زحمة الجراج
    if occupancy_high: factor += 0.2

    # الحفاظ على النطاق بين 0.7 و 1.3
    factor = round(max(0.7, min(factor, 1.3)), 2)

    # 3. حساب السعر الديناميكي الـ Standard (السعر الأساسي المرجعي)
    dynamic_standard_price = float(fixed_price) * factor

    # 4. توليد التلات أسعار وتقريبهم لأرقام صحيحة بدون كسور
    final_prices = {
        "standard": int(round(dynamic_standard_price)),
        "vip": int(round(dynamic_standard_price * 1.3)),
        "special_needs": int(round(dynamic_standard_price * 0.7))
    }
    
    return final_prices