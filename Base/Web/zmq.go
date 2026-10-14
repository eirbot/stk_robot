package main

import (
	"encoding/json"
	"fmt"
	"strings"
	"sync"

	zmq "github.com/pebbe/zmq4"
)

// Thread de réception des capteurs (Robot -> PC)
func pipelineReceptionRobot() {
	receiver, _ := zmq.NewSocket(zmq.PULL)
	defer receiver.Close()
	// Le PC ouvre le port de réception
	receiver.Bind("tcp://*:5555")
	fmt.Println("[ZMQ PULL] En attente de la télémétrie du robot (Port 5555)...")

	for {
		msg, err := receiver.Recv(0)
		if err != nil {
			continue
		}

		var msgObj RobotMessage
		isGeneric := true
		if err := json.Unmarshal([]byte(msg), &msgObj); err != nil {
			isGeneric = false
		}

		if isGeneric {
			if msgObj.Type == "telemetry" {
				var tel RobotTelemetry
				if err := json.Unmarshal(msgObj.Data, &tel); err == nil {
					globalState.Lock()
					prevTirette := globalState.Telemetry.Tirette
					// IP invalide : on garde la précédente (la goroutine DHCP de main.go la tient à jour).
					// Pas de lecture des baux DHCP ici : on est sous verrou, à 10 Hz.
					if !isValidIP(tel.RaspIP) {
						tel.RaspIP = globalState.Telemetry.RaspIP
					}
					globalState.Telemetry = tel

					// 1. Détection FRONT : uniquement transition ARMED -> TRIGGERED et match non fini/non stoppé
					if prevTirette == "ARMED" && tel.Tirette == "TRIGGERED" &&
						!globalState.MatchRunning && !globalState.MatchFinished &&
						globalState.FsmState != "FINISHED" && globalState.FsmState != "STOPPED" {
						globalState.MatchRunning = true
						globalState.FsmState = "RUNNING"
					}

					// Allègement trame : pour la télémétrie haute fréquence (10Hz),
					// on n'embarque pas le dictionnaire Config complet (économise ~88% de bande passante et CPU client)
					packet, _ := json.Marshal(map[string]interface{}{
						"type": "state_update",
						"data": map[string]interface{}{
							"match_running":     globalState.MatchRunning,
							"match_finished":    globalState.MatchFinished,
							"score_current":     globalState.ScoreCurrent,
							"team":              globalState.Team,
							"timer_str":         globalState.TimerStr,
							"fsm_state":         globalState.FsmState,
							"obstacle_detected": globalState.ObstacleDetected,
							"obstacle_type":     globalState.ObstacleType,
							"telemetry":         globalState.Telemetry,
							"vision_pose":       globalState.VisionPose,
						},
					})
					globalState.Unlock()

					globalHub.Broadcast(packet)
				} else {
					fmt.Printf("[ZMQ] Erreur décodage télémétrie: %v\n", err)
				}
			} else if msgObj.Type == "vision_update" {
				// 8. Télémétrie Caméra Zénithale isolée de l'odométrie roues
				var vPose VisionPose
				if err := json.Unmarshal(msgObj.Data, &vPose); err == nil {
					globalState.Lock()
					globalState.VisionPose = vPose
					globalState.Unlock()

					packet, _ := json.Marshal(map[string]interface{}{
						"type": "vision_update",
						"data": vPose,
					})
					globalHub.Broadcast(packet)
				}
			} else if msgObj.Type == "state_update" {
				var update StateUpdate
				if err := json.Unmarshal(msgObj.Data, &update); err == nil {
					globalState.Lock()
					prevTirette := globalState.Telemetry.Tirette
					if update.MatchRunning != nil {
						globalState.MatchRunning = *update.MatchRunning
					}
					if update.MatchFinished != nil {
						globalState.MatchFinished = *update.MatchFinished
					}
					if update.ScoreCurrent != nil {
						globalState.ScoreCurrent = *update.ScoreCurrent
					}
					if update.Team != nil {
						globalState.Team = *update.Team
					}
					if update.TimerStr != nil {
						globalState.TimerStr = *update.TimerStr
					}
					if update.FsmState != nil {
						globalState.FsmState = *update.FsmState
					}
					if update.ObstacleDetected != nil {
						globalState.ObstacleDetected = *update.ObstacleDetected
					}
					if update.ObstacleType != nil {
						globalState.ObstacleType = *update.ObstacleType
					}
					if update.Telemetry != nil {
						globalState.Telemetry = *update.Telemetry
					} else {
						if update.X != nil {
							globalState.Telemetry.X = *update.X
						}
						if update.Y != nil {
							globalState.Telemetry.Y = *update.Y
						}
						if update.Theta != nil {
							globalState.Telemetry.Theta = *update.Theta
						}
						if update.Voltage != nil {
							globalState.Telemetry.Voltage = *update.Voltage
						}
						if update.Current != nil {
							globalState.Telemetry.Current = *update.Current
						}
						if update.Tirette != nil {
							globalState.Telemetry.Tirette = *update.Tirette
						}
						if update.IMUYaw != nil {
							globalState.Telemetry.IMUYaw = *update.IMUYaw
						}
						if update.RaspIP != nil && isValidIP(*update.RaspIP) {
							globalState.Telemetry.RaspIP = *update.RaspIP
						}
					}

					// 1. Détection FRONT : uniquement transition ARMED -> TRIGGERED et match non fini/non stoppé
					if prevTirette == "ARMED" && globalState.Telemetry.Tirette == "TRIGGERED" &&
						!globalState.MatchRunning && !globalState.MatchFinished &&
						globalState.FsmState != "FINISHED" && globalState.FsmState != "STOPPED" {
						globalState.MatchRunning = true
						globalState.FsmState = "RUNNING"
					}

					// Paquet allégé (timer_str change toutes les 100 ms en match) :
					// la Config n'est jointe que si le robot l'a modifiée
					data := map[string]interface{}{
						"match_running":     globalState.MatchRunning,
						"match_finished":    globalState.MatchFinished,
						"score_current":     globalState.ScoreCurrent,
						"team":              globalState.Team,
						"timer_str":         globalState.TimerStr,
						"fsm_state":         globalState.FsmState,
						"obstacle_detected": globalState.ObstacleDetected,
						"obstacle_type":     globalState.ObstacleType,
						"telemetry":         globalState.Telemetry,
						"vision_pose":       globalState.VisionPose,
					}
					if update.Config != nil {
						data["config"] = globalState.Config
					}
					packet, _ := json.Marshal(map[string]interface{}{
						"type": "state_update",
						"data": data,
					})
					globalState.Unlock()

					globalHub.Broadcast(packet)
				}
			} else if msgObj.Type == "action" {
				var act string
				if err := json.Unmarshal(msgObj.Data, &act); err == nil {
					globalState.Lock()
					var cfgPayload json.RawMessage
					if act == "team" {
						if globalState.Team == "BLEUE" {
							globalState.Team = "JAUNE"
						} else {
							globalState.Team = "BLEUE"
						}
						if globalState.Config != nil {
							globalState.Config["team"] = globalState.Team
							saveConfigToFile(globalState.Config)
							cfgPayload = getConfigCopyLocked()
						}
					} else if act == "start" {
						globalState.MatchRunning = true
						globalState.FsmState = "RUNNING"
					} else if act == "stop" {
						globalState.MatchRunning = false
						globalState.FsmState = "STOPPED"
					} else if act == "reset" {
						globalState.MatchRunning = false
						globalState.MatchFinished = false
						globalState.ScoreCurrent = 0
						globalState.FsmState = "WAIT_START"
					}
					globalState.Unlock()

					if len(cfgPayload) > 0 {
						envoyerAuRobot("config_update", cfgPayload)
					}
					if act != "team" {
						envoyerAuRobot("action", act)
					}
					broadcastState()
				}
			} else if msgObj.Type == "config_edit" {
				var body map[string]interface{}
				if err := json.Unmarshal(msgObj.Data, &body); err == nil {
					key, okKey := body["key"].(string)
					val, okVal := body["val"]

					if okKey && okVal && val != nil {
						globalState.Lock()
						if globalState.Config == nil {
							globalState.Config = make(map[string]interface{})
						}

						keys := strings.Split(key, ".")
						curr := globalState.Config
						for i := 0; i < len(keys)-1; i++ {
							k := keys[i]
							nextMap, ok := curr[k].(map[string]interface{})
							if !ok {
								newMap := make(map[string]interface{})
								curr[k] = newMap
								curr = newMap
							} else {
								curr = nextMap
							}
						}
						curr[keys[len(keys)-1]] = val

						if key == "team" {
							if strVal, ok := val.(string); ok {
								globalState.Team = strVal
							}
						}

						saveConfigToFile(globalState.Config)
						globalState.Unlock()

						// Ne pas renvoyer config_update au robot : c'est le robot qui vient d'émettre config_edit
						broadcastState()
					}
				}
			} else {
				// Relay any other message types (new_log, sys_info) directly to web clients
				globalHub.Broadcast([]byte(msg))
			}
		} else {
			// Fallback: decode as flat telemetry
			var tel RobotTelemetry
			if err := json.Unmarshal([]byte(msg), &tel); err == nil {
				globalState.Lock()
				prevTirette := globalState.Telemetry.Tirette
				if !isValidIP(tel.RaspIP) {
					tel.RaspIP = globalState.Telemetry.RaspIP
				}
				globalState.Telemetry = tel
				if prevTirette == "ARMED" && tel.Tirette == "TRIGGERED" &&
					!globalState.MatchRunning && !globalState.MatchFinished &&
					globalState.FsmState != "FINISHED" && globalState.FsmState != "STOPPED" {
					globalState.MatchRunning = true
					globalState.FsmState = "RUNNING"
				}
				packet, _ := json.Marshal(map[string]interface{}{
					"type": "state_update",
					"data": map[string]interface{}{
						"match_running":     globalState.MatchRunning,
						"match_finished":    globalState.MatchFinished,
						"score_current":     globalState.ScoreCurrent,
						"team":              globalState.Team,
						"timer_str":         globalState.TimerStr,
						"fsm_state":         globalState.FsmState,
						"obstacle_detected": globalState.ObstacleDetected,
						"obstacle_type":     globalState.ObstacleType,
						"telemetry":         globalState.Telemetry,
					},
				})
				globalState.Unlock()

				globalHub.Broadcast(packet)
			}
		}
	}
}

// 4. Verrou mutex pour garantir la thread-safety de zmqPublisher
var zmqPubMutex sync.Mutex

// Envoyer un ordre descendant vers le robot via ZMQ PUB (Thread-Safe)
func envoyerAuRobot(cmdType string, payload interface{}) {
	packet, err := json.Marshal(map[string]interface{}{
		"type":    cmdType,
		"payload": payload,
	})
	if err != nil {
		return
	}
	zmqPubMutex.Lock()
	defer zmqPubMutex.Unlock()
	if zmqPublisher != nil {
		zmqPublisher.Send(string(packet), 0)
	}
}
