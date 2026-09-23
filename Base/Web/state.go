package main

import (
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"

	"github.com/gofiber/websocket/v2"
	zmq "github.com/pebbe/zmq4"
)

func getRaspIPFromDHCP() string {
	candidatePaths := []string{
		"/var/lib/misc/dnsmasq.leases",
		"/var/lib/dnsmasq/dnsmasq.leases",
		"/tmp/dnsmasq.leases",
	}

	matches, _ := filepath.Glob("/var/lib/NetworkManager/*.leases")
	candidatePaths = append(candidatePaths, matches...)

	for _, p := range candidatePaths {
		data, err := os.ReadFile(p)
		if err != nil {
			continue
		}
		lines := strings.Split(string(data), "\n")
		var bestIP string
		for i := len(lines) - 1; i >= 0; i-- {
			line := strings.TrimSpace(lines[i])
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			parts := strings.Fields(line)
			if len(parts) >= 4 {
				ip := parts[2]
				hostname := strings.ToLower(parts[3])
				if strings.Contains(hostname, "rasp") || strings.Contains(hostname, "robot") {
					return ip
				}
				if strings.HasPrefix(ip, "192.168.10.") && ip != "192.168.10.2" && bestIP == "" {
					bestIP = ip
				}
			}
		}
		if bestIP != "" {
			return bestIP
		}
	}

	// Fallback : journalctl pour les logs dhcp
	out, err := exec.Command("journalctl", "-t", "dnsmasq-dhcp", "-n", "30", "--no-pager").Output()
	if err == nil {
		lines := strings.Split(string(out), "\n")
		for i := len(lines) - 1; i >= 0; i-- {
			line := lines[i]
			if strings.Contains(line, "DHCPACK") && (strings.Contains(strings.ToLower(line), "rasp") || strings.Contains(line, "192.168.10.")) {
				fields := strings.Fields(line)
				for _, f := range fields {
					if strings.HasPrefix(f, "192.168.10.") && f != "192.168.10.2" {
						return f
					}
				}
			}
		}
	}

	return ""
}

func getHostIP() string {
	ifaces, err := net.Interfaces()
	if err == nil {
		var ip192_10 string
		var ip192 string
		var ipOther string

		for _, iface := range ifaces {
			if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
				continue
			}
			name := strings.ToLower(iface.Name)
			if strings.HasPrefix(name, "docker") || strings.HasPrefix(name, "veth") || strings.HasPrefix(name, "br-") {
				continue
			}
			addrs, err := iface.Addrs()
			if err != nil {
				continue
			}
			for _, addr := range addrs {
				var ip net.IP
				switch v := addr.(type) {
				case *net.IPNet:
					ip = v.IP
				case *net.IPAddr:
					ip = v.IP
				}
				if ip == nil || ip.IsLoopback() {
					continue
				}
				ip = ip.To4()
				if ip == nil {
					continue
				}
				ipStr := ip.String()
				if strings.HasPrefix(ipStr, "192.168.10.") {
					ip192_10 = ipStr
				} else if strings.HasPrefix(ipStr, "192.168.") {
					ip192 = ipStr
				} else if ipOther == "" {
					ipOther = ipStr
				}
			}
		}

		if ip192_10 != "" {
			return ip192_10
		}
		if ip192 != "" {
			return ip192
		}
		if ipOther != "" {
			return ipOther
		}
	}

	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err == nil {
		defer conn.Close()
		localAddr := conn.LocalAddr().(*net.UDPAddr)
		ip := localAddr.IP.String()
		if ip != "" && !strings.HasPrefix(ip, "127.") {
			return ip
		}
	}

	return "127.0.0.1"
}

var globalState = FullState{
	Team:     "BLEUE",
	TimerStr: "100.0",
	FsmState: "WAIT_START",
	ServerIP: getHostIP(),
	Telemetry: RobotTelemetry{
		RaspIP: getRaspIPFromDHCP(),
	},
}

type Hub struct {
	sync.Mutex
	clients map[*websocket.Conn]chan []byte
}

var globalHub = Hub{
	clients: make(map[*websocket.Conn]chan []byte),
}

func (h *Hub) Broadcast(msg []byte) {
	h.Lock()
	defer h.Unlock()
	for _, ch := range h.clients {
		select {
		case ch <- msg:
		default:
		}
	}
}

var zmqPublisher *zmq.Socket
