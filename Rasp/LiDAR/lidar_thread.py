"""Évitement LiDAR : reçoit les tours du driver C++ (lidar_udp.cpp, UDP 127.0.0.1:8080),
en déduit l'état d'obstacle (core/obstacles.py) et l'envoie à l'ESP moteurs (« L etat »).

Le LiDAR est dans la balise (~430 mm de haut) : il ne voit que les balises des autres robots (et les
gens autour de la table), pas les pierres. Distances = de balise à balise, donc de centre à centre :
`lidar.seuil_mm` (550 : notre avant 245 + corps adverse ~200 + marge) devant / derrière, `lidar.proche_mm`
(420 : demi-largeur 188 + corps adverse + marge) tout autour.

Config `lidar` : `montage` (cf. core/obstacles.py), `filtre_table` (True : points hors de la table
ignorés quand la pose est fiable), `marge_table_mm`. Les points restants (repère table) sont
publiés dans shared.lidar_points pour le planificateur et la boîte noire.

Le thread lance / arrête aussi le driver C++ selon `lidar_mode` (OFF : capteur arrêté).
"""
import socket
import subprocess
import threading
import time

import ihm.shared as shared
from core import obstacles

ESP_REFRESH_S = 0.5     # « L » renvoyé au moins à cette période (sinon seulement sur changement)
LOG_PERIOD_S = 2.0


class LidarCollisionThread(threading.Thread):
    def __init__(self, robot, seuil_mm=550.0, proche_mm=420.0):
        """
        :param robot: RobotActions (envoie « L etat » à l'ESP moteurs)
        :param seuil_mm: distance de déclenchement devant / derrière (mm)
        """
        super().__init__(daemon=True, name="LidarCollision")
        self.robot = robot
        self.detector = obstacles.ObstacleDetector(seuil_mm=seuil_mm, near_mm=proche_mm,
                                                   montage=shared.cfg.get("lidar", {}).get("montage"))
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 8080))
        self.sock.settimeout(2.0)

        self._esp_state = None
        self._esp_state_time = 0.0
        self._last_log = 0.0
        self._publish(obstacles.CLEAR)

    # --- Sorties -------------------------------------------------------------------------
    def _publish(self, state):
        """État pour l'IHM (shared.state) et pour l'ESP (sur changement + rafraîchissement)."""
        if state != shared.state.get("obstacle_type"):
            if state != obstacles.CLEAR:
                print(f"[🛑 OBSTACLE] Type {state} (mode {shared.state.get('lidar_mode')})")
            elif shared.state.get("obstacle_type"):
                print("[✅ LIBRE] Voie libre confirmée")
        shared.state["obstacle_detected"] = state != obstacles.CLEAR
        shared.state["obstacle_type"] = state
        now = time.time()
        if state != self._esp_state or now - self._esp_state_time > ESP_REFRESH_S:
            self.robot.set_lidar_state(state)
            self._esp_state = state
            self._esp_state_time = now

    def _filtrer(self, scan, now):
        """Efface les points hors table (pose fiable seulement) et publie les points restants."""
        cfg = shared.cfg.get("lidar", {})
        montage = cfg.get("montage")
        self.detector.montage = montage
        pose = shared.pose_fiable()
        if pose is not None and cfg.get("filtre_table", True):
            scan = obstacles.filter_outside_table(scan, pose, float(cfg.get("marge_table_mm", 40.0)), montage)
        shared.lidar_points = [(round(x), round(y)) for _, x, y in obstacles.sector_points(scan, pose, montage)] \
            if pose is not None else []
        shared.lidar_points_t = now
        shared.navigateur.observer_lidar(shared.lidar_points, now)
        return scan

    def _send_frame(self, scan):
        """Point le plus proche (et points du tour dans le repère table), pour la carte (map.js), à 5 Hz."""
        if not shared.zmq_client_instance or time.time() - getattr(self, "_last_frame", 0.0) < 0.2:
            return
        self._last_frame = time.time()
        shared.zmq_client_instance.send_event("lidar_frame", {
            "obstacle": {"angle": scan.closest_angle,
                         "distance": scan.closest_dist if scan.closest_dist > 0 else 99999.0},
            "points": shared.lidar_points,
        })

    # --- Driver C++ ------------------------------------------------------------------------
    def _manage_process(self, mode):
        """Driver lancé si le mode n'est pas OFF, arrêté sinon. False si le lancement a échoué."""
        if mode == "OFF":
            if shared.lidar_process is not None:
                print("[LIDAR THREAD] LiDAR sur OFF : arrêt du capteur")
                shared.lidar_process.terminate()
                try:
                    shared.lidar_process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    shared.lidar_process.kill()
                shared.lidar_process = None
        elif shared.lidar_process is None and shared.lidar_bin:
            print("[LIDAR THREAD] LiDAR activé : démarrage du capteur")
            try:
                shared.lidar_process = subprocess.Popen([shared.lidar_bin], preexec_fn=shared.die_with_parent)
            except OSError as e:
                # Binaire absent / corrompu : pas de relance en boucle (CPU à 100 %, journaux saturés)
                print(f"[LIDAR THREAD] Impossible de lancer {shared.lidar_bin} : {e}. Nouvel essai dans 5 s.")
                return False
        return True

    # --- Boucle ------------------------------------------------------------------------------
    def run(self):
        print(f"[LIDAR THREAD] Surveillance démarrée, seuil {self.detector.seuil_mm:.0f} mm")
        while self.running:
            try:
                mode = shared.state.get("lidar_mode", "OFF")
                if not self._manage_process(mode):
                    time.sleep(5)
                    continue
                if mode == "OFF":
                    self.detector.update(None, "OFF", time.time())
                    self._publish(obstacles.CLEAR)
                    time.sleep(0.1)
                    continue

                data, _ = self.sock.recvfrom(1024)
                scan = obstacles.parse_scan(data)
                if scan is None:
                    continue
                now = time.time()
                scan = self._filtrer(scan, now)
                self._send_frame(scan)
                if now - self._last_log > LOG_PERIOD_S and scan.closest_dist > 0:
                    print(f"[LIDAR THREAD] Ping... (obstacle le plus proche à {scan.closest_dist:.0f} mm, "
                          f"{scan.closest_angle:.1f}°)")
                    self._last_log = now
                # Le mode a pu changer pendant l'attente du paquet
                self._publish(self.detector.update(scan, shared.state.get("lidar_mode", "OFF"), now))

            except socket.timeout:
                if shared.state.get("lidar_mode", "OFF") != "OFF":
                    print("[⚠️ ALERTE] Perte de com LiDAR. Arrêt par sécurité.")
                    self._publish(self.detector.on_timeout(time.time()))
            except Exception as e:
                if self.running:
                    print(f"[LIDAR THREAD] Erreur : {e}")
                    time.sleep(0.5)  # pas de boucle d'erreurs à pleine vitesse

    def stop(self):
        self.running = False
        self.sock.close()
