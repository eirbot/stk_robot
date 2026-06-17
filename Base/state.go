package main

import (
	"sync"

	"github.com/gofiber/websocket/v2"
	zmq "github.com/pebbe/zmq4"
)

var globalState = FullState{
	Team:     "BLEUE",
	TimerStr: "100.0",
	FsmState: "WAIT_START",
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
