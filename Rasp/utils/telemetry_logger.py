import os
import time
import csv
import threading
from datetime import datetime
import ihm.shared as shared
from utils.system_info import get_battery_voltage, get_battery_current, get_cpu_temp

class TelemetryLogger:
    # Journaux de match (page Replay de la base, qui les lit par ssh : Base/Web/media.go)
    # ROBOT_TELEMETRY_DIR : autre dossier (tests, simulateur)
    DEFAULT_DIR = os.environ.get("ROBOT_TELEMETRY_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "telemetry")

    def __init__(self, log_dir=DEFAULT_DIR, interval=0.1):
        self.log_dir = log_dir
        self.interval = interval
        self.running = False
        self.thread = None
        self.file = None
        self.writer = None
        
        # Ensure log directory exists
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            
    def start(self):
        if self.running: return
        self.running = True
        
        # Create new log file with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(self.log_dir, f"blackbox_{timestamp}.csv")
        
        try:
            self.file = open(filename, 'w', newline='')
            self.writer = csv.writer(self.file)
            # Header
            self.writer.writerow([
                "timestamp", 
                "match_time", 
                "x", "y", "theta", 
                "match_running", "fsm_state", 
                "voltage", "current", "cpu_temp"
            ])
            print(f"[LOGGER] Enregistrement télémétrie démarré : {filename}")
            
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        except Exception as e:
            print(f"[LOGGER] Erreur création fichier log: {e}")
            self.running = False

    def stop(self):
        """Ferme le journal en cours (sans effet s'il n'y en a pas : fin à 100 s puis STOP)."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        if self.file:
            self.file.close()
            self.file = None
            print("[LOGGER] Enregistrement terminé.")

    def _loop(self):
        start_time = time.time()
        
        while self.running:
            try:
                now = time.time()
                match_time = now - shared.state.get('start_time', now) if shared.state.get('start_time') else 0
                
                # Collect Data
                row = [
                    f"{now:.3f}",
                    f"{match_time:.2f}",
                    f"{shared.robot_pos['x']:.1f}",
                    f"{shared.robot_pos['y']:.1f}",
                    f"{shared.robot_pos['theta']:.2f}",
                    "1" if shared.state['match_running'] else "0",
                    shared.state.get('fsm_state', 'UNKNOWN'),
                    get_battery_voltage(), # Returns string "12.4V" or similar, might need cleaning for CSV? 
                                          # get_battery_voltage returns "XX.XXV" string usually. 
                                          # Let's clean it here or in frontend. Let's keep raw for now.
                    get_battery_current(),
                    get_cpu_temp()
                ]
                
                if self.writer:
                    self.writer.writerow(row)
                    self.file.flush() # Ensure data is written
                
                time.sleep(self.interval)
                
            except Exception as e:
                print(f"[LOGGER] Erreur boucle: {e}")
                time.sleep(1)

# Global Instance (optional)
telemetry = TelemetryLogger()
