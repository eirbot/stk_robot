
import time
import threading
import ihm.shared as shared

def timer_loop():
    print("[TIMER] Thread démarré.")
    while True:
        try:
            # Sync Timer independent of strategy blocking
            if shared.state["match_running"] and shared.state["start_time"]:
                elapsed = time.time() - shared.state["start_time"]
                remaining = max(0.0, 100.0 - elapsed)
                shared.state["timer"] = remaining
                shared.state["timer_str"] = f"{remaining:.1f}"
                
            time.sleep(0.5) # 2Hz Update Rate
            
        except Exception as e:
            print(f"[TIMER] Error: {e}")
            time.sleep(1)

def start_timer_thread():
    t = threading.Thread(target=timer_loop, daemon=True)
    t.start()
