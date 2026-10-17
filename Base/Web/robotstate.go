package main

// État du robot côté base : MIROIR en lecture seule.
//
// Le robot est la seule source de vérité de l'état du match et de sa config
// (Rasp/core/match_state.py, Rasp/core/config_store.py). Il publie un instantané
// complet « robot_state » à chaque changement et toutes les 2 s ; la base l'applique
// ici, sans jamais recalculer l'état elle-même. Les actions de l'interface sont
// seulement transmises au robot (routes /api/action et /api/config_edit).

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"time"
)

// Au-delà de ce délai sans aucun message du robot, il est considéré hors ligne
const robotOfflineAfter = 3 * time.Second

// Copie de la dernière config reçue du robot : affichée quand il est éteint
const robotConfigCacheFile = "robot_config_cache.json"

type RobotSnapshot struct {
	State   map[string]interface{} `json:"state"`
	Config  map[string]interface{} `json:"config"`
	Version map[string]string      `json:"version"`
}

func snapString(m map[string]interface{}, key string, fallback string) string {
	if v, ok := m[key].(string); ok {
		return v
	}
	return fallback
}

func snapBool(m map[string]interface{}, key string, fallback bool) bool {
	if v, ok := m[key].(bool); ok {
		return v
	}
	return fallback
}

func snapInt(m map[string]interface{}, key string, fallback int) int {
	if v, ok := m[key].(float64); ok {
		return int(v)
	}
	return fallback
}

// noteRobotMessage : à appeler pour chaque message reçu du robot.
// Renvoie true si le robot vient de repasser en ligne (état à diffuser).
func noteRobotMessage() bool {
	globalState.Lock()
	defer globalState.Unlock()
	globalState.LastRobotSeen = time.Now()
	if !globalState.RobotOnline {
		globalState.RobotOnline = true
		return true
	}
	return false
}

func robotIsOnline() bool {
	globalState.Lock()
	defer globalState.Unlock()
	return globalState.RobotOnline
}

// applyRobotSnapshot recopie l'instantané publié par le robot dans le miroir.
func applyRobotSnapshot(snap RobotSnapshot) {
	globalState.Lock()
	s := snap.State
	if s != nil {
		globalState.FsmState = snapString(s, "fsm_state", globalState.FsmState)
		globalState.MatchRunning = snapBool(s, "match_running", globalState.MatchRunning)
		globalState.MatchFinished = snapBool(s, "match_finished", globalState.MatchFinished)
		globalState.TimerStr = snapString(s, "timer_str", globalState.TimerStr)
		globalState.Team = snapString(s, "team", globalState.Team)
		globalState.TiretteMsg = snapString(s, "tirette_msg", globalState.TiretteMsg)
		globalState.StratMode = snapString(s, "strat_mode", globalState.StratMode)
		globalState.StaticStrat = s["static_strat"]
		globalState.StratID = s["strat_id"]
		globalState.TestMode = snapBool(s, "test_mode", globalState.TestMode)
		globalState.BatLow = snapBool(s, "bat_low", globalState.BatLow)
		globalState.ObstacleDetected = snapBool(s, "obstacle_detected", globalState.ObstacleDetected)
		globalState.ObstacleType = snapInt(s, "obstacle_type", globalState.ObstacleType)
		if t := snapString(s, "tirette", ""); t != "" {
			globalState.Telemetry.Tirette = t
		}
	}
	var cfgJSON []byte
	if snap.Config != nil {
		newJSON, _ := json.Marshal(snap.Config)
		oldJSON, _ := json.Marshal(globalState.Config)
		if !bytes.Equal(newJSON, oldJSON) {
			cfgJSON = newJSON
		}
		globalState.Config = snap.Config
	}
	if snap.Version != nil {
		globalState.RobotVersion = snap.Version
	}
	globalState.Unlock()

	if cfgJSON != nil {
		if err := os.WriteFile(robotConfigCacheFile, cfgJSON, 0644); err != nil {
			fmt.Printf("[ROBOT] Cache de config non écrit : %v\n", err)
		}
	}
}

// loadConfig : config affichée au démarrage, avant que le robot ne publie la sienne.
// Dernière config reçue du robot si elle existe, sinon Rasp/config.json du dépôt (lecture seule).
func loadConfig() map[string]interface{} {
	for _, path := range []string{robotConfigCacheFile, findRaspPath() + "/config.json"} {
		content, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		var cfg map[string]interface{}
		if err := json.Unmarshal(content, &cfg); err == nil {
			return cfg
		}
	}
	return make(map[string]interface{})
}

// watchRobotLink passe le robot hors ligne quand il se tait.
func watchRobotLink() {
	for {
		time.Sleep(1 * time.Second)
		globalState.Lock()
		changed := globalState.RobotOnline && time.Since(globalState.LastRobotSeen) > robotOfflineAfter
		if changed {
			globalState.RobotOnline = false
		}
		globalState.Unlock()
		if changed {
			fmt.Println("[ROBOT] Hors ligne (plus de messages)")
			broadcastState()
		}
	}
}
