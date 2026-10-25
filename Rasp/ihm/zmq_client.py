import os
import zmq
import json
import threading
import time
import ihm.shared as shared
from utils.system_info import get_voltage_float, get_battery_current, get_ip

def _read_code_version():
    """Contenu du fichier VERSION écrit au déploiement (tools/deploy.sh, /api/update_rasp)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION")
    try:
        with open(path, encoding="utf-8") as f:
            return dict(line.strip().split("=", 1) for line in f if "=" in line)
    except OSError:
        return {"commit": "inconnu"}


class ZmqClient(threading.Thread):
    def __init__(self, server_ip="127.0.0.1"):
        super().__init__()
        self.daemon = True
        self.server_ip = server_ip
        
        self.context = zmq.Context()
        # ZMQ PUSH to push telemetry and updates up to the server
        self.push_socket = self.context.socket(zmq.PUSH)
        self.push_port = os.environ.get("STK_ZMQ_ROBOT_PORT", "5555")  # mêmes variables que la base
        self.sub_port = os.environ.get("STK_ZMQ_BASE_PORT", "5556")
        self.push_socket.connect(f"tcp://{server_ip}:{self.push_port}")
        # 3. Verrou pour assurer la thread-safety du socket PUSH partagé
        self.push_lock = threading.Lock()
        
        # ZMQ SUB to receive commands down from the server
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(f"tcp://{server_ip}:{self.sub_port}")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        
        self.running = True
        self.last_sent_state = {}
        self.last_publish_time = 0.0
        self.force_publish = True
        self.code_version = _read_code_version()
        # IP mise en cache : get_ip() ouvre des sockets, inutile de l'appeler à 10 Hz
        self._cached_ip = None
        self._cached_ip_time = 0.0

    def run(self):
        print(f"[ZMQ CLIENT] Démarrage... PUSH -> {self.server_ip}:{self.push_port}, SUB -> {self.server_ip}:{self.sub_port}")
        
        # Lancement du thread d'envoi périodique de l'état (telemetry + state)
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.sender_thread.start()
        
        while self.running:
            try:
                if self.sub_socket.poll(timeout=1000):
                    msg = self.sub_socket.recv_string()
                    self._handle_msg(msg)
            except Exception as e:
                print(f"[ZMQ CLIENT] Erreur réception : {e}")
                time.sleep(1)

    def _handle_msg(self, msg_str):
        try:
            packet = json.loads(msg_str)
            cmd_type = packet.get("type")
            payload = packet.get("payload")
            if not cmd_type:
                return

            # Diagnostic du lien base <-> robot (Base/Web/robotping.go) : réponse immédiate, sans log
            if cmd_type == "ping":
                self.send_event("pong", payload)
                return

            # cmd_vel (20 Hz) et vision_pose (cadence caméra) : ne pas les afficher (chaque print repart en new_log vers l'IHM)
            if cmd_type not in ("cmd_vel", "vision_pose"):
                print(f"[ZMQ CLIENT] Commande reçue : {cmd_type} -> {payload}")
            
            if cmd_type in ("config_update", "config_edit"):
                # config_update : {clé: valeur, ...} ; config_edit : {"key": "a.b", "val": v}
                if isinstance(payload, dict) and "key" in payload and "val" in payload:
                    payload = {payload["key"]: payload["val"]}
                if payload:
                    _, err = shared.update_config_from_server(payload)
                    if err:
                        shared.send_log(f"Réglage refusé : {err}", "err")
                    self.force_publish = True

            elif cmd_type == "action":
                # L'état du match n'est modifié que par shared.match (core/match_state.py)
                act = payload
                try:
                    if act in ("start", "tirette"):
                        shared.match.start()
                    elif act == "stop":
                        shared.match.stop()
                    elif act == "reset":
                        shared.match.reset()
                    elif act == "team":
                        shared.match.toggle_team()
                except shared.MatchError as e:
                    print(f"[ZMQ CLIENT] Action {act} refusée : {e}")
                    shared.send_log(f"Action {act} refusée : {e}", "err")
                self.force_publish = True
                if act == "init":
                    print("[ZMQ CLIENT] Action INIT reçue (Pose match)")
                    try:
                        from strat.actions import actionneurs
                        if actionneurs:
                            threading.Thread(target=actionneurs.pose_match, daemon=True).start()
                    except Exception as e:
                        print(f"[ZMQ CLIENT] Erreur action init : {e}")


            elif cmd_type == "cmd_vel":
                try:
                    vx = float(payload.get("vx", payload.get("v", 0.0)))
                    vtheta = float(payload.get("vtheta", payload.get("w", 0.0)))
                    from strat.actions import esp
                    if esp:
                        esp.set_speed(vx, vtheta)
                except Exception as e:
                    print(f"[ZMQ CLIENT] Erreur cmd_vel : {e}")

            elif cmd_type == "cmd_actuator":
                try:
                    from strat.actions import actionneurs
                    if not actionneurs:
                        print("[ZMQ CLIENT] ⚠️ Actionneurs non disponibles (mode simulation)")
                    else:
                        act_cmd = payload.get("cmd") if isinstance(payload, dict) else str(payload)
                        print(f"[ZMQ CLIENT] 🦾 Ordre Actionneur : {act_cmd} ({payload})")
                        
                        # Presets globaux (lancés dans un thread dédié pour ne jamais bloquer la boucle ZMQ)
                        if act_cmd == "pose_match":
                            threading.Thread(target=actionneurs.pose_match, daemon=True).start()
                        elif act_cmd == "pose_camera":
                            threading.Thread(target=actionneurs.pose_camera, daemon=True).start()
                        elif act_cmd == "pose_ranger":
                            threading.Thread(target=actionneurs.pose_ranger, daemon=True).start()
                        elif act_cmd == "pose_deploy":
                            threading.Thread(target=actionneurs.pose_deploy, daemon=True).start()
                        elif act_cmd == "pose_grab":
                            threading.Thread(target=actionneurs.pose_grab, daemon=True).start()
                        elif act_cmd == "pose_poser":
                            threading.Thread(target=actionneurs.pose_poser, daemon=True).start()
                        elif act_cmd == "init" or act_cmd == "init_robot":
                            threading.Thread(target=actionneurs.init_robot, daemon=True).start()
                        elif act_cmd == "pose_temperature":
                            is_yellow = shared.state.get("team") == "JAUNE"
                            threading.Thread(target=actionneurs.pose_temperature, args=(is_yellow,), daemon=True).start()
                        
                        # Contrôles unitaires
                        elif act_cmd == "ascenseur":
                            act_id = int(payload.get("id", 1))
                            hauteur = int(payload.get("hauteur", payload.get("height", 0)))
                            actionneurs.ascenseur(act_id, hauteur)
                        elif act_cmd == "grab":
                            act_id = int(payload.get("id", 1))
                            actionneurs.grab(act_id)
                        elif act_cmd == "release":
                            act_id = int(payload.get("id", 1))
                            actionneurs.release(act_id)
                        elif act_cmd == "grab_all":
                            for i in range(1, 5):
                                actionneurs.grab(i)
                        elif act_cmd == "release_all":
                            for i in range(1, 5):
                                actionneurs.release(i)
                        elif act_cmd == "pivoter":
                            act_id = int(payload.get("id", 1))
                            sens = int(payload.get("sens", 0))
                            actionneurs.pivoter(act_id, sens)
                        elif act_cmd == "tourner":
                            act_id = int(payload.get("id", 1))
                            actionneurs.tourner(act_id)
                        elif act_cmd == "raw":
                            raw_cmd = str(payload.get("raw", ""))
                            if raw_cmd:
                                actionneurs.send(raw_cmd)
                except Exception as e:
                    print(f"[ZMQ CLIENT] Erreur cmd_actuator : {e}")

            elif cmd_type == "goto":
                try:
                    x = float(payload.get("x", 0))
                    y = float(payload.get("y", 0))
                    theta = float(payload.get("theta", 0))
                    print(f"[ZMQ CLIENT] GOTO manuel -> ({x}, {y}, {theta})")
                    # Lancement dans un thread séparé pour ne PAS bloquer la réception ZMQ (traitement immédiat du STOP)
                    threading.Thread(target=self._run_manual_goto, args=(x, y, theta), daemon=True).start()
                except Exception as e:
                    print(f"[ZMQ CLIENT] Erreur lancement goto : {e}")

            elif cmd_type == "vision_pose":
                try:
                    mesure = (time.time(), float(payload["x"]), float(payload["y"]), float(payload["theta"]))
                except (KeyError, TypeError, ValueError):
                    mesure = None
                if mesure:
                    shared.vision_poses.append(mesure)
                    self._fuse_camera(mesure)

            elif cmd_type == "set_robot_pos":
                try:
                    x = float(payload.get("x", 0))
                    y = float(payload.get("y", 0))
                    theta = float(payload.get("theta", 0))
                    print(f"[ZMQ CLIENT] SET_POS command -> ({x}, {y}, {theta})")
                    from strat.actions import esp
                    if esp:
                        esp.set_pos(x, y, theta)  # remet aussi la fusion à zéro
                    else:
                        shared.set_known_pose(x, y, theta)
                except Exception as e:
                    print(f"[ZMQ CLIENT] Erreur set_robot_pos : {e}")

            elif cmd_type == "play_audio":
                try:
                    filename = payload.get("filename") or payload
                    shared.audio.play(filename)
                except Exception as e:
                    print(f"[ZMQ CLIENT] Erreur play_audio : {e}")

            elif cmd_type == "stop_audio":
                try:
                    shared.audio.stop()
                except Exception as e:
                    print(f"[ZMQ CLIENT] Erreur stop_audio : {e}")

            elif cmd_type == "set_volume":
                try:
                    vol = int(payload.get("volume", 50))
                    shared.audio.set_volume(vol)
                except Exception as e:
                    print(f"[ZMQ CLIENT] Erreur set_volume : {e}")

        except Exception as e:
            print(f"[ZMQ CLIENT] Erreur traitement message : {e}")

    def _fuse_camera(self, mesure):
        """Pose caméra zénithale -> correction continue de la pose (core/localisation.py)."""
        from core import frames
        repere = shared.cfg.get("vision_odom", {}).get("repere", {})
        x, y, theta = frames.apply_camera_repere(mesure[1], mesure[2], mesure[3], repere)
        shared.loc_log.write("c", mesure[0], x, y, theta)
        if not shared.loc.enabled() or shared.loc.pose() is None:
            return
        if shared.loc.on_camera(mesure[0], x, y, theta)["ok"]:
            shared.refresh_robot_pos()

    def _run_manual_goto(self, x, y, theta):
        try:
            from strat.actions import esp
            if esp:
                # Coordonnées manuelles absolues : pas de symétrie JAUNE et pas d'écrasement de is_returning
                esp.goto(x, y, theta, manual=True)
            else:
                print(f"[ZMQ CLIENT] GOTO simulé ({x}, {y}, {theta})")
        except Exception as e:
            print(f"[ZMQ CLIENT] Erreur exécution goto manuel : {e}")

    def send_event(self, event_type, event_data):
        try:
            packet = {
                "type": event_type,
                "data": event_data
            }
            with self.push_lock:
                self.push_socket.send_json(packet, zmq.NOBLOCK)
        except zmq.Again:
            pass
        except Exception as e:
            print(f"[ZMQ CLIENT] Erreur send_event ({event_type}): {e}")

    def _sender_loop(self):
        while self.running:
            try:
                # 1. Envoi de la télémétrie à 10Hz
                telemetry_data = {
                    "x": shared.robot_pos.get("x", 0.0),
                    "y": shared.robot_pos.get("y", 0.0),
                    "theta": shared.robot_pos.get("theta", 0.0),
                    "voltage": shared.state.get("voltage", 0.0),
                    "current": shared.state.get("current", 0.0),
                    "tirette": shared.state.get("tirette", "WAIT_INSERT"),
                    "imu_yaw": 0.0
                }
                telemetry_data["voltage"] = get_voltage_float()
                try:
                    telemetry_data["current"] = float(get_battery_current())
                except Exception:
                    telemetry_data["current"] = 0.0
                now = time.time()
                if self._cached_ip is None or now - self._cached_ip_time >= 5.0:
                    try:
                        self._cached_ip = get_ip()
                    except Exception:
                        self._cached_ip = "Err"
                    self._cached_ip_time = now
                telemetry_data["rasp_ip"] = self._cached_ip

                self.send_event("telemetry", telemetry_data)

                # 2. État du robot (source de vérité) : instantané complet, envoyé à chaque
                #    changement et toutes les 2 s (la base se resynchronise après un redémarrage)
                snapshot = shared.match.snapshot()
                snapshot["obstacle_detected"] = shared.state.get("obstacle_detected", False)
                snapshot["obstacle_type"] = shared.state.get("obstacle_type", 0)
                if (self.force_publish or snapshot != self.last_sent_state
                        or now - self.last_publish_time >= 2.0):
                    self.force_publish = False
                    self.last_sent_state = snapshot
                    self.last_publish_time = now
                    self.send_event("robot_state", {
                        "state": snapshot,
                        "config": shared.config_store.snapshot(),
                        "version": self.code_version,
                    })

            except Exception as e:
                print(f"[ZMQ CLIENT] Erreur boucle d'envoi : {e}")
            time.sleep(0.1)
