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
            
            if cmd_type == "set_team":
                new_team = payload.get("team")
                if new_team:
                    shared.state["team"] = new_team
                    if new_team == 'JAUNE':
                        shared.send_led_cmd("COLOR:255,160,0")
                    else:
                        shared.send_led_cmd("COLOR:0,0,255")
                    
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

            elif cmd_type == "config_edit":
                key = payload.get("key")
                val = payload.get("val")
                if key and val is not None:
                    shared.state[key] = val
                    if key == "ekf_enabled":
                        shared.ekf_enabled = val
                    if "config" in shared.state:
                        conf = shared.state["config"]
                        keys = key.split('.')
                        current_level = conf
                        for k in keys[:-1]:
                            if k not in current_level or not isinstance(current_level[k], dict):
                                current_level[k] = {}
                            current_level = current_level[k]
                        current_level[keys[-1]] = val
                        shared.state["config"] = conf
                        shared.save_config(conf)

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
                state_data = {
                    "match_running": shared.state.get("match_running", False),
                    "match_finished": shared.state.get("match_finished", False),
                    "score_current": shared.state.get("score_current", 0),
                    "team": shared.state.get("team", "BLEUE"),
                    "timer_str": shared.state.get("timer_str", "100.0"),
                    "fsm_state": shared.state.get("fsm_state", "INIT"),
                    "telemetry": {
                        "x": shared.robot_pos.get("x", 0.0),
                        "y": shared.robot_pos.get("y", 0.0),
                        "theta": shared.robot_pos.get("theta", 0.0),
                        "voltage": shared.state.get("voltage", 0.0),
                        "current": shared.state.get("current", 0.0),
                        "tirette": shared.state.get("tirette", "WAIT_INSERT"),
                        "imu_yaw": 0.0
                    }
                }
                from utils import get_voltage_float, get_battery_current
                try:
                    state_data["telemetry"]["voltage"] = get_voltage_float()
                    state_data["telemetry"]["current"] = get_battery_current()
                except:
                    pass

                self.send_event("state_update", state_data)
            except Exception as e:
                print(f"[ZMQ CLIENT] Erreur boucle d'envoi : {e}")
            time.sleep(0.1)
