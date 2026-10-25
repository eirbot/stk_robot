package main

import (
	"encoding/json"
	"fmt"
	"sync"
	"time"
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

// Pose détectée par la caméra zénithale (indépendante de l'odométrie roues)
type VisionPose struct {
	X           float64      `json:"x"`
	Y           float64      `json:"y"`
	Theta       float64      `json:"theta"` // En degrés
	Detected    bool         `json:"detected"`
	Adversaires []Adversaire `json:"adversaires,omitempty"` // robots adverses vus sur la même image
	Pierres     []Pierre     `json:"pierres,omitempty"`     // pierres (tag 13, face du haut)
}

// Pierre vue d'en haut (repère table, mm ; Theta = axe long de la boîte, degrés)
type Pierre struct {
	X     float64 `json:"x"`
	Y     float64 `json:"y"`
	Z     float64 `json:"z"`
	Theta float64 `json:"theta"`
}

// Robot adverse vu par la caméra zénithale (repère table, mm) : planificateur du robot
type Adversaire struct {
	ID    int     `json:"id"`
	X     float64 `json:"x"`
	Y     float64 `json:"y"`
	Theta float64 `json:"theta"`
}

// État Global Unifié (fusion de l'IHM et du matériel)
type FullState struct {
	sync.Mutex
	MatchRunning     bool                   `json:"match_running"`
	MatchFinished    bool                   `json:"match_finished"`
	Team             string                 `json:"team"`
	TimerStr         string                 `json:"timer_str"`
	FsmState         string                 `json:"fsm_state"`
	ObstacleDetected bool                   `json:"obstacle_detected"`
	ObstacleType     int                    `json:"obstacle_type"`
	Telemetry        RobotTelemetry         `json:"telemetry"`
	VisionPose       VisionPose             `json:"vision_pose"`
	Config           map[string]interface{} `json:"config"`
	ServerIP         string                 `json:"server_ip"`

	// Miroir de l'état publié par le robot (robot_state, cf. robotstate.go)
	TiretteMsg    string            `json:"tirette_msg"`
	StratMode     string            `json:"strat_mode"`
	StaticStrat   interface{}       `json:"static_strat"`
	StratID       interface{}       `json:"strat_id"`
	TestMode      bool              `json:"test_mode"`
	BatLow        bool              `json:"bat_low"`
	RobotOnline   bool              `json:"robot_online"`
	RobotVersion  map[string]string `json:"robot_version"`
	LastRobotSeen time.Time         `json:"-"`
}

type RobotMessage struct {
	Type string          `json:"type"`
	Data json.RawMessage `json:"data"`
}

type StateUpdate struct {
	MatchRunning     *bool                   `json:"match_running"`
	MatchFinished    *bool                   `json:"match_finished"`
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
