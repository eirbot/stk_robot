package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
)

// Sons, LED et journaux de match : pages Sons (media.js), LED Studio, Strat Studio, Debug, Replay.
// Les fichiers de référence sont dans le dépôt de la base (Rasp/ihm/audio, Rasp/config_led_animations.json) ;
// le robot reçoit les ordres par ZMQ et les fichiers par scp (best effort : robot éteint = OK quand même).

var (
	validAudioName = regexp.MustCompile(`^[A-Za-z0-9_\-. ]+\.mp3$`)
	validLogName   = regexp.MustCompile(`^(blackbox_[0-9_\-]+\.csv|match_[0-9_\-]+\.jsonl)$`)
	ledColorValue  = regexp.MustCompile(`^\d{1,3},\d{1,3},\d{1,3}$`)
	ledPixelValue  = regexp.MustCompile(`^\d{1,4},\d{1,3},\d{1,3},\d{1,3}$`)
)

// Dossier des journaux de match sur le robot (Rasp/utils/telemetry_logger.py)
const robotTelemetryDir = "logs/telemetry"

func audioDir() string { return filepath.Join(findRaspPath(), "ihm", "audio") }

func ledAnimationsFile() string { return filepath.Join(findRaspPath(), "config_led_animations.json") }

// Commande du service LED du robot (Rasp/utils/led_service.py) pour /api/led_control
func ledCommand(mode, value string) (string, error) {
	value = strings.TrimSpace(value)
	switch mode {
	case "color":
		if strings.EqualFold(value, "OFF") || value == "0,0,0" {
			return "OFF", nil
		}
		if ledColorValue.MatchString(value) {
			return "COLOR:" + value, nil
		}
	case "pixel":
		if ledPixelValue.MatchString(value) {
			return "PIXEL:" + value, nil
		}
	}
	return "", fmt.Errorf("commande LED invalide : mode %q, valeur %q", mode, value)
}

// Commande sur le robot par ssh (journaux) ; sortie standard
func robotSSH(ctx context.Context, command string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
		robotTarget(resolveRaspIP()), command)
	return cmd.Output()
}

func setupMediaRoutes(app *fiber.App) {
	// --- Sons ---
	app.Get("/api/list_audio_files", func(c *fiber.Ctx) error {
		files := []string{}
		entries, _ := os.ReadDir(audioDir())
		for _, e := range entries {
			if !e.IsDir() && validAudioName.MatchString(e.Name()) {
				files = append(files, e.Name())
			}
		}
		sort.Strings(files)
		return c.JSON(files)
	})

	app.Post("/api/upload_sound", func(c *fiber.Ctx) error {
		file, err := c.FormFile("file")
		if err != nil || !validAudioName.MatchString(file.Filename) {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "fichier .mp3 attendu (lettres, chiffres, - _ . espace)"})
		}
		_ = os.MkdirAll(audioDir(), 0755)
		dest := filepath.Join(audioDir(), file.Filename)
		if err := c.SaveFile(file, dest); err != nil {
			return c.Status(500).JSON(fiber.Map{"status": "error", "msg": err.Error()})
		}
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		scp := exec.CommandContext(ctx, "scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
			dest, fmt.Sprintf("%s:%s/ihm/audio/", robotTarget(resolveRaspIP()), robotDir))
		robotOK := scp.Run() == nil
		return c.JSON(fiber.Map{"status": "ok", "robot": robotOK})
	})

	app.Post("/api/play_test", func(c *fiber.Ctx) error {
		var body struct {
			Filename string `json:"filename"`
		}
		if err := c.BodyParser(&body); err != nil || body.Filename == "" {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "filename requis"})
		}
		envoyerAuRobot("play_audio", fiber.Map{"filename": body.Filename})
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/stop_audio", func(c *fiber.Ctx) error {
		envoyerAuRobot("stop_audio", nil)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/set_volume", func(c *fiber.Ctx) error {
		var body struct {
			Volume int `json:"volume"`
		}
		if err := c.BodyParser(&body); err != nil || body.Volume < 0 || body.Volume > 100 {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "volume entre 0 et 100"})
		}
		envoyerAuRobot("set_volume", fiber.Map{"volume": body.Volume})
		return c.JSON(fiber.Map{"status": "ok"})
	})

	// --- LED ---
	app.Get("/api/led_animations", func(c *fiber.Ctx) error {
		data, err := os.ReadFile(ledAnimationsFile())
		if err != nil {
			return c.JSON(fiber.Map{})
		}
		c.Set("Content-Type", "application/json")
		return c.Send(data)
	})

	app.Post("/api/led_animations", func(c *fiber.Ctx) error {
		var animations map[string]interface{}
		if err := json.Unmarshal(c.Body(), &animations); err != nil {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "objet JSON attendu"})
		}
		data, _ := json.MarshalIndent(animations, "", "    ")
		if err := os.WriteFile(ledAnimationsFile(), data, 0644); err != nil {
			return c.Status(500).JSON(fiber.Map{"status": "error", "msg": err.Error()})
		}
		// Le robot écrit sa copie et recharge le service LED
		envoyerAuRobot("led_animations", animations)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/play_animation", func(c *fiber.Ctx) error {
		var body struct {
			Name string `json:"name"`
		}
		if err := c.BodyParser(&body); err != nil || strings.TrimSpace(body.Name) == "" || strings.ContainsAny(body.Name, "\n:") {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "nom d'animation invalide"})
		}
		envoyerAuRobot("led_cmd", "PLAY:"+strings.TrimSpace(body.Name))
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/led_control", func(c *fiber.Ctx) error {
		var body struct {
			Mode  string `json:"mode"`
			Value string `json:"value"`
		}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": err.Error()})
		}
		cmd, err := ledCommand(body.Mode, body.Value)
		if err != nil {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": err.Error()})
		}
		envoyerAuRobot("led_cmd", cmd)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/set_brightness", func(c *fiber.Ctx) error {
		var body struct {
			Value float64 `json:"value"`
		}
		if err := c.BodyParser(&body); err != nil || body.Value < 0 || body.Value > 1 {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "luminosité entre 0 et 1"})
		}
		envoyerAuRobot("led_cmd", fmt.Sprintf("BRIGHTNESS:%.3f", body.Value))
		return c.JSON(fiber.Map{"status": "ok"})
	})

	// --- Journaux de match (enregistrés par le robot pendant chaque match) ---
	app.Get("/api/logs/list", func(c *fiber.Ctx) error {
		ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
		defer cancel()
		out, err := robotSSH(ctx, fmt.Sprintf("ls -1t %s/%s 2>/dev/null", robotDir, robotTelemetryDir))
		files := []string{}
		if err == nil {
			for _, f := range strings.Split(string(out), "\n") {
				if validLogName.MatchString(strings.TrimSpace(f)) {
					files = append(files, strings.TrimSpace(f))
				}
			}
		}
		return c.JSON(files)
	})

	app.Get("/api/logs/:name", func(c *fiber.Ctx) error {
		name := c.Params("name")
		if !validLogName.MatchString(name) {
			return c.Status(400).SendString("nom de journal invalide")
		}
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		out, err := robotSSH(ctx, fmt.Sprintf("cat %s/%s/%s", robotDir, robotTelemetryDir, name))
		if err != nil {
			return c.Status(502).SendString("journal illisible sur le robot (hors ligne ?)")
		}
		if strings.HasSuffix(name, ".jsonl") {
			c.Set("Content-Type", "application/x-ndjson; charset=utf-8")
		} else {
			c.Set("Content-Type", "text/csv; charset=utf-8")
		}
		return c.Send(out)
	})
}
