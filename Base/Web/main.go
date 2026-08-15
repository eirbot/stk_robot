package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"

	"github.com/gofiber/fiber/v2"
	zmq "github.com/pebbe/zmq4"
)

func findRaspPath() string {
	paths := []string{
		"../../Rasp", // Si exécuté depuis Base/Web/
		"Rasp",       // Si exécuté depuis la racine du projet
	}
	for _, p := range paths {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return "../../Rasp" // Par défaut
}

func loadConfig() map[string]interface{} {
	path := findRaspPath() + "/config.json"
	content, err := os.ReadFile(path)
	if err != nil {
		log.Printf("Impossible de lire config.json à l'adresse %s : %v", path, err)
		return make(map[string]interface{})
	}
	var cfg map[string]interface{}
	if err := json.Unmarshal(content, &cfg); err != nil {
		log.Printf("Impossible de décoder config.json : %v", err)
		return make(map[string]interface{})
	}
	return cfg
}

func main() {
	// Charger la configuration globale
	globalState.Lock()
	globalState.Config = loadConfig()
	if t, ok := globalState.Config["team"].(string); ok {
		globalState.Team = t
	}
	globalState.Unlock()

	// Initialisation du canal descendant ZMQ PUB (PC -> Robot)
	var err error
	zmqPublisher, err = zmq.NewSocket(zmq.PUB)
	if err != nil {
		log.Fatalf("Impossible de créer le socket ZMQ PUB : %v", err)
	}
	defer zmqPublisher.Close()
	
	err = zmqPublisher.Bind("tcp://*:5556")
	if err != nil {
		log.Fatalf("Impossible de lier le socket ZMQ PUB au port 5556 : %v", err)
	}
	fmt.Println("[ZMQ PUB] Canal d'ordres initialisé (Port 5556)...")

	// Lancement de l'écoute du robot en tâche de fond
	go pipelineReceptionRobot()

	app := fiber.New(fiber.Config{
		BodyLimit: 20 * 1024 * 1024, // Limite de 20 Mo pour le téléversement
	})

	// Configuration des routes (définies dans routes.go)
	setupRoutes(app)

	log.Fatal(app.Listen(":8080"))
}
