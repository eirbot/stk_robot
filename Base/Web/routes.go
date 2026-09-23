package main

import (
	"bufio"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
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
		path := findRaspPath() + "/config.json"
		_ = os.WriteFile(path, configData, 0644)
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
	app.Get("/controle", func(c *fiber.Ctx) error { return c.SendFile("./templates/controle.html") })
	app.Get("/control", func(c *fiber.Ctx) error { return c.Redirect("/controle") })

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
		} else if act == "init" {
			envoyerAuRobot("action", "init")
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
		path := findRaspPath() + "/strat/strategies"
		files, err := os.ReadDir(path)
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
		path := findRaspPath() + "/strat/strategies/" + name + ".xml"
		content, err := os.ReadFile(path)
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
		
		basePath := findRaspPath() + "/strat/strategies/" + name
		err1 := os.WriteFile(basePath+".xml", []byte(body["xml"]), 0644)
		err2 := os.WriteFile(basePath+".py", []byte(body["code"]), 0644)
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

	// Routes de diagnostic pour le test de connexion (latence et débit)
	app.Get("/api/ping", func(c *fiber.Ctx) error {
		return c.SendStatus(200)
	})

	app.Get("/api/speedtest/download", func(c *fiber.Ctx) error {
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

	app.Post("/api/speedtest/upload", func(c *fiber.Ctx) error {
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
		// On transmet directement l'action matérielle (ex: type: "play_audio", file: "intro.mp3")
		envoyerAuRobot(body["action"].(string), body["data"])
		return c.JSON(fiber.Map{"status": "sent_to_robot"})
	})

	// Route API pour flasher les ESPs (Motor / Actionneurs) depuis la base déportée via la Raspberry Pi
	app.Post("/api/flash_esp/:target", func(c *fiber.Ctx) error {
		target := strings.ToLower(c.Params("target"))

		var envName, serialPort, label string
		if target == "motors" || target == "motor" {
			envName = "Motor"
			serialPort = "/dev/esp_motors"
			label = "Moteurs"
		} else if target == "arms" || target == "arm" || target == "actionneurs" {
			envName = "Actionneurs"
			serialPort = "/dev/esp_action"
			label = "Actionneurs / Bras"
		} else {
			return c.Status(400).JSON(fiber.Map{
				"status": "error",
				"msg":    fmt.Sprintf("Cible inconnue: %s. Utilisez 'motors' ou 'arms'.", target),
			})
		}

		// 1. Détermination du répertoire racine du projet (contenant platformio.ini)
		projectRoot := "/home/based/Documents/stk_robot"
		if p, err := filepath.Abs("../.."); err == nil {
			if _, err := os.Stat(filepath.Join(p, "platformio.ini")); err == nil {
				projectRoot = p
			}
		}

		// 2. Détermination du chemin vers le binaire pio
		pioPath := "/home/based/.local/bin/pio"
		if p, err := exec.LookPath("pio"); err == nil {
			pioPath = p
		} else if _, err := os.Stat("/home/based/.platformio/penv/bin/pio"); err == nil {
			pioPath = "/home/based/.platformio/penv/bin/pio"
		}

		// 3. Compilation avec PlatformIO pour l'environnement demandé
		fmt.Printf("[FLASH] Démarrage compilation PlatformIO pour '%s' dans %s...\n", envName, projectRoot)
		buildCmd := exec.Command(pioPath, "run", "-e", envName)
		buildCmd.Dir = projectRoot
		buildOut, err := buildCmd.CombinedOutput()
		if err != nil {
			fmt.Printf("[FLASH] Échec de la compilation:\n%s\n", string(buildOut))
			return c.JSON(fiber.Map{
				"status": "error",
				"step":   "build",
				"msg":    fmt.Sprintf("Échec de la compilation PlatformIO pour %s", label),
				"output": string(buildOut),
			})
		}
		fmt.Printf("[FLASH] Compilation réussie pour %s !\n", envName)

		// 4. Récupération de l'IP de la Raspberry Pi
		globalState.Lock()
		raspIP := globalState.Telemetry.RaspIP
		globalState.Unlock()
		if raspIP == "" || raspIP == "??" || raspIP == "Err" {
			raspIP = getRaspIPFromDHCP()
		}
		if raspIP == "" || raspIP == "??" || raspIP == "Err" {
			raspIP = "192.168.10.89"
		}

		// 5. Transfert des binaires (.bin) vers la Rasp
		remoteDir := fmt.Sprintf("/tmp/esp_flash/%s", envName)
		mkdirCmd := exec.Command("ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
			fmt.Sprintf("eirbot@%s", raspIP), fmt.Sprintf("mkdir -p %s", remoteDir))
		if out, err := mkdirCmd.CombinedOutput(); err != nil {
			return c.JSON(fiber.Map{
				"status": "error",
				"step":   "ssh_mkdir",
				"msg":    fmt.Sprintf("Impossible de créer le dossier distant sur la Rasp: %v", err),
				"output": string(out),
			})
		}

		localBinPattern := filepath.Join(projectRoot, ".pio", "build", envName, "*.bin")
		binFiles, _ := filepath.Glob(localBinPattern)
		if len(binFiles) == 0 {
			return c.JSON(fiber.Map{
				"status": "error",
				"step":   "find_bins",
				"msg":    fmt.Sprintf("Aucun binaire trouvé dans %s", localBinPattern),
			})
		}

		scpArgs := []string{"-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5"}
		scpArgs = append(scpArgs, binFiles...)
		scpArgs = append(scpArgs, fmt.Sprintf("eirbot@%s:%s/", raspIP, remoteDir))
		scpCmd := exec.Command("scp", scpArgs...)
		if out, err := scpCmd.CombinedOutput(); err != nil {
			return c.JSON(fiber.Map{
				"status": "error",
				"step":   "scp",
				"msg":    fmt.Sprintf("Erreur lors de la copie des binaires vers la Rasp: %v", err),
				"output": string(out),
			})
		}

		// 6. Libération du port série sur la Rasp (fuser -k pour libérer main_robot.py si actif)
		freeCmd := exec.Command("ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
			fmt.Sprintf("eirbot@%s", raspIP), fmt.Sprintf("sudo fuser -k %s 2>/dev/null; sleep 0.5", serialPort))
		_ = freeCmd.Run()

		// 7. Flashage via esptool.py sur la Raspberry Pi
		flashScript := fmt.Sprintf(
			"python3 /home/eirbot/esptool/esptool.py --chip esp32 --port %s --baud 460800 write_flash -z "+
				"--flash_mode dio --flash_freq 40m --flash_size 4MB "+
				"0x1000 %s/bootloader.bin 0x8000 %s/partitions.bin 0x10000 %s/firmware.bin",
			serialPort, remoteDir, remoteDir, remoteDir,
		)

		fmt.Printf("[FLASH] Envoi de la commande de flash sur la Rasp (%s sur %s)...\n", envName, serialPort)
		flashCmd := exec.Command("ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=30",
			fmt.Sprintf("eirbot@%s", raspIP), flashScript)
		flashOut, err := flashCmd.CombinedOutput()
		if err != nil {
			fmt.Printf("[FLASH] Échec du flash:\n%s\n", string(flashOut))
			return c.JSON(fiber.Map{
				"status": "error",
				"step":   "flash",
				"msg":    fmt.Sprintf("Échec du flash sur l'ESP %s : %v", label, err),
				"output": string(flashOut),
			})
		}

		fmt.Printf("[FLASH] Flash réussi pour %s !\n%s\n", label, string(flashOut))
		return c.JSON(fiber.Map{
			"status": "ok",
			"msg":    fmt.Sprintf("Flash de l'ESP %s réussi avec succès !", label),
			"output": string(flashOut),
		})
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
					Data    interface{} `json:"data"`
				}
				if err := json.Unmarshal(msg, &packet); err == nil {
					targetPayload := packet.Payload
					if targetPayload == nil {
						targetPayload = packet.Data
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
			if err := c.WriteMessage(websocket.TextMessage, msg); err != nil {
				break
			}
		}
	}))
}
