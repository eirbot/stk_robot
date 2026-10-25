package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/gofiber/fiber/v2"
)

// Worker de vision zénithale (caméra USB de la base) : lancement, arrêt, flux

var (
	visionCmd   *exec.Cmd
	visionDone  chan struct{} // Fermé quand le worker se termine
	visionMutex sync.Mutex
)

// Modèles MuJoCo (export Onshape) du sous-module vision_deporte ; "" s'il n'est pas récupéré
func mujocoModelsDir() string {
	dir := findVisionDir()
	if dir == "" {
		return ""
	}
	models := filepath.Join(dir, "vision_deporte", "src", "vision_deporte", "models")
	if !fileExists(filepath.Join(models, "table", "table.xml")) {
		return ""
	}
	return models
}

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

func setupVisionRoutes(app *fiber.App) {
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
}
