import sys
import threading
import time
from ihm.shared import send_log
import ihm.shared as shared
from ihm.tasks import background_loop
from ihm.zmq_client import ZmqClient

# Classe simple pour rediriger les prints vers l'IHM via ZMQ
class LogCapture:
    def __init__(self, original, tag):
        self.orig = original
        self.tag = tag
        self.encoding = getattr(original, 'encoding', 'utf-8')
    def write(self, msg):
        try: self.orig.write(msg); self.orig.flush()
        except: pass
        if msg and msg.strip():
            try: send_log(msg.strip(), self.tag)
            except: pass
    def flush(self): 
        try: self.orig.flush()
        except: pass
    def __getattr__(self, name): return getattr(self.orig, name)

def run_ihm():
    print("[IHM] Démarrage du client ZMQ...")
    
    # Initialisation et démarrage du client ZMQ
    server_ip = shared.cfg.get('server_ip', '192.168.10.2')
    client = ZmqClient(server_ip=server_ip)
    shared.zmq_client_instance = client
    client.start()
    
    # Redirection Logs (après le démarrage du client)
    sys.stdout = LogCapture(sys.stdout, 'info')
    sys.stderr = LogCapture(sys.stderr, 'error')

    # Démarrage de la boucle d'arrière-plan (tasks : batterie, etc.)
    bg_thread = threading.Thread(target=background_loop, daemon=True)
    bg_thread.start()
    
    print("[IHM] Client ZMQ et tâches de fond démarrés.")
    
    # Rester en vie
    while True:
        time.sleep(1)