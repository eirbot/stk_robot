package main

// Thème de l'écran du robot : chaque appareil garde son thème (theme.js), mais l'écran 7" du
// robot (?mode=robot) suit le dernier thème choisi sur un autre appareil. La base le retient
// (Base/ui_theme.txt) et le diffuse en direct par WebSocket ({"type":"ui_theme"}).
// POST sans PIN (cf. pinFreeRoutes) : un thème n'a aucun effet sur le robot.

import (
	"encoding/json"
	"os"
	"strings"
	"sync"

	"github.com/gofiber/fiber/v2"
)

const uiThemeFile = "ui_theme.txt"

// Mêmes noms que THEMES dans static/js/theme.js
var uiThemes = map[string]bool{"stk": true, "nuit": true, "sombre": true, "win95": true}

var uiTheme struct {
	sync.Mutex
	name string
}

func loadUITheme() {
	b, err := os.ReadFile(uiThemeFile)
	name := strings.TrimSpace(string(b))
	if err != nil || !uiThemes[name] {
		name = "stk"
	}
	uiTheme.Lock()
	uiTheme.name = name
	uiTheme.Unlock()
}

func setupUIThemeRoutes(app *fiber.App) {
	loadUITheme()

	app.Get("/api/ui_theme", func(c *fiber.Ctx) error {
		uiTheme.Lock()
		defer uiTheme.Unlock()
		return c.JSON(fiber.Map{"theme": uiTheme.name})
	})

	app.Post("/api/ui_theme", func(c *fiber.Ctx) error {
		var req struct {
			Theme string `json:"theme"`
		}
		if err := c.BodyParser(&req); err != nil || !uiThemes[req.Theme] {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "Thème inconnu"})
		}
		uiTheme.Lock()
		changed := uiTheme.name != req.Theme
		uiTheme.name = req.Theme
		uiTheme.Unlock()
		if changed {
			_ = os.WriteFile(uiThemeFile, []byte(req.Theme+"\n"), 0o644)
			if packet, err := json.Marshal(fiber.Map{"type": "ui_theme", "data": fiber.Map{"theme": req.Theme}}); err == nil {
				globalHub.Broadcast(packet)
			}
		}
		return c.JSON(fiber.Map{"status": "ok", "theme": req.Theme})
	})
}
