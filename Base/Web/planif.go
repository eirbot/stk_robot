package main

// Planificateur de trajectoire sur la base (Base/Planif/planif_worker.py, processus Python).
//
// Le planificateur reçoit par une prise PUB dédiée (zmqPlanifPort, le robot ne l'écoute pas) tout
// ce qu'il lui faut : caméra zénithale (pose du robot, adversaires, pierres), télémétrie du robot,
// points LiDAR et demandes de navigation (nav_*). Il répond sur la prise PULL commune (5555) par
// des messages « plan », relayés au robot et aux pages (carte 3D). Lancé et relancé par base_stk.

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	zmq "github.com/pebbe/zmq4"
)

var (
	planifPublisher *zmq.Socket
	planifPubMutex  sync.Mutex
)

func initPlanifPublisher() error {
	sock, err := zmq.NewSocket(zmq.PUB)
	if err != nil {
		return err
	}
	if err := sock.Bind("tcp://*:" + zmqPlanifPort); err != nil {
		sock.Close()
		return err
	}
	planifPublisher = sock
	fmt.Printf("[ZMQ PUB] Canal du planificateur initialisé (Port %s)\n", zmqPlanifPort)
	return nil
}

// envoyerAuPlanif : données brutes (json.RawMessage) ou structure, sans bloquer
func envoyerAuPlanif(msgType string, data interface{}) {
	planifPubMutex.Lock()
	defer planifPubMutex.Unlock()
	if planifPublisher == nil {
		return
	}
	packet, err := json.Marshal(map[string]interface{}{"type": msgType, "data": data})
	if err != nil {
		return
	}
	_, _ = planifPublisher.Send(string(packet), zmq.DONTWAIT)
}

// Messages du robot utiles au planificateur (en plus de vision_update et telemetry)
func pourLePlanif(msgType string) bool {
	switch msgType {
	case "lidar_frame", "nav_demande", "nav_fin":
		return true
	}
	return false
}

// Messages qui ne viennent pas du robot (ne le marquent pas « en ligne »)
func messageDeLaBase(msgType string) bool {
	return msgType == "vision_update" || msgType == "plan" || msgType == "carte_planif"
}

// superviserPlanif lance le worker et le relance s'il s'arrête (STK_NO_PLANIF=1 : pas de lancement)
func superviserPlanif() {
	if os.Getenv("STK_NO_PLANIF") != "" {
		return
	}
	root := findProjectRoot()
	script := filepath.Join(root, "Base", "Planif", "planif_worker.py")
	if !fileExists(script) {
		fmt.Printf("[PLANIF] %s introuvable : pas de planificateur sur la base\n", script)
		return
	}
	for {
		var cmd *exec.Cmd
		if uv := findUv(); uv != "" {
			cmd = exec.Command(uv, "run", "--project", root, "python", script)
		} else {
			cmd = exec.Command("python3", script)
		}
		cmd.Dir = root
		cmd.Env = append(os.Environ(),
			"STK_ZMQ_ROBOT_PORT="+zmqRobotPort, "STK_ZMQ_PLANIF_PORT="+zmqPlanifPort)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true, Pdeathsig: syscall.SIGTERM}
		debut := time.Now()
		if err := cmd.Start(); err != nil {
			fmt.Printf("[PLANIF] Lancement impossible : %v\n", err)
		} else {
			fmt.Printf("[PLANIF] 🚀 Planificateur démarré (PID %d)\n", cmd.Process.Pid)
			err = cmd.Wait()
			fmt.Printf("[PLANIF] Planificateur arrêté (%v)\n", err)
		}
		// Plantage au démarrage : on n'insiste pas en boucle serrée
		if time.Since(debut) < 10*time.Second {
			time.Sleep(10 * time.Second)
		} else {
			time.Sleep(2 * time.Second)
		}
	}
}
