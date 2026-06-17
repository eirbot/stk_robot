package main

import (
	"encoding/json"
	"fmt"
	"strings"
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
					globalState.Telemetry = tel

					// Si la tirette est tirée physiquement sur le robot, on déclenche le départ côté PC
					if tel.Tirette == "TRIGGERED" && !globalState.MatchRunning {
						globalState.MatchRunning = true
						globalState.FsmState = "RUNNING"
					}

					packet, _ := json.Marshal(map[string]interface{}{
						"type": "state_update",
						"data": &globalState,
					})
					globalState.Unlock()

					globalHub.Broadcast(packet)
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
					}

					// Si la tirette est tirée physiquement sur le robot, on déclenche le départ côté PC
					if globalState.Telemetry.Tirette == "TRIGGERED" && !globalState.MatchRunning {
						globalState.MatchRunning = true
						globalState.FsmState = "RUNNING"
					}

					packet, _ := json.Marshal(map[string]interface{}{
						"type": "state_update",
						"data": &globalState,
					})
					globalState.Unlock()

					globalHub.Broadcast(packet)
				}
			} else if msgObj.Type == "action" {
				var act string
				if err := json.Unmarshal(msgObj.Data, &act); err == nil {
					globalState.Lock()
					if act == "team" {
						if globalState.Team == "BLEUE" {
							globalState.Team = "JAUNE"
						} else {
							globalState.Team = "BLEUE"
						}
						if globalState.Config != nil {
							globalState.Config["team"] = globalState.Team
							saveConfigToFile(globalState.Config)
						}
						envoyerAuRobot("config_update", globalState.Config)
					} else if act == "start" {
						globalState.MatchRunning = true
						globalState.FsmState = "RUNNING"
						envoyerAuRobot("action", "start")
					} else if act == "stop" {
						globalState.MatchRunning = false
						globalState.FsmState = "STOPPED"
						envoyerAuRobot("action", "stop")
					} else if act == "reset" {
						globalState.MatchRunning = false
						globalState.MatchFinished = false
						globalState.ScoreCurrent = 0
						globalState.FsmState = "WAIT_START"
						envoyerAuRobot("action", "reset")
					}
					globalState.Unlock()
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

						envoyerAuRobot("config_update", globalState.Config)
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
				globalState.Telemetry = tel
				if tel.Tirette == "TRIGGERED" && !globalState.MatchRunning {
					globalState.MatchRunning = true
					globalState.FsmState = "RUNNING"
				}
				packet, _ := json.Marshal(map[string]interface{}{
					"type": "state_update",
					"data": &globalState,
				})
				globalState.Unlock()

				globalHub.Broadcast(packet)
			}
		}
	}
}

// Envoyer un ordre descendant vers le robot via ZMQ PUB
func envoyerAuRobot(cmdType string, payload interface{}) {
	packet, err := json.Marshal(map[string]interface{}{
		"type":    cmdType,
		"payload": payload,
	})
	if err == nil && zmqPublisher != nil {
		zmqPublisher.Send(string(packet), 0)
	}
}
