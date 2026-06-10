package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/websocket/v2"
)

func setupRoutes(app *fiber.App) {
	// Services de fichiers statiques pour l'IHM
	app.Static("/static", "./static")
	app.Get("/", func(c *fiber.Ctx) error { return c.SendFile("./templates/index.html") })
	app.Get("/map", func(c *fiber.Ctx) error { return c.SendFile("./templates/map.html") })
	app.Get("/debug", func(c *fiber.Ctx) error { return c.SendFile("./templates/debug.html") })
	app.Get("/blockly", func(c *fiber.Ctx) error { return c.SendFile("./templates/blockly.html") })
	app.Get("/led_studio", func(c *fiber.Ctx) error { return c.SendFile("./templates/led_studio.html") })
	app.Get("/media", func(c *fiber.Ctx) error { return c.SendFile("./templates/media.html") })
	app.Get("/replay", func(c *fiber.Ctx) error { return c.SendFile("./templates/replay.html") })

	// API REST pour les actions initiées depuis l'IHM Web
	app.Post("/api/action/:act", func(c *fiber.Ctx) error {
		act := c.Params("act")

		globalState.Lock()
		defer globalState.Unlock()

		if act == "team" {
			if globalState.Team == "BLEUE" {
				globalState.Team = "JAUNE"
			} else {
				globalState.Team = "BLEUE"
			}
			// On notifie le robot instantanément pour ses LEDs de couleur d'équipe
			envoyerAuRobot("set_team", map[string]string{"team": globalState.Team})
		} else if act == "start" {
			globalState.MatchRunning = true
			globalState.FsmState = "RUNNING"
			envoyerAuRobot("action", "start")
		} else if act == "stop" {
			globalState.MatchRunning = false
			globalState.FsmState = "STOPPED"
			envoyerAuRobot("action", "stop")
		} else if act == "reset" {
			globalState.MatchRunning = false
			globalState.MatchFinished = false
			globalState.ScoreCurrent = 0
			globalState.FsmState = "WAIT_START"
			envoyerAuRobot("action", "reset")
		} else if act == "tirette" {
			envoyerAuRobot("action", "tirette")
		}
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/score_edit", func(c *fiber.Ctx) error {
		var body map[string]int
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		delta := body["delta"]
		globalState.Lock()
		globalState.ScoreCurrent += delta
		if globalState.ScoreCurrent < 0 {
			globalState.ScoreCurrent = 0
		}
		envoyerAuRobot("update_score", map[string]int{"score_current": globalState.ScoreCurrent})
		globalState.Unlock()
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/config_edit", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		envoyerAuRobot("config_edit", body)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/goto", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		envoyerAuRobot("goto", body)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/set_robot_pos", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		envoyerAuRobot("set_robot_pos", body)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Get("/api/list_blockly_strats", func(c *fiber.Ctx) error {
		files, err := os.ReadDir("../Rasp/strat/strategies")
		if err != nil {
			return c.JSON([]string{})
		}
		var strats []string
		for _, file := range files {
			if !file.IsDir() && strings.HasSuffix(file.Name(), ".xml") {
				strats = append(strats, strings.TrimSuffix(file.Name(), ".xml"))
			}
		}
		return c.JSON(strats)
	})

	app.Get("/api/load_strat/:name", func(c *fiber.Ctx) error {
		name := c.Params("name")
		content, err := os.ReadFile("../Rasp/strat/strategies/" + name + ".xml")
		if err != nil {
			return c.Status(404).JSON(fiber.Map{"status": "error"})
		}
		return c.JSON(fiber.Map{"status": "success", "xml": string(content)})
	})

	app.Post("/api/save_strat", func(c *fiber.Ctx) error {
		var body map[string]string
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"status": "error"})
		}
		name := strings.ReplaceAll(body["filename"], ".xml", "")
		name = strings.ReplaceAll(name, ".py", "")
		
		err1 := os.WriteFile("../Rasp/strat/strategies/"+name+".xml", []byte(body["xml"]), 0644)
		err2 := os.WriteFile("../Rasp/strat/strategies/"+name+".py", []byte(body["code"]), 0644)
		if err1 != nil || err2 != nil {
			return c.Status(500).JSON(fiber.Map{"status": "error"})
		}
		return c.JSON(fiber.Map{"status": "success"})
	})

	app.Get("/api/beacons", func(c *fiber.Ctx) error {
		return c.JSON([][]float64{
			{50, 1550},
			{1950, 1550},
			{1000, -1550},
			{-125, 225},
		})
	})

	// Route API pour l'envoi de fichiers audios ou d'animations de l'IHM vers le robot
	app.Post("/api/robot/hardware", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		// On transmet directement l'action matérielle (ex: type: "play_audio", file: "intro.mp3")
		envoyerAuRobot(body["action"].(string), body["data"])
		return c.JSON(fiber.Map{"status": "sent_to_robot"})
	})

	// Gestionnaire d'IHM en temps réel (WebSockets)
	app.Use("/ws", func(c *fiber.Ctx) error {
		if websocket.IsWebSocketUpgrade(c) {
			return c.Next()
		}
		return fiber.ErrUpgradeRequired
	})

	app.Get("/ws", websocket.New(func(c *websocket.Conn) {
		fmt.Println("[Web-IHM] Client connecté")
		defer c.Close()

		// Boucle d'envoi de la télémétrie/état vers le navigateur à haute fréquence
		for {
			msg := <-chanToWeb
			if err := c.WriteMessage(websocket.TextMessage, msg); err != nil {
				break
			}
		}
	}))
}
