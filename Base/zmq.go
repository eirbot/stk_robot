package main

import (
	"encoding/json"
	"fmt"
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
			if msgObj.Type == "state_update" {
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

					select {
					case chanToWeb <- packet:
					default:
					}
				}
			} else {
				// Relay any other message types (new_log, sys_info) directly to web clients
				select {
				case chanToWeb <- []byte(msg):
				default:
				}
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

				select {
				case chanToWeb <- packet:
				default:
				}
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
