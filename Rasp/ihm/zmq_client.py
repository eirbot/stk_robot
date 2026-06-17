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

            elif cmd_type == "update_score":
                score = payload.get("score_current", 0)
                shared.state["score_current"] = score

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
                    from utils.system_info import get_voltage_float, get_battery_current
                    telemetry_data["voltage"] = get_voltage_float()
                    telemetry_data["current"] = get_battery_current()
                except Exception as e:
                    pass

                self.send_event("telemetry", telemetry_data)

                # 2. Envoi de l'état de contrôle uniquement s'il y a un changement
                current_state = {
                    "match_running": shared.state.get("match_running", False),
                    "match_finished": shared.state.get("match_finished", False),
                    "score_current": shared.state.get("score_current", 0),
                    "timer_str": shared.state.get("timer_str", "100.0"),
                    "fsm_state": shared.state.get("fsm_state", "INIT")
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
