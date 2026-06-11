from typing import cast
import serial
import threading
import time
import ihm.shared as shared  # On importe ton shared pour y stocker X, Y, Theta


class ESPActionneurs:
    def __init__(self, port="/dev/esp_action", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser: serial.Serial | None = None

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
            self.rx_thread = threading.Thread(
                target=self._receive_loop, daemon=True, name="ESP_Rx_Thread"
            )
            self.rx_thread.start()

        except serial.SerialException as e:
            print(
                f"[ACTIONNEURS] ❌ Erreur critique : Impossible d'ouvrir {self.port} -> {e}"
            )

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
                self.ser.write(msg.encode("utf-8"))
                # print(f"[ACTIONNEURS] -> {cmd}") # Décommenter pour le debug
            except Exception as e:
                print(f"[ACTIONNEURS] ❌ Erreur d'envoi : {e}")

    def init_robot(self):
        self.send("I")
        # Attend que l'ESP ait fini et que le flag soit levé
        # self.cmd_done_event.wait(timeout=5.0)
        # if not self.cmd_done_event.is_set():
        #      print("[ACTIONNEURS] ❌ Timeout - L'ESP n'a pas répondu à temps.")
        #      return False

        # # On reset le flag pour la prochaine commande
        # self.cmd_done_event.clear()
        # return True

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

    def pose_match(self):
        self.init_robot()
        self.pose_camera()

    def pose_camera(self):
        self.ascenseur(1, 170)
        self.ascenseur(2, 170)
        self.ascenseur(3, 170)
        self.ascenseur(4, 170)

        self.pivoter(1, 1)
        self.pivoter(4, 1)
        self.pivoter(2, 1)
        self.pivoter(3, 1)

        self.grab(1)
        self.grab(2)
        self.grab(3)
        self.grab(4)

        # self.send("C")

        # self.cmd_done_event.wait(timeout=5.0)
        # if not self.cmd_done_event.is_set():
        #      print("[ACTIONNEURS] ❌ Timeout - L'ESP n'a pas répondu à temps.")
        #      return False

        # # On reset le flag pour la prochaine commande
        # self.cmd_done_event.clear()
        # return True

    def pose_ranger(self):
        self.ascenseur(1, 0)
        self.ascenseur(2, 0)
        self.ascenseur(3, 0)
        self.ascenseur(4, 0)

        self.pivoter(1, 1)
        self.pivoter(4, 1)
        self.pivoter(2, 1)
        self.pivoter(3, 1)

        self.grab(1)
        self.grab(2)
        self.grab(3)
        self.grab(4)

        # self.send("C")

        # self.cmd_done_event.wait(timeout=5.0)
        # if not self.cmd_done_event.is_set():
        #      print("[ACTIONNEURS] ❌ Timeout - L'ESP n'a pas répondu à temps.")
        #      return False

        # # On reset le flag pour la prochaine commande
        # self.cmd_done_event.clear()
        # return True

    def pose_deploy(self):
        self.ascenseur(1, 100)
        self.ascenseur(2, 100)
        self.ascenseur(3, 100)
        self.ascenseur(4, 100)

        self.pivoter(2, 0)
        self.pivoter(3, 0)
        self.pivoter(1, 0)
        self.pivoter(4, 0)

        self.release(1)
        self.release(2)
        self.release(3)
        self.release(4)

        # self.send("C")

        # self.cmd_done_event.wait(timeout=5.0)
        # if not self.cmd_done_event.is_set():
        #      print("[ACTIONNEURS] ❌ Timeout - L'ESP n'a pas répondu à temps.")
        #      return False

        # # On reset le flag pour la prochaine commande
        # self.cmd_done_event.clear()
        # return True

    def pose_grab(self):
        self.ascenseur(1, 0)
        self.ascenseur(2, 0)
        self.ascenseur(3, 0)
        self.ascenseur(4, 0)

        self.grab(1)
        self.grab(2)
        self.grab(3)
        self.grab(4)

        # self.send("C")

        # self.cmd_done_event.wait(timeout=5.0)
        # if not self.cmd_done_event.is_set():
        #      print("[ACTIONNEURS] ❌ Timeout - L'ESP n'a pas répondu à temps.")
        #      return False

        # # On reset le flag pour la prochaine commande
        # self.cmd_done_event.clear()
        # return True

    def pose_retourne(self, actionneur_ids):
        self.ascenseur(1, 100)
        self.ascenseur(2, 100)
        self.ascenseur(3, 100)
        self.ascenseur(4, 100)

        self.pivoter(1, 1)
        self.pivoter(4, 1)
        self.pivoter(2, 1)
        self.pivoter(3, 1)

        for actionneur_id in actionneur_ids:
            self.tourner(actionneur_id)

        self.pivoter(2, 0)
        self.pivoter(3, 0)
        self.pivoter(1, 0)
        self.pivoter(4, 0)

        # self.send("C")

        # self.cmd_done_event.wait(timeout=5.0)
        # if not self.cmd_done_event.is_set():
        #      print("[ACTIONNEURS] ❌ Timeout - L'ESP n'a pas répondu à temps.")
        #      return False

        # # On reset le flag pour la prochaine commande
        # self.cmd_done_event.clear()
        # return True

    def pose_poser(self):
        self.ascenseur(1, 0)
        self.ascenseur(2, 0)
        self.ascenseur(3, 0)
        self.ascenseur(4, 0)

        self.release(1)
        self.release(2)
        self.release(3)
        self.release(4)

        # self.send("C")

        # self.cmd_done_event.wait(timeout=5.0)
        # if not self.cmd_done_event.is_set():
        #      print("[ACTIONNEURS] ❌ Timeout - L'ESP n'a pas répondu à temps.")
        #      return False

        # # On reset le flag pour la prochaine commande
        # self.cmd_done_event.clear()
        # return True

    def pose_temperature(self, is_yellow):
        if is_yellow:
            self.ascenseur(4, 170)
            self.pivoter(4, 1)
            self.release(4)
            self.ascenseur(4, 100)
        else:
            self.ascenseur(1, 170)
            self.pivoter(1, 1)
            self.release(1)
            self.ascenseur(1, 100)

    # --- Tâche de fond (Thread) ---

    def _receive_loop(self):
        """Boucle tournant en arrière-plan pour traiter les retours de l'ESP."""
        print("[ACTIONNEURS] 🎧 Thread d'écoute démarré.")
        while self.running:
            try:
                ser = cast(serial.Serial, self.ser)
                if ser.in_waiting > 0:
                    ligne = ser.readline().decode("utf-8", errors="ignore").strip()
                    if ligne:
                        self._process_message(ligne)
            except Exception as e:
                print(f"[ACTIONNEURS] Exception in rx loop: {e}")
                # Évite que le thread ne crash silencieusement en cas de bruit série
                pass

            time.sleep(0.005)  # Petite pause pour ne pas manger 100% du CPU

    def _process_message(self, msg):
        """Déchiffre le message et met à jour l'état partagé du robot."""
        print(f"[ACTIONNEURS] <- {msg}")  # Décommenter pour le debug
        if msg == "D":
            self.cmd_done_event.set()
        elif msg == "E":
            self.cmd_done_event.set()
            self.cmd_aborted = True
            print("[ACTIONNEURS] ❌ Erreur d'init")
        pass
