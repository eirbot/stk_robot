package main

import (
	"fmt"
	"log"

	"github.com/gofiber/fiber/v2"
	zmq "github.com/pebbe/zmq4"
)

func main() {
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

	app := fiber.New()

	// Configuration des routes (définies dans routes.go)
	setupRoutes(app)

	log.Fatal(app.Listen(":8080"))
}
