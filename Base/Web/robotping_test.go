package main

import (
	"encoding/json"
	"testing"
	"time"
)

func TestComputePingStats(t *testing.T) {
	s := computePingStats([]float64{2, 4, 3, 10}, 5)
	if s.Sent != 5 || s.Received != 4 || s.LossPct != 20 {
		t.Fatalf("comptes : %+v", s)
	}
	if s.MinMs != 2 || s.MaxMs != 10 || s.AvgMs != 4.75 || s.P95Ms != 10 {
		t.Fatalf("valeurs : %+v", s)
	}
	// écarts successifs : 2, 1, 7 -> 10/3
	if s.JitterMs < 3.33 || s.JitterMs > 3.34 {
		t.Fatalf("gigue : %v", s.JitterMs)
	}
	if z := computePingStats(nil, 3); z.Received != 0 || z.LossPct != 100 {
		t.Fatalf("aucune réponse : %+v", z)
	}
}

func TestPongRéveilleLeBonPing(t *testing.T) {
	done := make(chan bool, 1)
	go func() {
		_, ok := pingRobotOnce(time.Second)
		done <- ok
	}()
	// Le ping a pris le prochain identifiant : on y répond comme le ferait le robot
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		var found int64
		pingWaiters.Range(func(k, _ any) bool { found = k.(int64); return false })
		if found != 0 {
			data, _ := json.Marshal(map[string]int64{"id": found})
			handlePong(data)
			break
		}
		time.Sleep(time.Millisecond)
	}
	if !<-done {
		t.Fatal("pong ignoré")
	}
}
