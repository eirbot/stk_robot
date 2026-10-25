import serial
import threading
import time
import ihm.shared as shared  # On importe ton shared pour y stocker X, Y, Theta

class ESPActionneurs:
    def __init__(self, port='/dev/esp_action', baudrate=115200):
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
            print(f"[ACTIONNEURS] ✅ Connexion établie sur {self.port}")
            
            # Lancement du Thread de réception
            self.running = True
            self.rx_thread = threading.Thread(target=self._receive_loop, daemon=True, name="ESP_Rx_Thread")
            self.rx_thread.start()
            
        except serial.SerialException as e:
            print(f"[ACTIONNEURS] ❌ Erreur critique : Impossible d'ouvrir {self.port} -> {e}")

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
                # print(f"[ACTIONNEURS] -> {cmd}") # Décommenter pour le debug
            except Exception as e:
                print(f"[ACTIONNEURS] ❌ Erreur d'envoi : {e}")

    def send_raw(self, cmd):
        """Alias pour send, compatible avec les appels génériques."""
        self.send(cmd)

    def bloquer(self):
        """Fin de match / STOP : l'ESP interrompt le mouvement en cours et ignore la suite."""
        self.send("X")

    def debloquer(self):
        self.send("U")

    def init_robot(self):
        self.send("I")

    def tourner(self, actionneur_id):
        cmd = "T" + " " + str(actionneur_id)
        self.send(cmd)

    def ascenseur(self, actionneur_id, hauteur):
        cmd = "A" + " " + str(actionneur_id) + " " + str(hauteur)
        self.send(cmd)

    def poser(self, actionneur_id):
        self.ascenseur(actionneur_id, 0)
        self.release(actionneur_id)
    
    def grab(self, actionneur_id):
        cmd = "G" + " " + str(actionneur_id)
        self.send(cmd)
    
    def release(self, actionneur_id):
        cmd = "R" + " " + str(actionneur_id)
        self.send(cmd)

    def pivoter(self, actionneur_id, sens):
        cmd = "P" + " " + str(actionneur_id) + " " + str(sens)
        self.send(cmd)

    # --- Poses combinées ---------------------------------------------------------------
    # Séquences de l'année 2025 (Kapla, thermomètre) vidées : les noms restent (IHM, boutons,
    # Blockly les appellent), le contenu est à redéfinir pour 2027 avec les primitives
    # ci-dessus (ascenseur, pivoter, grab, release, tourner).

    def _a_definir(self, nom):
        print(f"[ACTIONNEURS] {nom} : séquence à définir (2027)")

    def pose_match(self):
        """Position de départ du match."""
        self.init_robot()
        self.pose_camera()

    def pose_camera(self):
        self._a_definir("pose_camera")

    def pose_ranger(self):
        self._a_definir("pose_ranger")

    def pose_deploy(self):
        self._a_definir("pose_deploy")

    def pose_grab(self):
        self._a_definir("pose_grab")

    def pose_retourne(self, actionneur_ids):
        self._a_definir("pose_retourne")

    def pose_poser(self):
        self._a_definir("pose_poser")

    def pose_temperature(self, is_yellow):
        self._a_definir("pose_temperature")

    # --- Tâche de fond (Thread) ---
    
    def _receive_loop(self):
        """Boucle tournant en arrière-plan pour traiter les retours de l'ESP."""
        print("[ACTIONNEURS] 🎧 Thread d'écoute démarré.")
        while self.running:
            try:
                # readline bloquant (timeout série) : réveil dès qu'une ligne arrive, sans polling
                ligne = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if ligne:
                    self._process_message(ligne)
            except Exception as e:
                print(f"[ACTIONNEURS] Exception in rx loop: {e}")
                time.sleep(0.05) # Évite une boucle à vide si le port est en erreur

    def _process_message(self, msg):
        """Déchiffre le message et met à jour l'état partagé du robot."""
        print(f"[ACTIONNEURS] <- {msg}") # Décommenter pour le debug
        if msg == "D":
            self.cmd_done_event.set()
        elif msg == "E":
            self.cmd_done_event.set()
            self.cmd_aborted = True
            print("[ACTIONNEURS] ❌ Erreur d'init")
        pass