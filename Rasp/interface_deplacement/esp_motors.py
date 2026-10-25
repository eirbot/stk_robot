import serial
import threading
import time
import ihm.shared as shared  # On importe ton shared pour y stocker X, Y, Theta

# Protocole série avec l'ESP moteurs (une commande par ligne ; référence : src/motors/protocol.h) :
#   Rasp -> ESP : G id x y theta (GoTo), V vx omega, S x y theta, L etat, H, K (battement de cœur)
#   ESP -> Rasp : T x y theta (odométrie), D id (GoTo id fini), A id (GoTo id annulé),
#                 W (watchdog liaison : l'ESP n'a rien reçu depuis 300 ms et a coupé les moteurs),
#                 E message (commande refusée par l'ESP)
# Nombres décimaux avec un point. Chaque GoTo a son numéro : un « A » en retard d'un ancien
# GoTo ne termine jamais le GoTo en cours. Un nouveau G pendant un GoTo le remplace (l'ESP
# répond « A ancien »).
# Tout octet envoyé est un signe de vie : "K" n'est émis que si aucune autre commande
# n'est partie depuis HEARTBEAT_PERIOD. Après un "W", rien ne reprend seul côté ESP :
# il faut renvoyer une commande (G, V...).
HEARTBEAT_PERIOD = 0.1  # s, à garder bien sous le délai du watchdog ESP (300 ms)
# Aucun D / A au bout de ce délai (ESP redémarré, trame perdue) : GoTo considéré annulé
GOTO_TIMEOUT_S = 30.0


class ESPError(Exception):
    """ESP moteurs absent (port série non ouvert) : aucun déplacement possible."""

class ESPMotors:
    def __init__(self, port='/dev/esp_motors', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        
        # Le Lock permet d'éviter que 2 threads parlent à l'ESP en même temps
        self.tx_lock = threading.Lock() 
        self.running = False
        self.rx_thread = None
        # GoTo en attente de D / A : numéro -> {"event", "ok"}
        self._goto_lock = threading.Lock()
        self._goto_waiters = {}
        self._next_goto_id = 1
        self.errors = []  # dernières trames « E » de l'ESP
        # Dernier instant où l'odométrie a bougé (sert à savoir si le robot est immobile)
        self.last_motion_time = time.time()
        self.last_rx_time = None       # dernière trame reçue de l'ESP (check-list avant match)
        self._last_pose = None

        # Battement de cœur / watchdog liaison ESP
        self.hb_thread = None
        self._last_tx_time = 0.0       # Dernier envoi réussi (toute commande compte)
        self.watchdog_count = 0        # Nombre de trames "W" reçues depuis le démarrage
        self.watchdog_tripped = False  # True entre un "W" et la consigne G/V suivante
        self.last_watchdog_time = None

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

            # Battement de cœur : sans lui l'ESP coupe les moteurs au bout de 300 ms
            self.hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="ESP_Heartbeat")
            self.hb_thread.start()
            
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
                self._last_tx_time = time.monotonic()
                if cmd[:1] in ("G", "V"):
                    # Nouvelle consigne de mouvement : l'ESP repart, le watchdog n'est plus d'actualité
                    self.watchdog_tripped = False
                # print(f"[MOTORS] -> {cmd}") # Décommenter pour le debug
            except Exception as e:
                print(f"[MOTORS] ❌ Erreur d'envoi : {e}")

    # --- Fonctions simplifiées pour tes autres threads ---
    
    @property
    def connected(self):
        return self.ser is not None and self.ser.is_open

    def goto(self, x, y, theta, manual=False):
        """GoTo en repère table : converti dans le repère odométrie de l'ESP (fusion caméra).
        Renvoie True si l'ESP a répondu « D », False s'il a été annulé (A, arrêt du match,
        délai dépassé). Lève ESPError si l'ESP n'est pas branché."""
        if not self.connected:
            raise ESPError(f"ESP moteurs non connecté ({self.port}) : déplacement impossible")
        with self._goto_lock:
            goto_id = self._next_goto_id
            self._next_goto_id = goto_id % 1_000_000 + 1
            waiter = {"event": threading.Event(), "ok": False}
            self._goto_waiters[goto_id] = waiter
        ox, oy, otheta = shared.loc.to_odom(x, y, theta)
        self.send(f"G {goto_id} {ox:.1f} {oy:.1f} {otheta:.2f}")

        try:
            t_end = time.monotonic() + GOTO_TIMEOUT_S
            # On attend la fin, en vérifiant régulièrement si le match est fini ou si un arrêt est demandé
            while not waiter["event"].wait(0.2):
                if manual:
                    # En mode manuel, on ne stoppe que si l'état FSM est explicitement STOPPED
                    if shared.state.get("fsm_state") == "STOPPED":
                        print("[MOTORS] 🛑 Arrêt demandé pendant déplacement manuel, envoi STOP")
                        self.stop_robot()
                        return False
                elif not shared.state.get("match_running", False):
                    # Si le match autonome est stoppé (IHM ou Bouton Stop)
                    print("[MOTORS] 🛑 Match arrêté pendant mouvement, envoi STOP")
                    self.stop_robot()
                    return False
                if time.monotonic() > t_end:
                    print(f"[MOTORS] ⚠️ GoTo {goto_id} sans réponse de l'ESP après {GOTO_TIMEOUT_S:.0f} s : annulé")
                    self.stop_robot()
                    return False
            return waiter["ok"]
        finally:
            with self._goto_lock:
                self._goto_waiters.pop(goto_id, None)

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
        """Pose connue en repère table. Le repère odo de la fusion = exactement ce que
        l'ESP reçoit (valeurs arrondies à l'envoi)."""
        odo = (round(x, 1), round(y, 1), round(theta, 2))
        self._last_pose = None
        shared.set_known_pose(x, y, theta, odo_pose=odo)
        self.send(f"S {odo[0]:.1f} {odo[1]:.1f} {odo[2]:.2f}")
        
    def set_lidar_state(self, val):
        self.send(f"L {val}")

    # --- Tâche de fond (Thread) ---

    def _heartbeat_loop(self):
        """Envoie "K" toutes les HEARTBEAT_PERIOD si aucune autre commande n'est partie."""
        next_beat = time.monotonic()
        while self.running:
            now = time.monotonic()
            if now - self._last_tx_time >= HEARTBEAT_PERIOD * 0.9:
                self.send("K")
            # Cadence fixe (pas de dérive) ; si on a pris du retard on repart de maintenant
            next_beat += HEARTBEAT_PERIOD
            delay = next_beat - time.monotonic()
            if delay <= 0:
                next_beat = time.monotonic()
                delay = 0
            time.sleep(delay)
    
    def _receive_loop(self):
        """Boucle tournant en arrière-plan pour traiter les retours de l'ESP."""
        print("[MOTORS] 🎧 Thread d'écoute démarré.")
        while self.running:
            try:
                # readline bloquant (timeout série) : réveil dès qu'une ligne arrive, sans polling
                ligne = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if ligne:
                    self._process_message(ligne)
            except Exception as e:
                print(f"[MOTORS] Exception in rx loop: {e}")
                time.sleep(0.05) # Évite une boucle à vide si le port est en erreur

    def _process_message(self, msg):
        """Déchiffre le message et met à jour l'état partagé du robot."""
        # print(f"[MOTORS] <- {msg}") # Décommenter pour le debug
        self.last_rx_time = time.time()
        
        if msg.startswith("T "):
            try:
                parts = msg.split()
                if len(parts) == 4:
                    x, y, theta = float(parts[1]), float(parts[2]), float(parts[3])
                    last = self._last_pose
                    if last is None or abs(x - last[0]) > 0.5 or abs(y - last[1]) > 0.5 or abs(theta - last[2]) > 0.2:
                        self.last_motion_time = time.time()
                    self._last_pose = (x, y, theta)
                    # Pose fusionnée (repère table) pour l'IHM et la stratégie
                    t = time.time()
                    shared.loc_log.write("o", t, x, y, theta)
                    tx, ty, ttheta = shared.loc.on_odom(t, x, y, theta)
                    shared.robot_pos.update({'x': tx, 'y': ty, 'theta': ttheta})
            except ValueError:
                print(f"[MOTORS] ⚠️ Erreur de parsing Odométrie : {msg}")
        elif msg.startswith(("D ", "A ")):
            # Fin du GoTo n° id : D = terminé, A = annulé (H, V, nouveau G, obstacle persistant...)
            try:
                goto_id = int(msg[2:])
            except ValueError:
                print(f"[MOTORS] ⚠️ Trame illisible : {msg}")
                return
            with self._goto_lock:
                waiter = self._goto_waiters.get(goto_id)
            if waiter is not None:  # sinon : GoTo déjà abandonné côté Rasp, réponse en retard
                waiter["ok"] = msg[0] == "D"
                waiter["event"].set()
        elif msg.startswith("E "):
            # Commande refusée par l'ESP : visible dans les journaux de l'IHM
            erreur = msg[2:]
            self.errors = (self.errors + [erreur])[-20:]
            print(f"[MOTORS] ❌ ESP : {erreur}")
            if hasattr(shared, "send_log"):
                shared.send_log(f"ESP moteurs : {erreur}", "err")
        elif msg == "W":
            # L'ESP n'a rien reçu pendant 300 ms : moteurs coupés, GoTo annulé (un "A id" suit
            # si un GoTo tournait). Rien ne reprend seul : il faut renvoyer une commande.
            self.watchdog_count += 1
            self.watchdog_tripped = True
            self.last_watchdog_time = time.time()
            print(f"[MOTORS] ⚠️ WATCHDOG ESP : liaison Rasp perdue > 300 ms, moteurs arrêtés "
                  f"(n°{self.watchdog_count}). Nouvelle commande nécessaire pour repartir.")