import psycopg2
import time
from datetime import datetime, timedelta

# ==========================================================
# 1. DATABASE SETTINGS
# ==========================================================
DB_URI = 'postgresql://postgres.fjubdwibycchdqfgjsco:kksS8JWstgxvCC.@aws-0-eu-west-1.pooler.supabase.com:5432/postgres'

# ==========================================================
# 2. EMERGENCY TRACKER (Garage-Specific & Sensor-Specific)
# ==========================================================
active_alerts = {}
is_first_run = True  # Flag to prevent "Startup Bomb" of old alerts

def check_sensors_and_alert():
    global active_alerts, is_first_run
    try:
        conn = psycopg2.connect(DB_URI)
        cursor = conn.cursor()

        # Read all sensors and their garage IDs
        cursor.execute("SELECT sensor_id, garage_id, sensor_type, status FROM sensors;")
        sensors_data = cursor.fetchall()

        new_alerts = set()

        for s_id, g_id, s_type, status in sensors_data:
            if not status or not s_type or not g_id: 
                continue
            
            s_type = s_type.lower()
            s_status = status.lower()

            is_emergency = False
            if s_status == 'emergency' and s_type in ['flame', 'smoke', 'gas']:
                is_emergency = True
            elif s_type == 'temp':
                if s_status == 'emergency':
                    is_emergency = True
                else:
                    try:
                        if float(status) > 45.0:
                            is_emergency = True
                    except ValueError:
                        pass 

            # If this is the very first run, just memorize the current state silently
            if is_first_run:
                active_alerts[s_id] = is_emergency
                continue

            if s_id not in active_alerts:
                active_alerts[s_id] = False

            # Detect new emergency
            if is_emergency and not active_alerts[s_id]:
                new_alerts.add((g_id, s_type))
            # Detect cleared emergency
            elif not is_emergency and active_alerts[s_id]:
                print(f"🟢 [CLEAR] Sensor '{s_type.upper()}' in Garage {g_id} returned to normal.")
            
            active_alerts[s_id] = is_emergency

        # Finish silent initialization without sending old alerts
        if is_first_run:
            print("✅ [SYSTEM INIT] Initial sensor states loaded silently. Ready for new alerts.")
            is_first_run = False
            cursor.close()
            conn.close()
            return

        # Process new alerts targeting specific garages
        if new_alerts:
            now = datetime.utcnow() + timedelta(hours=3)
            notifications_data = []

            for g_id, alert_type in new_alerts:
                print(f"🚨 [NEW DANGER DETECTED] {alert_type.upper()} in Garage ID: {g_id}. Fetching targeted users...")

                # Magic Query: Fetches ONLY users in THIS specific garage
                query_users = """
                    SELECT DISTINCT c.user_id, r.reserv_status
                    FROM reservations r
                    JOIN cars c ON r.car_id = c.car_id
                    JOIN slots s ON r.slot_id = s.slot_id
                    WHERE r.reserv_status IN ('reserved', 'occupied')
                      AND s.garage_id = %s;
                """
                cursor.execute(query_users, (g_id,))
                affected_users = cursor.fetchall()

                for user_id, r_status in affected_users:
                    if not user_id: continue

                    if alert_type == 'flame':
                        title = "🔥 EMERGENCY: FIRE DETECTED"
                        msg = "CRITICAL: Open fire detected in your garage! Please evacuate and retrieve your car immediately if safe." if r_status == 'occupied' else "CRITICAL: Open fire detected in the garage! DO NOT come. Your reservation is suspended for safety."
                    elif alert_type == 'smoke':
                        title = "🌫️ EMERGENCY: SMOKE DETECTED"
                        msg = "ALERT: Heavy smoke detected in your garage! Please retrieve your car ASAP." if r_status == 'occupied' else "ALERT: Heavy smoke detected in the garage! Please delay your arrival."
                    elif alert_type == 'temp':
                        title = "🌡️ EMERGENCY: HIGH TEMPERATURE"
                        msg = "CRITICAL: Dangerously high temperature detected (>45°C) in your garage! Please retrieve your car immediately." if r_status == 'occupied' else "CRITICAL: Dangerously high temperature detected in the garage! DO NOT come."
                    elif alert_type == 'gas':
                        title = "⚠️ EMERGENCY: GAS LEAK"
                        msg = "ALERT: Toxic Gas leak detected in your garage! Please retrieve your car ASAP." if r_status == 'occupied' else "ALERT: Toxic Gas leak detected in the garage! Please delay your arrival."

                    notifications_data.append((user_id, title, msg, False, now))

            if notifications_data:
                cursor.executemany("""
                    INSERT INTO notifications (user_id, title, message, is_read, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                """, notifications_data)
                conn.commit()
                print(f"✅ [NOTIFICATIONS SENT] Successfully sent {len(notifications_data)} targeted emergency notifications.")
            else:
                print(f"ℹ️ [INFO] Emergency triggered in Garage {g_id}, but no active reservations found there.")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ [DB Error] Connection or sensor reading issue: {e}")

# ==========================================================
# 3. MAIN LOOP EXPORT
# ==========================================================
def run_emergency_loop():
    print("🛡️ Starting Targeted Emergency Monitoring System (Per-Garage & Per-Sensor)...")
    try:
        while True:
            check_sensors_and_alert()
            time.sleep(5)
    except Exception as e:
        print(f"❌ Emergency system stopped due to an error: {e}")

if __name__ == "__main__":
    run_emergency_loop()