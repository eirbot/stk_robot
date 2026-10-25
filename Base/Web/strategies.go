package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
)

// Stratégies Blockly : liste, lecture, sauvegarde (copiée aussi sur le robot)
func setupStrategyRoutes(app *fiber.App) {
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
}
