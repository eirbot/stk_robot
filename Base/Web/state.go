package main

import (
	"net"
	"strings"
	"sync"

	"github.com/gofiber/websocket/v2"
	zmq "github.com/pebbe/zmq4"
)

func getHostIP() string {
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err == nil {
		defer conn.Close()
		localAddr := conn.LocalAddr().(*net.UDPAddr)
		ip := localAddr.IP.String()
		if ip != "" && !strings.HasPrefix(ip, "127.") {
			return ip
		}
	}

	ifaces, err := net.Interfaces()
	if err == nil {
		for _, iface := range ifaces {
			if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
				continue
			}
			if strings.HasPrefix(iface.Name, "docker") || strings.HasPrefix(iface.Name, "veth") || strings.HasPrefix(iface.Name, "br-") {
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
				if ip != nil {
					return ip.String()
				}
			}
		}
	}
	return "127.0.0.1"
}

var globalState = FullState{
	Team:     "BLEUE",
	TimerStr: "100.0",
	FsmState: "WAIT_START",
	ServerIP: getHostIP(),
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
