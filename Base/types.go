package main

import (
	"encoding/json"
	"sync"
)

// Structure de la Télémétrie Montante (provenant du Robot)
type RobotTelemetry struct {
	X       float64 `json:"x"`
	Y       float64 `json:"y"`
	Theta   float64 `json:"theta"`
	Voltage float64 `json:"voltage"`
	Current float64 `json:"current"`
	Tirette string  `json:"tirette"` // "WAIT_INSERT", "TRIGGERED"
	IMUYaw  float64 `json:"imu_yaw"`
}

// État Global Unifié (fusion de l'IHM et du matériel)
type FullState struct {
	sync.Mutex
	MatchRunning  bool                   `json:"match_running"`
	MatchFinished bool                   `json:"match_finished"`
	ScoreCurrent  int                    `json:"score_current"`
	Team          string                 `json:"team"`
	TimerStr      string                 `json:"timer_str"`
	FsmState      string                 `json:"fsm_state"`
	Telemetry     RobotTelemetry         `json:"telemetry"`
	Config        map[string]interface{} `json:"config"`
}

type RobotMessage struct {
	Type string          `json:"type"`
	Data json.RawMessage `json:"data"`
}

type StateUpdate struct {
	MatchRunning  *bool                   `json:"match_running"`
	MatchFinished *bool                   `json:"match_finished"`
	ScoreCurrent  *int                    `json:"score_current"`
	Team          *string                 `json:"team"`
	TimerStr      *string                 `json:"timer_str"`
	FsmState      *string                 `json:"fsm_state"`
	X             *float64                `json:"x"`
	Y             *float64                `json:"y"`
	Theta         *float64                `json:"theta"`
	Voltage       *float64                `json:"voltage"`
	Current       *float64                `json:"current"`
	Tirette       *string                 `json:"tirette"`
	IMUYaw        *float64                `json:"imu_yaw"`
	Telemetry     *RobotTelemetry         `json:"telemetry"`
	Config        *map[string]interface{} `json:"config"`
}
