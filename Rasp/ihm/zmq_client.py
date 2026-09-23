import zmq
import json
import threading
import time
import ihm.shared as shared

class ZmqClient(threading.Thread):
    def __init__(self, server_ip="127.0.0.1"):
        super().__init__()
        self.daemon = True
        self.server_ip = server_ip
        
        self.context = zmq.Context()
        # ZMQ PUSH to push telemetry and updates up to the server
        self.push_socket = self.context.socket(zmq.PUSH)
        self.push_socket.connect(f"tcp://{server_ip}:5555")
        
        # ZMQ SUB to receive commands down from the server
        self.sub_socket = self.context.socket(zmq.SUB)
        self.sub_socket.connect(f"tcp://{server_ip}:5556")
        self.sub_socket.setsockopt_string(zmq.SUBSCRIBE, "")
        
        self.running = True
        self.last_sent_state = {}

    def run(self):
        print(f"[ZMQ CLIENT] Démarrage... PUSH -> {self.server_ip}:5555, SUB -> {self.server_ip}:5556")
        
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

            print(f"[ZMQ CLIENT] Commande reçue : {cmd_type} -> {payload}")
            
            if cmd_type == "config_update":
                if payload:
                    shared.update_config_from_server(payload)
                    
            elif cmd_type == "action":
                act = payload
                if act == "start":
                    if shared.state.get("fsm_state") in ("STOPPED", "FINISHED"):
                        shared.state["fsm_state"] = "WAIT_START"
                        shared.state["timer_str"] = "100.0"
                        shared.state["match_finished"] = False
                    shared.state["match_running"] = True
                    shared.state["start_time"] = time.time()
                elif act == "stop":
                    shared.state["match_running"] = False
                    shared.state["fsm_state"] = "STOPPED"
                    shared.state["tirette"] = "WAIT_INSERT"
                    try:
                        from strat.actions import esp
                        if esp:
                            esp.stop_robot()
                    except Exception as e:
                        pass
                elif act == "reset":
                    shared.state["fsm_state"] = "WAIT_START"
                    shared.state["score_current"] = 0
                    shared.state["timer_str"] = "100.0"
                    shared.state["match_finished"] = False
                    shared.state["match_running"] = False
                    shared.state["tirette"] = "WAIT_INSERT"
                elif act == "tirette":
                    shared.state["tirette"] = "TRIGGERED"
                    shared.state["match_running"] = True
                    shared.state["start_time"] = time.time()
                elif act == "init":
                    print("[ZMQ CLIENT] Action INIT reçue (Pose match)")
                    try:
                        from strat.actions import actionneurs
                        if actionneurs:
                            threading.Thread(target=actionneurs.pose_match, daemon=True).start()
                    except Exception as e:
                        print(f"[ZMQ CLIENT] Erreur action init : {e}")

            elif cmd_type == "update_score":
                score = payload.get("score_current", 0)
                shared.state["score_current"] = score

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
                    from strat.actions import RobotActions
                    x = float(payload.get("x", 0))
                    y = float(payload.get("y", 0))
                    theta = float(payload.get("theta", 0))
                    print(f"[ZMQ CLIENT] GOTO command -> ({x}, {y}, {theta})")
                    actions = RobotActions()
                    actions.goto(x, y, theta, manual=True)
                except Exception as e:
                    print(f"[ZMQ CLIENT] Erreur exécution goto : {e}")

            elif cmd_type == "set_robot_pos":
                try:
                    x = float(payload.get("x", 0))
                    y = float(payload.get("y", 0))
                    theta = float(payload.get("theta", 0))
                    print(f"[ZMQ CLIENT] SET_POS command -> ({x}, {y}, {theta})")
                    from strat.actions import esp
                    shared.robot_pos["x"] = x
                    shared.robot_pos["y"] = y
                    shared.robot_pos["theta"] = theta
                    if esp:
                        esp.set_pos(x, y, theta)
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

    def send_event(self, event_type, event_data):
        try:
            packet = {
                "type": event_type,
                "data": event_data
            }
            self.push_socket.send_json(packet, zmq.NOBLOCK)
        except Exception as e:
            pass

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
                try:
                    from utils.system_info import get_voltage_float, get_battery_current, get_ip
                    telemetry_data["voltage"] = get_voltage_float()
                    try:
                        telemetry_data["current"] = float(get_battery_current())
                    except:
                        telemetry_data["current"] = 0.0
                    telemetry_data["rasp_ip"] = get_ip()
                except Exception as e:
                    telemetry_data["rasp_ip"] = "Err"

                self.send_event("telemetry", telemetry_data)

                # 2. Envoi de l'état de contrôle uniquement s'il y a un changement
                current_state = {
                    "match_running": shared.state.get("match_running", False),
                    "match_finished": shared.state.get("match_finished", False),
                    "score_current": shared.state.get("score_current", 0),
                    "timer_str": shared.state.get("timer_str", "100.0"),
                    "fsm_state": shared.state.get("fsm_state", "INIT"),
                    "obstacle_detected": shared.state.get("obstacle_detected", False),
                    "obstacle_type": shared.state.get("obstacle_type", 0)
                }

                if current_state != self.last_sent_state:
                    # Envoi uniquement des champs modifiés pour éviter les écrasements concurrents (ex: couleur équipe)
                    diff_state = {}
                    for k, v in current_state.items():
                        if k not in self.last_sent_state or self.last_sent_state[k] != v:
                            diff_state[k] = v
                    if diff_state:
                        self.send_event("state_update", diff_state)
                    self.last_sent_state = current_state.copy()

            except Exception as e:
                print(f"[ZMQ CLIENT] Erreur boucle d'envoi : {e}")
            time.sleep(0.1)
