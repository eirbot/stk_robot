package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/websocket/v2"
)

func broadcastState() {
	globalState.Lock()
	packet, err := json.Marshal(map[string]interface{}{
		"type": "state_update",
		"data": &globalState,
	})
	globalState.Unlock()

	if err == nil {
		globalHub.Broadcast(packet)
	}
}

func saveConfigToFile(cfg map[string]interface{}) {
	configData, err := json.MarshalIndent(cfg, "", "    ")
	if err == nil {
		_ = os.WriteFile("../../Rasp/config.json", configData, 0644)
	}
}

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
		if act == "team" {
			if globalState.Team == "BLEUE" {
				globalState.Team = "JAUNE"
			} else {
				globalState.Team = "BLEUE"
			}
			if globalState.Config != nil {
				globalState.Config["team"] = globalState.Team
				saveConfigToFile(globalState.Config)
			}
			// On notifie le robot de la nouvelle configuration
			envoyerAuRobot("config_update", globalState.Config)
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
		globalState.Unlock()

		broadcastState()
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

		broadcastState()
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/config_edit", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}

		key, okKey := body["key"].(string)
		val, okVal := body["val"]

		if okKey && okVal && val != nil {
			globalState.Lock()
			if globalState.Config == nil {
				globalState.Config = make(map[string]interface{})
			}

			// Helper to set nested or flat key in config map
			keys := strings.Split(key, ".")
			curr := globalState.Config
			for i := 0; i < len(keys)-1; i++ {
				k := keys[i]
				nextMap, ok := curr[k].(map[string]interface{})
				if !ok {
					newMap := make(map[string]interface{})
					curr[k] = newMap
					curr = newMap
				} else {
					curr = nextMap
				}
			}
			curr[keys[len(keys)-1]] = val

			// Special side-effects
			if key == "team" {
				if strVal, ok := val.(string); ok {
					globalState.Team = strVal
				}
			}

			saveConfigToFile(globalState.Config)
			globalState.Unlock()

			// Notifier le robot avec la config complète mise à jour
			envoyerAuRobot("config_update", globalState.Config)
			broadcastState()
		}

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
		files, err := os.ReadDir("../../Rasp/strat/strategies")
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
		content, err := os.ReadFile("../../Rasp/strat/strategies/" + name + ".xml")
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
		
		err1 := os.WriteFile("../../Rasp/strat/strategies/"+name+".xml", []byte(body["xml"]), 0644)
		err2 := os.WriteFile("../../Rasp/strat/strategies/"+name+".py", []byte(body["code"]), 0644)
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
		
		ch := make(chan []byte, 100)
		globalHub.Lock()
		globalHub.clients[c] = ch
		globalHub.Unlock()

		defer func() {
			globalHub.Lock()
			delete(globalHub.clients, c)
			globalHub.Unlock()
			c.Close()
		}()

		// Envoyer l'état initial immédiatement après connexion
		globalState.Lock()
		initPacket, err := json.Marshal(map[string]interface{}{
			"type": "state_update",
			"data": &globalState,
		})
		globalState.Unlock()
		if err == nil {
			c.WriteMessage(websocket.TextMessage, initPacket)
		}

		// Goroutine pour lire les messages du client WebSocket
		go func() {
			for {
				_, msg, err := c.ReadMessage()
				if err != nil {
					break
				}
				
				var packet struct {
					Type    string      `json:"type"`
					Payload interface{} `json:"payload"`
				}
				if err := json.Unmarshal(msg, &packet); err == nil {
					if packet.Type == "action" && packet.Payload == "calibrate_vision" {
						fmt.Println("[Web-IHM] Message de calibration vision reçu, retransmission vers ZMQ...")
						envoyerAuRobot("action", "calibrate_vision")
					}
				}
			}
		}()

		// Boucle d'envoi de la télémétrie/état vers le navigateur à haute fréquence
		for msg := range ch {
			if err := c.WriteMessage(websocket.TextMessage, msg); err != nil {
				break
			}
		}
	}))
}
