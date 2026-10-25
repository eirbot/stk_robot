package main

import (
	"bufio"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/websocket/v2"
)

// 5. Copie sérialisée sous verrou pour éviter 'concurrent map iteration and write'
func getConfigCopyLocked() json.RawMessage {
	if globalState.Config == nil {
		return json.RawMessage("{}")
	}
	data, err := json.Marshal(globalState.Config)
	if err != nil {
		return json.RawMessage("{}")
	}
	return json.RawMessage(data)
}

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

func findWebDir() string {
	candidates := []string{
		"Web",
		"./Web",
		".",
		"../Web",
		"Base/Web",
	}
	for _, c := range candidates {
		if _, err := os.Stat(filepath.Join(c, "templates", "index.html")); err == nil {
			return c
		}
	}
	return "."
}

func setupRoutes(app *fiber.App) {
	webDir := findWebDir()

	// Code PIN des actions sensibles (auth.go) : avant toutes les routes /api
	app.Use("/api", authMiddleware)
	setupAuthRoutes(app)

	// Services de fichiers statiques pour l'IHM avec mise en cache et compression
	app.Static("/static", filepath.Join(webDir, "static"), fiber.Static{
		Compress:      true,
		ByteRange:     true,
		Browse:        false,
		MaxAge:        0, // Rechargement instantané des fichiers CSS/JS à chaque modification
		CacheDuration: 1 * time.Second,
	})

	// Modèles MuJoCo de vision_deporte (table, robot) : affichés tels quels par la carte 3D (map.js).
	// Sans Compress : Fiber écrirait une copie .fiber.gz de chaque fichier dans le sous-module.
	if dir := mujocoModelsDir(); dir != "" {
		app.Static("/models", dir, fiber.Static{MaxAge: 3600})
	}

	// Pages HTML avec en-têtes anti-blocage et revalidation
	sendPage := func(c *fiber.Ctx, relPath string) error {
		c.Set("Cache-Control", "no-cache, must-revalidate")
		return c.SendFile(filepath.Join(webDir, relPath))
	}

	// Pas d'icône d'onglet : 204 plutôt qu'un 404 dans la console du navigateur
	app.Get("/favicon.ico", func(c *fiber.Ctx) error { return c.SendStatus(fiber.StatusNoContent) })
	app.Get("/", func(c *fiber.Ctx) error { return sendPage(c, "templates/index.html") })
	app.Get("/map", func(c *fiber.Ctx) error { return sendPage(c, "templates/map.html") })
	app.Get("/debug", func(c *fiber.Ctx) error { return sendPage(c, "templates/debug.html") })
	app.Get("/blockly", func(c *fiber.Ctx) error { return sendPage(c, "templates/blockly.html") })
	app.Get("/led_studio", func(c *fiber.Ctx) error { return sendPage(c, "templates/led_studio.html") })
	app.Get("/media", func(c *fiber.Ctx) error { return sendPage(c, "templates/media.html") })
	app.Get("/replay", func(c *fiber.Ctx) error { return sendPage(c, "templates/replay.html") })
	app.Get("/controle", func(c *fiber.Ctx) error { return sendPage(c, "templates/controle.html") })
	app.Get("/control", func(c *fiber.Ctx) error { return c.Redirect("/controle") })
	app.Get("/regles", func(c *fiber.Ctx) error { return sendPage(c, "templates/regles.html") })
	app.Get("/update", func(c *fiber.Ctx) error { return sendPage(c, "templates/update.html") })
	app.Get("/demineur", func(c *fiber.Ctx) error { return sendPage(c, "templates/demineur.html") })

	// Règlements en PDF (dossier docu/ du dépôt) : seulement des .pdf, sans sous-dossier
	app.Get("/docu/:name", func(c *fiber.Ctx) error {
		name := filepath.Base(c.Params("name"))
		if !strings.HasSuffix(strings.ToLower(name), ".pdf") {
			return c.SendStatus(fiber.StatusNotFound)
		}
		path := filepath.Join(webDir, "..", "..", "docu", name)
		if _, err := os.Stat(path); err != nil {
			return c.SendStatus(fiber.StatusNotFound)
		}
		c.Set("Content-Type", "application/pdf")
		return c.SendFile(path)
	})

	// API REST pour contrôle vitesse joystick
	app.Post("/api/cmd_vel", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		envoyerAuRobot("cmd_vel", body)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	// API REST pour contrôle des actionneurs
	app.Post("/api/actuator", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		envoyerAuRobot("cmd_actuator", body)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	// API REST pour récupérer l'adresse IP réseau réelle du PC Base et de la Rasp
	app.Get("/api/server_ip", func(c *fiber.Ctx) error {
		globalState.Lock()
		raspIP := globalState.Telemetry.RaspIP
		globalState.Unlock()
		return c.JSON(fiber.Map{
			"ip":      getHostIP(),
			"rasp_ip": raspIP,
		})
	})

	// API REST pour les actions initiées depuis l'IHM Web
	// Le robot est la source de vérité : la base transmet les ordres et attend
	// l'instantané « robot_state » qu'il publie en retour (cf. robotstate.go).
	app.Post("/api/action/:act", func(c *fiber.Ctx) error {
		act := c.Params("act")
		switch act {
		case "start", "stop", "reset", "team", "tirette", "init":
		default:
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "Action inconnue : " + act})
		}
		if !robotIsOnline() {
			return c.Status(503).JSON(fiber.Map{"status": "error", "msg": "Robot hors ligne : action impossible"})
		}
		envoyerAuRobot("action", act)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/config_edit", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": err.Error()})
		}
		key, okKey := body["key"].(string)
		val, okVal := body["val"]
		if !okKey || !okVal || val == nil {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "key et val requis"})
		}
		if !robotIsOnline() {
			return c.Status(503).JSON(fiber.Map{"status": "error", "msg": "Robot hors ligne : réglage impossible"})
		}
		// Le robot valide, enregistre (config.json du robot) et republie sa config
		envoyerAuRobot("config_edit", map[string]interface{}{"key": key, "val": val})
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

	setupStrategyRoutes(app)
	setupMediaRoutes(app)

	// Routes de diagnostic pour le test de connexion (latence et débit)
	app.Get("/api/ping", func(c *fiber.Ctx) error {
		return c.SendStatus(200)
	})

	// Lien base <-> robot (allers-retours ZMQ) ; tests réseau refusés pendant un match
	app.Get("/api/robot_ping", refuseDuringMatch, handleRobotPing)

	app.Get("/api/speedtest/download", refuseDuringMatch, func(c *fiber.Ctx) error {
		c.Set("Content-Type", "application/octet-stream")
		c.Set("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
		c.Set("Content-Encoding", "identity")

		c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
			buffer := make([]byte, 64*1024) // 64 KB chunk
			_, _ = rand.Read(buffer)

			total := 0
			limit := 500 * 1024 * 1024 // 500 MB limit (largement suffisant pour 2 secondes à des débits multi-gigabits)
			for total < limit {
				n, err := w.Write(buffer)
				if err != nil {
					break
				}
				err = w.Flush()
				if err != nil {
					break
				}
				total += n
			}
		})
		return nil
	})

	app.Post("/api/speedtest/upload", refuseDuringMatch, func(c *fiber.Ctx) error {
		body := c.Body()
		return c.JSON(fiber.Map{
			"status": "ok",
			"bytes":  len(body),
		})
	})

	// Route API pour l'envoi de fichiers audios ou d'animations de l'IHM vers le robot
	app.Post("/api/robot/hardware", func(c *fiber.Ctx) error {
		var body map[string]interface{}
		if err := c.BodyParser(&body); err != nil {
			return c.Status(400).JSON(fiber.Map{"error": err.Error()})
		}
		act, ok := body["action"].(string)
		if !ok || strings.TrimSpace(act) == "" {
			return c.Status(400).JSON(fiber.Map{"error": "champ 'action' manquant ou invalide"})
		}
		// On transmet directement l'action matérielle (ex: type: "play_audio", file: "intro.mp3")
		envoyerAuRobot(act, body["data"])
		return c.JSON(fiber.Map{"status": "sent_to_robot"})
	})

	setupVisionRoutes(app)

	// Version du binaire de la base (injectée par Base/build.sh)
	app.Get("/api/version", func(c *fiber.Ctx) error {
		globalState.Lock()
		robot := globalState.RobotVersion
		globalState.Unlock()
		return c.JSON(fiber.Map{"base": buildVersion, "robot": robot})
	})

	// État vu par la base (miroir du robot) : diagnostic, tests, deploy.sh status
	app.Get("/api/state", func(c *fiber.Ctx) error {
		globalState.Lock()
		defer globalState.Unlock()
		return c.JSON(&globalState)
	})

	setupFlashRoutes(app)

	// Gestionnaire d'IHM en temps réel (WebSockets)
	app.Use("/ws", func(c *fiber.Ctx) error {
		if websocket.IsWebSocketUpgrade(c) {
			// PIN vérifié à l'ouverture : les commandes de cette connexion en dépendent
			c.Locals("trusted", isTrusted(c))
			return c.Next()
		}
		return fiber.ErrUpgradeRequired
	})

	app.Get("/ws", websocket.New(func(c *websocket.Conn) {
		fmt.Println("[Web-IHM] Client connecté")

		ch := make(chan []byte, 16) // Buffer restreint pour éliminer le backlog de vieux paquets lors du chargement
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

		trusted, _ := c.Locals("trusted").(bool)
		authWarned := false
		var writeMu sync.Mutex // deux goroutines écrivent sur la connexion

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
					Data    interface{} `json:"data"`
				}
				if err := json.Unmarshal(msg, &packet); err == nil {
					targetPayload := packet.Payload
					if targetPayload == nil {
						targetPayload = packet.Data
					}

					// Commandes sans PIN refusées (sauf STOP) ; le navigateur demande le PIN puis se reconnecte
					isCommand := packet.Type == "cmd_vel" || packet.Type == "cmd_actuator" || packet.Type == "action"
					if isCommand && !trusted && targetPayload != "stop" {
						if !authWarned {
							authWarned = true
							writeMu.Lock()
							_ = c.WriteMessage(websocket.TextMessage, []byte(`{"type":"auth_required","data":{"msg":"Code PIN requis"}}`))
							writeMu.Unlock()
						}
						continue
					}

					if packet.Type == "cmd_vel" {
						envoyerAuRobot("cmd_vel", targetPayload)
					} else if packet.Type == "cmd_actuator" {
						envoyerAuRobot("cmd_actuator", targetPayload)
					} else if packet.Type == "action" && targetPayload == "calibrate_vision" {
						fmt.Println("[Web-IHM] Message de calibration vision reçu, retransmission vers ZMQ...")
						envoyerAuRobot("action", "calibrate_vision")
					} else if packet.Type == "action" {
						if actStr, ok := targetPayload.(string); ok {
							envoyerAuRobot("action", actStr)
						}
					}
				}
			}
		}()

		// Boucle d'envoi de la télémétrie/état vers le navigateur à haute fréquence
		for msg := range ch {
			writeMu.Lock()
			err := c.WriteMessage(websocket.TextMessage, msg)
			writeMu.Unlock()
			if err != nil {
				break
			}
		}
	}))
}

// IP de la Rasp : télémétrie, sinon baux DHCP, sinon IP par défaut
func resolveRaspIP() string {
	globalState.Lock()
	raspIP := globalState.Telemetry.RaspIP
	globalState.Unlock()
	if !isValidIP(raspIP) {
		raspIP = getRaspIPFromDHCP()
	}
	if !isValidIP(raspIP) {
		raspIP = robotFallbackIP
	}
	return raspIP
}
