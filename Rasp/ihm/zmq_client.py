import os
import zmq
import json
import threading
import time
import hardware
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
        self._last_refusal = 0.0
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

    # --- Ordres de la base -------------------------------------------------------------
    # Commandes manuelles refusées pendant un match : le robot doit être autonome (règlement),
    # et un joystick oublié annulerait les GoTo de la stratégie.
    MANUAL_COMMANDS = ("cmd_vel", "goto", "set_robot_pos", "cmd_actuator", "calibration")
    # Messages fréquents, non affichés (chaque print repart en new_log vers l'IHM)
    QUIET_COMMANDS = ("ping", "cmd_vel", "vision_pose")

    def _handlers(self):
        return {
            "ping": self._on_ping,
            "config_update": self._on_config,
            "config_edit": self._on_config,
            "action": self._on_action,
            "cmd_vel": self._on_cmd_vel,
            "cmd_actuator": self._on_actuator,
            "goto": self._on_goto,
            "vision_pose": self._on_vision_pose,
            "set_robot_pos": self._on_set_robot_pos,
            "calibration": self._on_calibration,
            "play_audio": lambda p: shared.audio.play(p.get("filename") if isinstance(p, dict) else p),
            "stop_audio": lambda p: shared.audio.stop(),
            "set_volume": lambda p: shared.audio.set_volume(int(p.get("volume", 50))),
            "led_cmd": self._on_led_cmd,
            "led_animations": self._on_led_animations,
        }

    def _handle_msg(self, msg_str):
        try:
            packet = json.loads(msg_str)
        except ValueError:
            print(f"[ZMQ CLIENT] Message illisible : {msg_str[:80]}")
            return
        cmd_type = packet.get("type")
        payload = packet.get("payload")
        handler = self._handlers().get(cmd_type)
        if handler is None:
            if cmd_type:
                print(f"[ZMQ CLIENT] Commande inconnue : {cmd_type}")
            return
        if cmd_type not in self.QUIET_COMMANDS:
            print(f"[ZMQ CLIENT] Commande reçue : {cmd_type} -> {payload}")
        if cmd_type in self.MANUAL_COMMANDS and shared.match.running:
            self._refuse(cmd_type)
            return
        try:
            handler(payload)
        except Exception as e:
            print(f"[ZMQ CLIENT] Erreur {cmd_type} : {e}")

    def _refuse(self, cmd_type):
        """Commande manuelle pendant un match : refusée, signalée au plus toutes les 2 s (cmd_vel à 20 Hz)."""
        now = time.time()
        if now - self._last_refusal >= 2.0:
            self._last_refusal = now
            print(f"[ZMQ CLIENT] {cmd_type} refusé : match en cours")
            shared.send_log(f"Commande manuelle ({cmd_type}) refusée pendant un match", "err")

    def _on_ping(self, payload):
        # Diagnostic du lien base <-> robot (Base/Web/robotping.go)
        self.send_event("pong", payload)

    def _on_config(self, payload):
        # config_update : {clé: valeur, ...} ; config_edit : {"key": "a.b", "val": v}
        if isinstance(payload, dict) and "key" in payload and "val" in payload:
            payload = {payload["key"]: payload["val"]}
        if payload:
            _, err = shared.update_config_from_server(payload)
            if err:
                shared.send_log(f"Réglage refusé : {err}", "err")
            self.force_publish = True

    def _on_action(self, act):
        # L'état du match n'est modifié que par shared.match (core/match_state.py)
        match_actions = {"start": shared.match.start, "tirette": shared.match.start, "stop": shared.match.stop,
                         "reset": shared.match.reset, "team": shared.match.toggle_team}
        try:
            if act in match_actions:
                match_actions[act]()
            elif act == "init" and hardware.actionneurs:
                threading.Thread(target=hardware.actionneurs.pose_match, daemon=True).start()
        except shared.MatchError as e:
            print(f"[ZMQ CLIENT] Action {act} refusée : {e}")
            shared.send_log(f"Action {act} refusée : {e}", "err")
        self.force_publish = True

    def _on_cmd_vel(self, payload):
        if hardware.esp:
            vx = float(payload.get("vx", payload.get("v", 0.0)))
            vtheta = float(payload.get("vtheta", payload.get("w", 0.0)))
            hardware.esp.set_speed(vx, vtheta)

    def _on_actuator(self, payload):
        act = hardware.actionneurs
        if not act:
            print("[ZMQ CLIENT] ⚠️ Actionneurs non disponibles (mode simulation)")
            return
        p = payload if isinstance(payload, dict) else {"cmd": str(payload)}
        cmd = p.get("cmd")
        act_id = int(p.get("id", 1))
        # Séquences : dans un thread, pour ne jamais bloquer la réception (STOP traité aussitôt)
        sequences = {
            "pose_match": act.pose_match, "pose_camera": act.pose_camera, "pose_ranger": act.pose_ranger,
            "pose_deploy": act.pose_deploy, "pose_grab": act.pose_grab, "pose_poser": act.pose_poser,
            "init": act.init_robot, "init_robot": act.init_robot,
            "pose_temperature": lambda: act.pose_temperature(shared.state.get("team") == "JAUNE"),
        }
        # Commandes unitaires : un seul envoi série, immédiat
        unit = {
            "ascenseur": lambda: act.ascenseur(act_id, int(p.get("hauteur", p.get("height", 0)))),
            "grab": lambda: act.grab(act_id),
            "release": lambda: act.release(act_id),
            "grab_all": lambda: [act.grab(i) for i in range(1, 5)],
            "release_all": lambda: [act.release(i) for i in range(1, 5)],
            "pivoter": lambda: act.pivoter(act_id, int(p.get("sens", 0))),
            "tourner": lambda: act.tourner(act_id),
            "raw": lambda: act.send(str(p["raw"])) if p.get("raw") else None,
        }
        print(f"[ZMQ CLIENT] 🦾 Ordre actionneur : {cmd} ({payload})")
        if cmd in sequences:
            threading.Thread(target=sequences[cmd], daemon=True).start()
        elif cmd in unit:
            unit[cmd]()
        else:
            print(f"[ZMQ CLIENT] Ordre actionneur inconnu : {cmd}")

    # Commandes acceptées par le service LED (utils/led_service.py), envoyées par la base
    LED_COMMANDS = ("OFF", "RELOAD", "COLOR:", "PIXEL:", "PLAY:", "BRIGHTNESS:")

    def _on_led_cmd(self, cmd):
        if isinstance(cmd, str) and "\n" not in cmd and cmd.startswith(self.LED_COMMANDS):
            shared.send_led_cmd(cmd)
        else:
            print(f"[ZMQ CLIENT] Commande LED refusée : {cmd!r}")

    def _on_led_animations(self, animations):
        """Animations éditées dans le LED Studio : enregistrées puis rechargées par le service LED."""
        if not isinstance(animations, dict):
            return
        path = os.path.join(shared.ROOT_DIR, "config_led_animations.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(animations, f, indent=4, ensure_ascii=False)
        os.replace(tmp, path)
        shared.send_led_cmd("RELOAD")

    def _on_goto(self, payload):
        x, y, theta = float(payload.get("x", 0)), float(payload.get("y", 0)), float(payload.get("theta", 0))
        # Thread séparé : la réception ZMQ ne doit pas attendre la fin du déplacement (STOP)
        threading.Thread(target=self._run_manual_goto, args=(x, y, theta), daemon=True).start()

    def _on_vision_pose(self, payload):
        try:
            mesure = (time.time(), float(payload["x"]), float(payload["y"]), float(payload["theta"]))
        except (KeyError, TypeError, ValueError):
            return
        shared.vision_poses.append(mesure)
        self._fuse_camera(mesure)
        # Robots adverses vus par la même image (Base/Vision/vision_deporte_worker.py)
        for adv in payload.get("adversaires") or []:
            try:
                shared.noter_adversaire(int(adv["id"]), float(adv["x"]), float(adv["y"]), mesure[0])
            except (KeyError, TypeError, ValueError):
                continue

    def _on_calibration(self, payload):
        """Calibration automatique de la fusion (strat/calibration.py) : start / stop."""
        if shared.robot is None:
            return
        if shared.calibration is None:
            from strat.calibration import Calibration
            shared.calibration = Calibration(shared.robot, shared, hardware)
        shared.calibration.commande(payload)

    def _on_set_robot_pos(self, payload):
        x, y, theta = float(payload.get("x", 0)), float(payload.get("y", 0)), float(payload.get("theta", 0))
        if hardware.esp:
            hardware.esp.set_pos(x, y, theta)  # remet aussi la fusion à zéro
        else:
            shared.set_known_pose(x, y, theta)

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
            if hardware.esp:
                # Coordonnées manuelles absolues : pas de symétrie JAUNE
                hardware.esp.goto(x, y, theta, manual=True)
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
