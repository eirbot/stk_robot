package main

import (
	"context"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
)

// Sérialise les flashs ESP (route /api/flash_esp)
var flashMutex sync.Mutex

// Mise à jour du code de la Rasp et flash des ESP32 depuis la base
func setupFlashRoutes(app *fiber.App) {
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

		// 1. Projet PlatformIO (ESP/platformio.ini)
		espDir := espProjectDir()

		// 2. Détermination du chemin vers le binaire pio (cf. settings.go)
		pioPath := findPio()

		// 3. Compilation avec PlatformIO pour l'environnement demandé
		fmt.Printf("[FLASH] Démarrage compilation PlatformIO pour '%s' dans %s...\n", envName, espDir)
		buildCmd := exec.CommandContext(ctx, pioPath, "run", "-e", envName)
		buildCmd.Dir = espDir
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

		localBinPattern := filepath.Join(espDir, ".pio", "build", envName, "*.bin")
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
}
