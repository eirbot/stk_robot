package main

import zmq "github.com/pebbe/zmq4"

var globalState = FullState{
	Team:     "BLEUE",
	TimerStr: "100.0",
	FsmState: "WAIT_START",
}

// Canaux internes Go pour dispatcher les messages
var chanToWeb = make(chan []byte, 100)
var zmqPublisher *zmq.Socket
