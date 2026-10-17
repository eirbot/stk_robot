package main

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

// Isole chaque test dans un dossier temporaire (cache de config écrit en relatif)
func inTempDir(t *testing.T) {
	t.Helper()
	dir := t.TempDir()
	old, _ := os.Getwd()
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = os.Chdir(old) })
}

func resetGlobalState() {
	globalState.Lock()
	globalState.MatchRunning = false
	globalState.FsmState = "WAIT_START"
	globalState.Team = "BLEUE"
	globalState.Config = map[string]interface{}{}
	globalState.RobotOnline = false
	globalState.RobotVersion = nil
	globalState.Unlock()
}

func TestApplyRobotSnapshot(t *testing.T) {
	inTempDir(t)
	resetGlobalState()
	applyRobotSnapshot(RobotSnapshot{
		State: map[string]interface{}{
			"fsm_state": "RUNNING", "match_running": true, "team": "JAUNE",
			"timer_str": "42.0", "strat_id": "carre", "test_mode": true,
			"tirette": "TRIGGERED", "obstacle_type": float64(2),
		},
		Config:  map[string]interface{}{"team": "JAUNE", "static_strat": "carre"},
		Version: map[string]string{"commit": "abc123"},
	})
	globalState.Lock()
	defer globalState.Unlock()
	if globalState.FsmState != "RUNNING" || !globalState.MatchRunning || globalState.Team != "JAUNE" {
		t.Fatalf("état mal recopié : %s %v %s", globalState.FsmState, globalState.MatchRunning, globalState.Team)
	}
	if globalState.TimerStr != "42.0" || globalState.StratID != "carre" || !globalState.TestMode {
		t.Fatalf("champs du match mal recopiés")
	}
	if globalState.Telemetry.Tirette != "TRIGGERED" || globalState.ObstacleType != 2 {
		t.Fatalf("tirette / obstacle mal recopiés")
	}
	if globalState.RobotVersion["commit"] != "abc123" {
		t.Fatalf("version robot absente")
	}
}

func TestConfigCacheEtLoadConfig(t *testing.T) {
	inTempDir(t)
	resetGlobalState()
	applyRobotSnapshot(RobotSnapshot{Config: map[string]interface{}{"team": "JAUNE", "lidar_mode": "OFF"}})
	if _, err := os.Stat(robotConfigCacheFile); err != nil {
		t.Fatalf("cache non écrit : %v", err)
	}
	cfg := loadConfig()
	if cfg["lidar_mode"] != "OFF" {
		t.Fatalf("loadConfig n'a pas relu le cache : %v", cfg)
	}
	abs, _ := filepath.Abs(robotConfigCacheFile)
	t.Logf("cache : %s", abs)
}

func TestSnapshotPartielGardeLesValeurs(t *testing.T) {
	inTempDir(t)
	resetGlobalState()
	globalState.Lock()
	globalState.Team = "JAUNE"
	globalState.Unlock()
	applyRobotSnapshot(RobotSnapshot{State: map[string]interface{}{"fsm_state": "STOPPED"}})
	globalState.Lock()
	defer globalState.Unlock()
	if globalState.Team != "JAUNE" || globalState.FsmState != "STOPPED" {
		t.Fatalf("un champ absent ne doit pas être écrasé")
	}
}

func TestRobotEnLigne(t *testing.T) {
	resetGlobalState()
	if robotIsOnline() {
		t.Fatal("hors ligne au départ")
	}
	if !noteRobotMessage() {
		t.Fatal("premier message : doit signaler le passage en ligne")
	}
	if noteRobotMessage() {
		t.Fatal("déjà en ligne : pas de nouveau signal")
	}
	globalState.Lock()
	globalState.LastRobotSeen = time.Now().Add(-2 * robotOfflineAfter)
	globalState.Unlock()
	// Une itération de watchRobotLink
	globalState.Lock()
	if globalState.RobotOnline && time.Since(globalState.LastRobotSeen) > robotOfflineAfter {
		globalState.RobotOnline = false
	}
	globalState.Unlock()
	if robotIsOnline() {
		t.Fatal("doit passer hors ligne après le délai")
	}
}
