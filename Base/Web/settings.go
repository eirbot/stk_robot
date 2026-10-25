package main

// Réglages de déploiement regroupés : chemins du projet, outils, adresses du LAN et du robot.
// Chaque valeur peut être surchargée par une variable d'environnement (cf. Base/systemd/base_stk.service).

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

// Version du binaire, injectée par Base/build.sh : -ldflags "-X main.buildVersion=<commit>[-dirty] <date>"
var buildVersion = "dev"

var (
	// Robot (Raspberry Pi)
	robotUser       = envOr("STK_ROBOT_USER", "eirbot")
	robotDir        = envOr("STK_ROBOT_DIR", "Documents/robot_stk")    // Relatif au $HOME du robot
	robotEsptool    = envOr("STK_ROBOT_ESPTOOL", "esptool/esptool.py") // Relatif au $HOME du robot
	robotFallbackIP = envOr("STK_ROBOT_IP", "192.168.10.89")           // Si ni télémétrie ni bail DHCP

	// LAN de la base (dnsmasq)
	lanPrefix = envOr("STK_LAN_PREFIX", "192.168.10.")
	baseLanIP = envOr("STK_BASE_IP", "192.168.10.2")

	// Ports (autres valeurs : tests de bout en bout à côté d'une base déjà lancée).
	// Les mêmes variables STK_ZMQ_* sont lues par Rasp/ihm/zmq_client.py.
	httpPort     = envOr("STK_HTTP_PORT", "8080")
	zmqRobotPort = envOr("STK_ZMQ_ROBOT_PORT", "5555") // robot -> base (PULL)
	zmqBasePort  = envOr("STK_ZMQ_BASE_PORT", "5556")  // base -> robot (PUB)
	// base -> planificateur (PUB, Base/Planif/planif_worker.py)
	zmqPlanifPort = envOr("STK_ZMQ_PLANIF_PORT", "5557")
)

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func isProjectRoot(dir string) bool {
	return fileExists(filepath.Join(dir, "ESP", "platformio.ini")) && fileExists(filepath.Join(dir, "Rasp", "main_robot.py"))
}

// Projet PlatformIO des firmwares ESP32 (platformio.ini, src/, .pio/build/)
func espProjectDir() string { return filepath.Join(findProjectRoot(), "ESP") }

// Racine du dépôt stk_robot : $STK_PROJECT_ROOT, sinon on remonte depuis le binaire (Base/base_stk)
// puis depuis le dossier de travail jusqu'à trouver ESP/platformio.ini + Rasp/main_robot.py
func findProjectRoot() string {
	if p := os.Getenv("STK_PROJECT_ROOT"); p != "" {
		return p
	}
	var starts []string
	if exe, err := os.Executable(); err == nil {
		if real, err := filepath.EvalSymlinks(exe); err == nil {
			exe = real
		}
		starts = append(starts, filepath.Dir(exe))
	}
	if wd, err := os.Getwd(); err == nil {
		starts = append(starts, wd)
	}
	for _, dir := range starts {
		for {
			if isProjectRoot(dir) {
				return dir
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	// Dernier recours : on suppose un lancement depuis Base/
	p, _ := filepath.Abs("..")
	return p
}

// Binaire PlatformIO : $STK_PIO, sinon PATH, sinon emplacements usuels dans le $HOME
func findPio() string {
	if p := os.Getenv("STK_PIO"); p != "" {
		return p
	}
	if p, err := exec.LookPath("pio"); err == nil {
		return p
	}
	if home, err := os.UserHomeDir(); err == nil {
		for _, p := range []string{
			filepath.Join(home, ".platformio", "penv", "bin", "pio"),
			filepath.Join(home, ".local", "bin", "pio"),
		} {
			if fileExists(p) {
				return p
			}
		}
	}
	return "pio"
}

// Destination ssh du robot (user@ip)
func robotTarget(ip string) string {
	return robotUser + "@" + ip
}

// Contenu du fichier VERSION écrit sur le robot (même format que tools/deploy.sh) :
//
//	commit=<sha court>[-dirty]   (dirty = modifs locales dans Rasp/, config.json exclu car non déployé)
//	date=<date ISO 8601>
//	source=<machine qui a poussé>
func raspVersionFile(root string) string {
	commit := "inconnu"
	if out, err := exec.Command("git", "-C", root, "rev-parse", "--short", "HEAD").Output(); err == nil {
		commit = strings.TrimSpace(string(out))
		st, err := exec.Command("git", "-C", root, "status", "--porcelain", "--", "Rasp", ":!Rasp/config.json").Output()
		if err == nil && len(strings.TrimSpace(string(st))) > 0 {
			commit += "-dirty"
		}
	}
	host, _ := os.Hostname()
	return fmt.Sprintf("commit=%s\ndate=%s\nsource=%s\n", commit, time.Now().Format(time.RFC3339), host)
}
