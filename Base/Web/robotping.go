package main

// Diagnostic du lien base <-> robot : série d'allers-retours ZMQ « ping » / « pong »
// (le robot renvoie aussitôt le pong, cf. Rasp/ihm/zmq_client.py).

import (
	"encoding/json"
	"math"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gofiber/fiber/v2"
)

var (
	pingSeq     int64
	pingWaiters sync.Map // id -> chan struct{}
)

// Pong reçu du robot (zmq.go)
func handlePong(data json.RawMessage) {
	var p struct {
		ID int64 `json:"id"`
	}
	if json.Unmarshal(data, &p) != nil {
		return
	}
	if ch, ok := pingWaiters.Load(p.ID); ok {
		select {
		case ch.(chan struct{}) <- struct{}{}:
		default:
		}
	}
}

// Un aller-retour ; false si pas de réponse avant timeout
func pingRobotOnce(timeout time.Duration) (time.Duration, bool) {
	id := atomic.AddInt64(&pingSeq, 1)
	ch := make(chan struct{}, 1)
	pingWaiters.Store(id, ch)
	defer pingWaiters.Delete(id)

	start := time.Now()
	envoyerAuRobot("ping", map[string]int64{"id": id})
	select {
	case <-ch:
		return time.Since(start), true
	case <-time.After(timeout):
		return 0, false
	}
}

type PingStats struct {
	Sent     int       `json:"sent"`
	Received int       `json:"received"`
	LossPct  float64   `json:"loss_pct"`
	MinMs    float64   `json:"min_ms"`
	AvgMs    float64   `json:"avg_ms"`
	P95Ms    float64   `json:"p95_ms"`
	MaxMs    float64   `json:"max_ms"`
	JitterMs float64   `json:"jitter_ms"` // écart moyen entre deux allers-retours successifs
	RTTs     []float64 `json:"rtts_ms"`
}

// Statistiques d'une série (rtts : allers-retours reçus, dans l'ordre ; sent : pings envoyés)
func computePingStats(rtts []float64, sent int) PingStats {
	s := PingStats{Sent: sent, Received: len(rtts), RTTs: rtts}
	if sent > 0 {
		s.LossPct = 100 * float64(sent-len(rtts)) / float64(sent)
	}
	if len(rtts) == 0 {
		return s
	}
	sorted := append([]float64(nil), rtts...)
	sort.Float64s(sorted)
	sum := 0.0
	for _, v := range sorted {
		sum += v
	}
	s.MinMs = sorted[0]
	s.MaxMs = sorted[len(sorted)-1]
	s.AvgMs = sum / float64(len(sorted))
	s.P95Ms = sorted[int(math.Ceil(0.95*float64(len(sorted))))-1]
	if len(rtts) > 1 {
		j := 0.0
		for i := 1; i < len(rtts); i++ {
			j += math.Abs(rtts[i] - rtts[i-1])
		}
		s.JitterMs = j / float64(len(rtts)-1)
	}
	return s
}

// n pings espacés de interval ; arrêt après 5 pertes d'affilée (robot qui ne répond plus)
func runRobotPing(n int, interval, timeout time.Duration) PingStats {
	var rtts []float64
	sent, lostInARow := 0, 0
	for i := 0; i < n && lostInARow < 5; i++ {
		sent++
		if d, ok := pingRobotOnce(timeout); ok {
			rtts = append(rtts, float64(d.Microseconds())/1000)
			lostInARow = 0
		} else {
			lostInARow++
		}
		time.Sleep(interval)
	}
	return computePingStats(rtts, sent)
}

func matchIsRunning() bool {
	globalState.Lock()
	defer globalState.Unlock()
	return globalState.MatchRunning
}

// Les tests réseau saturent le Wi-Fi : interdits pendant un match
func refuseDuringMatch(c *fiber.Ctx) error {
	if matchIsRunning() {
		return c.Status(409).JSON(fiber.Map{"status": "error", "msg": "Test réseau impossible pendant un match"})
	}
	return c.Next()
}

func handleRobotPing(c *fiber.Ctx) error {
	if !robotIsOnline() {
		return c.Status(503).JSON(fiber.Map{"status": "error", "msg": "Robot hors ligne"})
	}
	n := c.QueryInt("n", 30)
	if n < 1 {
		n = 1
	} else if n > 100 {
		n = 100
	}
	return c.JSON(runRobotPing(n, 50*time.Millisecond, 500*time.Millisecond))
}
