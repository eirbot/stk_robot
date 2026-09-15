import serial
import threading
import time
import ihm.shared as shared  # On importe ton shared pour y stocker X, Y, Theta

class ESPMotors:
    def __init__(self, port='/dev/esp_motors', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        
        # Le Lock permet d'éviter que 2 threads parlent à l'ESP en même temps
        self.tx_lock = threading.Lock() 
        self.running = False
        self.rx_thread = None
        self.cmd_done_event = threading.Event()
        self.cmd_aborted = False

    def start(self):
        """Initialise la connexion et lance le thread d'écoute."""
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
            # Désactive DTR et RTS pour éviter que l'ESP32 ne reste bloqué en mode Reset ou Bootloader
            self.ser.setDTR(False)
            self.ser.setRTS(False)
            self.ser.reset_input_buffer()
            print(f"[MOTORS] ✅ Connexion établie sur {self.port}")
            
            # Lancement du Thread de réception
            self.running = True
            self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True, name="ESP_Rx_Thread")
            self.rx_thread.start()
            
        except serial.SerialException as e:
            print(f"[MOTORS] ❌ Erreur critique : Impossible d'ouvrir {self.port} -> {e}")

    def stop(self):
        """Arrête proprement le thread et ferme le port."""
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send(self, cmd):
        """Envoie une commande à l'ESP de manière Thread-Safe."""
        if not self.ser or not self.ser.is_open:
            return
        
        # On s'assure qu'un seul thread peut écrire sur le port série à la fois
        with self.tx_lock:
            try:
                msg = f"{cmd}\n"
                self.ser.write(msg.encode('utf-8'))
                # print(f"[MOTORS] -> {cmd}") # Décommenter pour le debug
            except Exception as e:
                print(f"[MOTORS] ❌ Erreur d'envoi : {e}")

    # --- Fonctions simplifiées pour tes autres threads ---
    
    def goto(self, x, y, theta):
        self.cmd_done_event.clear()
        self.cmd_aborted = False
        self.send(f"G {x} {y} {theta}")
        
        # On attend la fin, mais on vérifie régulièrement si le match est fini
        while not self.cmd_done_event.wait(0.2):
            # Si le match est stoppé manuellement (IHM ou Bouton Stop)
            if not shared.state.get("match_running", False):
                print("[MOTORS] 🛑 Match arrêté pendant mouvement, envoi STOP")
                self.stop_robot()
                return False
        
        return not self.cmd_aborted

    def set_speed(self, vx, vtheta):
        """
        Envoie une consigne de vitesse au robot.
        :param vx: Vitesse linéaire en mm/s (-1000 à 1000)
        :param vtheta: Vitesse angulaire en deg/s (-360 à 360)
        """
        vx_int = int(round(vx))
        vtheta_int = int(round(vtheta))
        self.send(f"V {vx_int} {vtheta_int}")

    def stop_robot(self):
        """Arrête immédiatement les moteurs de l'ESP."""
        self.send("H")

    def set_pos(self, x, y, theta):
        self.send(f"S {x} {y} {theta}")
        
    def set_lidar_state(self, val):
        self.send(f"L {val}")

    # --- Tâche de fond (Thread) ---
    
    def _receive_loop(self):
        """Boucle tournant en arrière-plan pour traiter les retours de l'ESP."""
        print("[MOTORS] 🎧 Thread d'écoute démarré.")
        while self.running:
            try:
                if self.ser.in_waiting > 0:
                    ligne = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if ligne:
                        self._process_message(ligne)
            except Exception as e:
                print(f"[MOTORS] Exception in rx loop: {e}")
                # Évite que le thread ne crash silencieusement en cas de bruit série
                pass 
                
            time.sleep(0.005) # Petite pause pour ne pas manger 100% du CPU

    def _process_message(self, msg):
        """Déchiffre le message et met à jour l'état partagé du robot."""
        # print(f"[MOTORS] <- {msg}") # Décommenter pour le debug
        
        if msg.startswith("T "):
            try:
                parts = msg.split()
                if len(parts) == 4:
                    # On met à jour directement ton dictionnaire global "shared"
                    # Ainsi ton IHM et ta Strat ont toujours la position en temps réel
                    shared.robot_pos['x'] = float(parts[1])
                    shared.robot_pos['y'] = float(parts[2])
                    shared.robot_pos['theta'] = float(parts[3])
            except ValueError:
                print(f"[MOTORS] ⚠️ Erreur de parsing Odométrie : {msg}")
        elif msg == "D":
            # Le mouvement est terminé avec succès
            self.cmd_aborted = False
            self.cmd_done_event.set()
        elif msg == "A":
            # Le mouvement a été annulé (timeout obstacle)
            self.cmd_aborted = True
            self.cmd_done_event.set()