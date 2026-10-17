package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/compress"
	"github.com/gofiber/fiber/v2/middleware/recover"
	zmq "github.com/pebbe/zmq4"
)

func findRaspPath() string {
	paths := []string{
		// Relatif au binaire ou à $STK_PROJECT_ROOT (cf. settings.go)
		filepath.Join(findProjectRoot(), "Rasp"),
		"../Rasp",    // Si exécuté depuis Base/
		"../../Rasp", // Si exécuté depuis Base/Web/
		"Rasp",       // Si exécuté depuis la racine du projet
	}
	for _, p := range paths {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}
	return "../Rasp" // Par défaut
}

func main() {
	// Charger la configuration globale
	globalState.Lock()
	globalState.ServerIP = getHostIP()
	globalState.Config = loadConfig()
	if t, ok := globalState.Config["team"].(string); ok {
		globalState.Team = t
	}
	dhcpIP := getRaspIPFromDHCP()
	if dhcpIP != "" {
		globalState.Telemetry.RaspIP = dhcpIP
	}
	globalState.Unlock()
	fmt.Printf("[VERSION] base_stk %s (projet : %s)\n", buildVersion, findProjectRoot())
	fmt.Printf("[NET] Base Déportée joignable sur : http://%s:%s\n", globalState.ServerIP, httpPort)
	if dhcpIP != "" {
		fmt.Printf("[NET] IP Robot détectée via DHCP : %s\n", dhcpIP)
	}

	// Surveillance périodique des baux DHCP pour détecter le robot automatiquement
	go func() {
		for {
			time.Sleep(3 * time.Second)
			ip := getRaspIPFromDHCP()
			if ip != "" {
				globalState.Lock()
				if globalState.Telemetry.RaspIP != ip {
					globalState.Telemetry.RaspIP = ip
					packet, _ := json.Marshal(map[string]interface{}{
						"type": "state_update",
						"data": &globalState,
					})
					globalHub.Broadcast(packet)
				}
				globalState.Unlock()
			}
		}
	}()

	// Initialisation du canal descendant ZMQ PUB (PC -> Robot)
	var err error
	zmqPublisher, err = zmq.NewSocket(zmq.PUB)
	if err != nil {
		log.Fatalf("Impossible de créer le socket ZMQ PUB : %v", err)
	}
	defer zmqPublisher.Close()
	
	err = zmqPublisher.Bind("tcp://*:" + zmqBasePort)
	if err != nil {
		log.Fatalf("Impossible de lier le socket ZMQ PUB au port %s : %v", zmqBasePort, err)
	}
	fmt.Printf("[ZMQ PUB] Canal d'ordres initialisé (Port %s)...\n", zmqBasePort)

	// Lancement de l'écoute du robot en tâche de fond
	go pipelineReceptionRobot()
	go watchRobotLink()

	// Démarrage automatique du module de vision si la caméra USB est branchée
	// STK_NO_VISION=1 : pas de démarrage auto de la caméra (tests, PC de dev avec webcam)
	if _, err := os.Stat("/dev/video0"); err == nil && os.Getenv("STK_NO_VISION") == "" {
		go func() {
			time.Sleep(1 * time.Second) // Attente de l'ouverture des sockets ZMQ
			_, _ = startVisionWorker()
		}()
	}

	app := fiber.New(fiber.Config{
		BodyLimit: 20 * 1024 * 1024, // Limite de 20 Mo pour le téléversement
	})

	// 6. Middleware recover pour empêcher tout plantage du serveur en cas de panique dans une route
	app.Use(recover.New())

	// Compression automatique (Gzip / Brotli / Deflate) de tous les flux HTTP (HTML, CSS, JS, JSON)
	// Réduit drastiquement la taille des premiers paquets transmis au navigateur
	app.Use(compress.New(compress.Config{
		Level: compress.LevelBestSpeed,
	}))

	// Configuration des routes (définies dans routes.go)
	initAuth()
	setupRoutes(app)

	if httpPort == "8080" {
		go redirectPort80()
	}

	log.Fatal(app.Listen(":" + httpPort))
}

// http://stk.eirbot (port 80) -> http://stk.eirbot:8080, pour ne pas avoir à taper le port.
// Le port 80 demande net.ipv4.ip_unprivileged_port_start <= 80 (cf. Base/setup_dns.sh) : sinon on s'en passe.
func redirectPort80() {
	ln, err := net.Listen("tcp", ":80")
	if err != nil {
		fmt.Printf("[NET] Port 80 indisponible (%v) : interface seulement sur :8080\n", err)
		return
	}
	fmt.Println("[NET] Redirection http://<base>:80 -> :8080 active")
	_ = http.Serve(ln, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.Host)
		if err != nil {
			host = r.Host
		}
		http.Redirect(w, r, "http://"+host+":8080"+r.URL.RequestURI(), http.StatusFound)
	}))
}
