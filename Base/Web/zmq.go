package main

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"

	zmq "github.com/pebbe/zmq4"
)

// Thread de réception des capteurs (Robot -> PC)
func pipelineReceptionRobot() {
	receiver, _ := zmq.NewSocket(zmq.PULL)
	defer receiver.Close()
	// Le PC ouvre le port de réception
	receiver.Bind("tcp://*:" + zmqRobotPort)
	fmt.Printf("[ZMQ PULL] En attente de la télémétrie du robot (Port %s)...\n", zmqRobotPort)

	var lastVisionBroadcast time.Time
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
		if noteRobotMessage() {
			fmt.Println("[ROBOT] En ligne")
			broadcastState()
		}

		if isGeneric {
			if msgObj.Type == "telemetry" {
				var tel RobotTelemetry
				if err := json.Unmarshal(msgObj.Data, &tel); err == nil {
					globalState.Lock()
					// IP invalide : on garde la précédente (la goroutine DHCP de main.go la tient à jour).
					// Pas de lecture des baux DHCP ici : on est sous verrou, à 10 Hz.
					if !isValidIP(tel.RaspIP) {
						tel.RaspIP = globalState.Telemetry.RaspIP
					}
					globalState.Telemetry = tel


					// Allègement trame : pour la télémétrie haute fréquence (10Hz),
					// on n'embarque pas le dictionnaire Config complet (économise ~88% de bande passante et CPU client)
					packet, _ := json.Marshal(map[string]interface{}{
						"type": "state_update",
						"data": map[string]interface{}{
							"match_running":     globalState.MatchRunning,
							"match_finished":    globalState.MatchFinished,
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

					// Pages web limitées à 10 Hz (la caméra va plus vite) : sinon chaque
					// téléphone connecté parse et redessine à chaque image
					if time.Since(lastVisionBroadcast) >= 100*time.Millisecond || !vPose.Detected {
						lastVisionBroadcast = time.Now()
						packet, _ := json.Marshal(map[string]interface{}{
							"type": "vision_update",
							"data": vPose,
						})
						globalHub.Broadcast(packet)
					}

					// Relais au robot pour le recalage de l'odométrie (robot.recalage_camera)
					if vPose.Detected {
						envoyerAuRobot("vision_pose", vPose)
					}
				}
			} else if msgObj.Type == "state_update" {
				var update StateUpdate
				if err := json.Unmarshal(msgObj.Data, &update); err == nil {
					globalState.Lock()
					if update.MatchRunning != nil {
						globalState.MatchRunning = *update.MatchRunning
					}
					if update.MatchFinished != nil {
						globalState.MatchFinished = *update.MatchFinished
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


					// Paquet allégé (timer_str change toutes les 100 ms en match) :
					// la Config n'est jointe que si le robot l'a modifiée
					data := map[string]interface{}{
						"match_running":     globalState.MatchRunning,
						"match_finished":    globalState.MatchFinished,
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
			} else if msgObj.Type == "robot_state" {
				// Instantané complet publié par le robot (source de vérité) : appliqué tel quel
				var snap RobotSnapshot
				if err := json.Unmarshal(msgObj.Data, &snap); err == nil {
					applyRobotSnapshot(snap)
					broadcastState()
				} else {
					fmt.Printf("[ZMQ] robot_state illisible : %v\n", err)
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
				if !isValidIP(tel.RaspIP) {
					tel.RaspIP = globalState.Telemetry.RaspIP
				}
				globalState.Telemetry = tel
				packet, _ := json.Marshal(map[string]interface{}{
					"type": "state_update",
					"data": map[string]interface{}{
						"match_running":     globalState.MatchRunning,
						"match_finished":    globalState.MatchFinished,
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
