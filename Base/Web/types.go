package main

import (
	"encoding/json"
	"fmt"
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
	RaspIP  string  `json:"rasp_ip"`
}

func (t *RobotTelemetry) UnmarshalJSON(data []byte) error {
	type Alias RobotTelemetry
	aux := struct {
		Current interface{} `json:"current"`
		Voltage interface{} `json:"voltage"`
		*Alias
	}{
		Alias: (*Alias)(t),
	}
	if err := json.Unmarshal(data, &aux); err != nil {
		return err
	}
	switch v := aux.Current.(type) {
	case float64:
		t.Current = v
	case string:
		var f float64
		fmt.Sscanf(v, "%f", &f)
		t.Current = f
	}
	switch v := aux.Voltage.(type) {
	case float64:
		t.Voltage = v
	case string:
		var f float64
		fmt.Sscanf(v, "%f", &f)
		t.Voltage = f
	}
	return nil
}

// État Global Unifié (fusion de l'IHM et du matériel)
type FullState struct {
	sync.Mutex
	MatchRunning     bool                   `json:"match_running"`
	MatchFinished    bool                   `json:"match_finished"`
	ScoreCurrent     int                    `json:"score_current"`
	Team             string                 `json:"team"`
	TimerStr         string                 `json:"timer_str"`
	FsmState         string                 `json:"fsm_state"`
	ObstacleDetected bool                   `json:"obstacle_detected"`
	ObstacleType     int                    `json:"obstacle_type"`
	Telemetry        RobotTelemetry         `json:"telemetry"`
	Config           map[string]interface{} `json:"config"`
	ServerIP         string                 `json:"server_ip"`
}

type RobotMessage struct {
	Type string          `json:"type"`
	Data json.RawMessage `json:"data"`
}

type StateUpdate struct {
	MatchRunning     *bool                   `json:"match_running"`
	MatchFinished    *bool                   `json:"match_finished"`
	ScoreCurrent     *int                    `json:"score_current"`
	Team             *string                 `json:"team"`
	TimerStr         *string                 `json:"timer_str"`
	FsmState         *string                 `json:"fsm_state"`
	ObstacleDetected *bool                   `json:"obstacle_detected"`
	ObstacleType     *int                    `json:"obstacle_type"`
	X                *float64                `json:"x"`
	Y                *float64                `json:"y"`
	Theta            *float64                `json:"theta"`
	Voltage          *float64                `json:"voltage"`
	Current          *float64                `json:"current"`
	Tirette          *string                 `json:"tirette"`
	IMUYaw           *float64                `json:"imu_yaw"`
	RaspIP           *string                 `json:"rasp_ip"`
	Telemetry        *RobotTelemetry         `json:"telemetry"`
	Config           *map[string]interface{} `json:"config"`
}
