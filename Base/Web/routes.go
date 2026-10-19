package main

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/websocket/v2"
)

// Sérialise les flashs ESP (route /api/flash_esp)
var flashMutex sync.Mutex

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

var (
	visionCmd   *exec.Cmd
	visionDone  chan struct{} // Fermé quand le worker se termine
	visionMutex sync.Mutex
)

func findVisionDir() string {
	candidates := []string{
		"Vision",
		"./Vision",
		"../Vision",
		"Base/Vision",
		"../../Base/Vision",
		filepath.Join(findProjectRoot(), "Base", "Vision"), // cf. settings.go
	}
	for _, dir := range candidates {
		if fi, err := os.Stat(dir); err == nil && fi.IsDir() {
			if _, err2 := os.Stat(filepath.Join(dir, "CMakeLists.txt")); err2 == nil {
				return dir
			}
		}
	}
	return ""
}

func ensureVisionWorkerCompiled(visionDir string) (string, error) {
	binCandidates := []string{
		filepath.Join(visionDir, "vision_worker"),
		filepath.Join(visionDir, "build", "vision_worker"),
	}

	cppFile := filepath.Join(visionDir, "vision_worker.cpp")
	var cppModTime time.Time
	if fi, err := os.Stat(cppFile); err == nil {
		cppModTime = fi.ModTime()
	}

	for _, bin := range binCandidates {
		if fi, err := os.Stat(bin); err == nil && !fi.IsDir() {
			if !cppModTime.IsZero() && fi.ModTime().Before(cppModTime) {
				fmt.Printf("[VISION] 🔄 Le code C++ vision_worker.cpp (%s) est plus récent que %s (%s). Recompilation...\n",
					cppModTime.Format("15:04:05"), filepath.Base(bin), fi.ModTime().Format("15:04:05"))
				break
			}
			_ = os.Chmod(bin, 0755)
			return filepath.Abs(bin)
		}
	}

	// Binaire non présent ou obsolète : compilation automatique en C++ via CMake
	fmt.Printf("[VISION] ⚙️  Compilation de vision_worker C++ dans %s via CMake...\n", visionDir)
	buildDir := filepath.Join(visionDir, "build")
	_ = os.MkdirAll(buildDir, 0755)

	cmakeCmd := exec.Command("cmake", "-B", "build", "-S", ".")
	cmakeCmd.Dir = visionDir
	cmakeCmd.Stdout = os.Stdout
	cmakeCmd.Stderr = os.Stderr
	if err := cmakeCmd.Run(); err != nil {
		return "", fmt.Errorf("erreur configuration CMake dans %s: %w", visionDir, err)
	}

	makeCmd := exec.Command("cmake", "--build", "build", "-j4")
	makeCmd.Dir = visionDir
	makeCmd.Stdout = os.Stdout
	makeCmd.Stderr = os.Stderr
	if err := makeCmd.Run(); err != nil {
		return "", fmt.Errorf("erreur compilation vision_worker: %w", err)
	}

	for _, bin := range binCandidates {
		if fi, err := os.Stat(bin); err == nil && !fi.IsDir() {
			_ = os.Chmod(bin, 0755)
			fmt.Printf("[VISION] ✅ Binaire C++ compilé avec succès : %s\n", bin)
			return filepath.Abs(bin)
		}
	}

	return "", fmt.Errorf("compilation terminée mais binaire vision_worker introuvable")
}

func startVisionWorker() (int, error) {
	visionMutex.Lock()
	defer visionMutex.Unlock()

	if visionAlive() {
		return visionCmd.Process.Pid, nil
	}

	visionDir := findVisionDir()
	if visionDir == "" {
		return 0, fmt.Errorf("dossier Base/Vision introuvable")
	}

	// Vision déportée (sous-module Python/uv) en priorité, sinon worker C++
	var cmd *exec.Cmd
	label := ""
	if uvPath := findUv(); uvPath != "" && fileExists(filepath.Join(visionDir, "vision_deporte", "pyproject.toml")) {
		absDir, _ := filepath.Abs(visionDir)
		cmd = exec.Command(uvPath, "run", "--project", "vision_deporte", "--with", "pyzmq",
			"python", "vision_deporte_worker.py")
		cmd.Dir = absDir
		label = "vision_deporte (uv)"
	} else {
		binPath, err := ensureVisionWorkerCompiled(visionDir)
		if err != nil {
			return 0, fmt.Errorf("impossible de préparer le binaire C++ : %w", err)
		}
		cmd = exec.Command(binPath)
		cmd.Dir = filepath.Dir(binPath)
		label = "vision_worker C++ (" + binPath + ")"
	}
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	// Groupe de processus dédié : uv lance python en enfant, il faut tuer les deux.
	// Pdeathsig : le worker s'arrête aussi si base_stk meurt (sinon il garde la caméra et le port 8082)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true, Pdeathsig: syscall.SIGTERM}

	if err := cmd.Start(); err != nil {
		return 0, err
	}
	done := make(chan struct{})
	visionCmd, visionDone = cmd, done
	go func() { _ = cmd.Wait(); close(done) }()
	fmt.Printf("[VISION] 🚀 Processus %s démarré (PID: %d)\n", label, cmd.Process.Pid)
	return cmd.Process.Pid, nil
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func findUv() string {
	if p, err := exec.LookPath("uv"); err == nil {
		return p
	}
	if home, err := os.UserHomeDir(); err == nil {
		for _, p := range []string{
			filepath.Join(home, ".local", "bin", "uv"),
			filepath.Join(home, ".cargo", "bin", "uv"),
		} {
			if fileExists(p) {
				return p
			}
		}
	}
	return ""
}

func stopVisionWorker() {
	visionMutex.Lock()
	defer visionMutex.Unlock()

	if visionCmd != nil && visionCmd.Process != nil {
		pid := visionCmd.Process.Pid
		_ = syscall.Kill(-pid, syscall.SIGTERM) // Tout le groupe (uv + python)
		select {
		case <-visionDone:
		case <-time.After(3 * time.Second):
			_ = syscall.Kill(-pid, syscall.SIGKILL)
			<-visionDone
		}
		fmt.Printf("[VISION] Processus vision_worker (PID: %d) arrêté\n", pid)
		visionCmd = nil
	}
}

// À appeler sous visionMutex
func visionAlive() bool {
	if visionCmd == nil || visionCmd.Process == nil {
		return false
	}
	select {
	case <-visionDone:
		return false
	default:
		return true
	}
}

func isVisionWorkerRunning() (bool, int) {
	visionMutex.Lock()
	defer visionMutex.Unlock()

	if visionAlive() {
		return true, visionCmd.Process.Pid
	}
	return false, 0
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

	var validStratNameRegex = regexp.MustCompile(`^[a-zA-Z0-9_\-]+$`)

	sanitizeStratName := func(raw string) (string, error) {
		name := strings.TrimSpace(raw)
		name = strings.TrimSuffix(name, ".xml")
		name = strings.TrimSuffix(name, ".py")
		name = filepath.Base(name) // Supprime tout composant de chemin ../ ou /
		if name == "" || name == "." || name == ".." || !validStratNameRegex.MatchString(name) {
			return "", fmt.Errorf("nom de stratégie invalide (alphanuémrique, '-' et '_' uniquement)")
		}
		return name, nil
	}

	app.Get("/api/load_strat/:name", func(c *fiber.Ctx) error {
		cleanName, err := sanitizeStratName(c.Params("name"))
		if err != nil {
			return c.Status(400).JSON(fiber.Map{"status": "error", "message": err.Error()})
		}
		strategiesDir := filepath.Clean(filepath.Join(findRaspPath(), "strat", "strategies"))
		targetPath := filepath.Clean(filepath.Join(strategiesDir, cleanName+".xml"))
		if !strings.HasPrefix(targetPath, strategiesDir+string(filepath.Separator)) {
			return c.Status(403).JSON(fiber.Map{"status": "error", "message": "accès interdit"})
		}
		content, err := os.ReadFile(targetPath)
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
		cleanName, err := sanitizeStratName(body["filename"])
		if err != nil {
			return c.Status(400).JSON(fiber.Map{"status": "error", "message": err.Error()})
		}
		strategiesDir := filepath.Clean(filepath.Join(findRaspPath(), "strat", "strategies"))
		basePath := filepath.Clean(filepath.Join(strategiesDir, cleanName))
		if !strings.HasPrefix(basePath, strategiesDir+string(filepath.Separator)) {
			return c.Status(403).JSON(fiber.Map{"status": "error", "message": "accès interdit"})
		}
		_ = os.MkdirAll(strategiesDir, 0755)
		err1 := os.WriteFile(basePath+".xml", []byte(body["xml"]), 0644)
		err2 := os.WriteFile(basePath+".py", []byte(body["code"]), 0644)
		if err1 != nil || err2 != nil {
			return c.Status(500).JSON(fiber.Map{"status": "error"})
		}

		// Envoi direct au robot : il rescanne strat/strategies chaque seconde, pas de redémarrage.
		// Best effort : robot éteint = sauvegarde quand même OK sur la base.
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		raspIP := resolveRaspIP()
		scpCmd := exec.CommandContext(ctx, "scp", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
			basePath+".xml", basePath+".py", fmt.Sprintf("eirbot@%s:Documents/robot_stk/strat/strategies/", raspIP))
		if out, err := scpCmd.CombinedOutput(); err != nil {
			fmt.Printf("[STRAT] Envoi de %s au robot (%s) impossible : %v %s\n", cleanName, raspIP, err, strings.TrimSpace(string(out)))
			return c.JSON(fiber.Map{"status": "success", "robot": false})
		}
		return c.JSON(fiber.Map{"status": "success", "robot": true})
	})

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

	// --- Routes Vision Zénithale USB (PC Base) ---
	app.Get("/api/stream_usb", func(c *fiber.Ctx) error {
		globalState.Lock()
		srvIP := globalState.ServerIP
		globalState.Unlock()
		if srvIP == "" || srvIP == "127.0.0.1" {
			srvIP = c.Hostname()
		}
		qs := string(c.Request().URI().QueryString())
		target := fmt.Sprintf("http://%s:8082/stream", srvIP)
		if qs != "" {
			target += "?" + qs
		}
		return c.Redirect(target)
	})

	app.Get("/api/vision/status", func(c *fiber.Ctx) error {
		running, pid := isVisionWorkerRunning()
		return c.JSON(fiber.Map{
			"running": running,
			"pid":     pid,
		})
	})

	app.Post("/api/vision/start", func(c *fiber.Ctx) error {
		pid, err := startVisionWorker()
		if err != nil {
			return c.Status(500).JSON(fiber.Map{"status": "error", "msg": err.Error()})
		}
		return c.JSON(fiber.Map{"status": "ok", "pid": pid})
	})

	app.Post("/api/vision/stop", func(c *fiber.Ctx) error {
		stopVisionWorker()
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/vision/toggle", func(c *fiber.Ctx) error {
		running, _ := isVisionWorkerRunning()
		if running {
			stopVisionWorker()
			return c.JSON(fiber.Map{"status": "stopped", "running": false})
		} else {
			pid, err := startVisionWorker()
			if err != nil {
				return c.Status(500).JSON(fiber.Map{"status": "error", "msg": err.Error()})
			}
			return c.JSON(fiber.Map{"status": "started", "running": true, "pid": pid})
		}
	})

	app.All("/api/vision/resolution", func(c *fiber.Ctx) error {
		mode := c.Query("mode")
		target := "http://127.0.0.1:8082/api/toggle_resolution"
		if mode != "" {
			target += "?mode=" + mode
		}
		client := http.Client{Timeout: 2 * time.Second}
		resp, err := client.Get(target)
		if err != nil {
			return c.Status(502).JSON(fiber.Map{"status": "error", "msg": "vision_worker non joignable"})
		}
		defer resp.Body.Close()
		var res map[string]interface{}
		_ = json.NewDecoder(resp.Body).Decode(&res)
		return c.JSON(res)
	})

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

	// Route API pour mettre à jour le code Python de la Rasp depuis la base :
	// git pull (best effort) puis rsync de Rasp/ vers le robot et redémarrage du launcher
	app.Post("/api/update_rasp", func(c *fiber.Ctx) error {
		// Même verrou que le flash : les deux redémarrent des choses sur la Rasp
		if !flashMutex.TryLock() {
			return c.Status(409).JSON(fiber.Map{"status": "error", "msg": "Un flash ou une mise à jour est déjà en cours"})
		}
		defer flashMutex.Unlock()

		globalState.Lock()
		running := globalState.MatchRunning
		globalState.Unlock()
		if running {
			return c.Status(409).JSON(fiber.Map{"status": "error", "msg": "Match en cours : mise à jour refusée"})
		}

		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
		defer cancel()

		r := deployRaspCode(ctx, true, false, nil)
		if r.Step != "" {
			return c.JSON(fiber.Map{"status": "error", "step": r.Step, "msg": r.Msg, "output": r.Output})
		}
		return c.JSON(fiber.Map{"status": "ok", "msg": r.Msg, "files": r.Changed, "warning": r.Warning})
	})

	// Thème suivi par l'écran du robot (uitheme.go)
	setupUIThemeRoutes(app)

	// Windows Update : mises à jour du code depuis GitHub (winupdate.go)
	setupUpdateRoutes(app)

	// Route API pour flasher les ESPs (Motor / Actionneurs) depuis la base déportée via la Raspberry Pi
	app.Post("/api/flash_esp/:target", func(c *fiber.Ctx) error {
		// Un seul flash à la fois : deux pio/esptool en parallèle sur le même port série échouent
		if !flashMutex.TryLock() {
			return c.Status(409).JSON(fiber.Map{"status": "error", "msg": "Un flash est déjà en cours"})
		}
		defer flashMutex.Unlock()
		// Borne la durée totale (compilation + ssh + flash) pour ne pas bloquer le handler indéfiniment
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
		defer cancel()

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
		projectRoot := findProjectRoot()

		// 2. Détermination du chemin vers le binaire pio (cf. settings.go)
		pioPath := findPio()

		// 3. Compilation avec PlatformIO pour l'environnement demandé
		fmt.Printf("[FLASH] Démarrage compilation PlatformIO pour '%s' dans %s...\n", envName, projectRoot)
		buildCmd := exec.CommandContext(ctx, pioPath, "run", "-e", envName)
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
		raspIP := resolveRaspIP()

		// 5. Transfert des binaires (.bin) vers la Rasp
		remoteDir := fmt.Sprintf("/tmp/esp_flash/%s", envName)
		mkdirCmd := exec.CommandContext(ctx, "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
			robotTarget(raspIP), fmt.Sprintf("mkdir -p %s", remoteDir))
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
		scpArgs = append(scpArgs, fmt.Sprintf("%s:%s/", robotTarget(raspIP), remoteDir))
		scpCmd := exec.CommandContext(ctx, "scp", scpArgs...)
		if out, err := scpCmd.CombinedOutput(); err != nil {
			return c.JSON(fiber.Map{
				"status": "error",
				"step":   "scp",
				"msg":    fmt.Sprintf("Erreur lors de la copie des binaires vers la Rasp: %v", err),
				"output": string(out),
			})
		}

		// 6. Libération du port série sur la Rasp (fuser -k pour libérer main_robot.py si actif)
		freeCmd := exec.CommandContext(ctx, "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
			robotTarget(raspIP), fmt.Sprintf("sudo fuser -k %s 2>/dev/null; sleep 0.5", serialPort))
		_ = freeCmd.Run()

		// 7. Flashage via esptool.py sur la Raspberry Pi
		flashScript := fmt.Sprintf(
			"python3 %s --chip esp32 --port %s --baud 460800 write_flash -z "+
				"--flash_mode dio --flash_freq 40m --flash_size 4MB "+
				"0x1000 %s/bootloader.bin 0x8000 %s/partitions.bin 0x10000 %s/firmware.bin",
			robotEsptool, serialPort, remoteDir, remoteDir, remoteDir,
		)

		fmt.Printf("[FLASH] Envoi de la commande de flash sur la Rasp (%s sur %s)...\n", envName, serialPort)
		flashCmd := exec.CommandContext(ctx, "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=30",
			robotTarget(raspIP), flashScript)
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
