package main

// Code PIN pour les actions sensibles de l'interface.
//
// - PIN défini par $STK_PIN ou le fichier Base/pin.txt (non versionné). Aucun PIN = protection
//   désactivée (pratique sur le PC de dev), avec un avertissement au démarrage.
// - Protégé : toutes les commandes POST /api/* (match, réglages, déplacements, actionneurs,
//   stratégies, flash, mise à jour, vision) et les commandes envoyées par WebSocket.
// - Toujours autorisé : la lecture (GET), STOP (sécurité), et les clients de confiance :
//   la base elle-même (loopback) et l'écran du robot (IP du robot).
// - PIN accepté -> cookie de session 12 h. 5 erreurs -> blocage 30 s de l'adresse.

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
)

const (
	sessionCookie   = "stk_session"
	sessionDuration = 12 * time.Hour
	maxPinFailures  = 5
	pinLockDuration = 30 * time.Second
)

// Commandes POST qui restent libres
var pinFreeRoutes = map[string]bool{
	"/api/login":            true,
	"/api/logout":           true,
	"/api/action/stop":      true, // sécurité : arrêter le robot ne doit jamais être bloqué
	"/api/speedtest/upload": true, // diagnostic réseau, sans effet
}

type authState struct {
	sync.Mutex
	pin      string
	sessions map[string]time.Time
	failures map[string]int
	lockedTo map[string]time.Time
}

var auth = authState{
	sessions: map[string]time.Time{},
	failures: map[string]int{},
	lockedTo: map[string]time.Time{},
}

func loadPin() string {
	if p := strings.TrimSpace(os.Getenv("STK_PIN")); p != "" {
		return p
	}
	if b, err := os.ReadFile("pin.txt"); err == nil {
		return strings.TrimSpace(string(b))
	}
	return ""
}

func initAuth() {
	auth.Lock()
	auth.pin = loadPin()
	auth.Unlock()
	if auth.pin == "" {
		fmt.Println("[AUTH] Aucun code PIN (STK_PIN ou Base/pin.txt) : actions sensibles NON protégées")
	} else {
		fmt.Println("[AUTH] Code PIN actif pour les actions sensibles")
	}
}

func pinRequired() bool {
	auth.Lock()
	defer auth.Unlock()
	return auth.pin != ""
}

func newToken() string {
	b := make([]byte, 32)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func validSession(token string) bool {
	if token == "" {
		return false
	}
	auth.Lock()
	defer auth.Unlock()
	exp, ok := auth.sessions[token]
	if ok && time.Now().After(exp) {
		delete(auth.sessions, token)
		return false
	}
	return ok
}

// trustedIP : la base elle-même et l'écran du robot n'ont pas besoin du PIN
func trustedIP(ip string) bool {
	parsed := net.ParseIP(ip)
	if parsed != nil && parsed.IsLoopback() {
		return true
	}
	return ip != "" && ip == resolveRaspIP()
}

func isTrusted(c *fiber.Ctx) bool {
	return !pinRequired() || validSession(c.Cookies(sessionCookie)) || trustedIP(c.IP())
}

// authMiddleware protège les commandes POST /api/*
func authMiddleware(c *fiber.Ctx) error {
	if c.Method() != fiber.MethodPost || pinFreeRoutes[c.Path()] || isTrusted(c) {
		return c.Next()
	}
	return c.Status(401).JSON(fiber.Map{"status": "error", "auth": true, "msg": "Code PIN requis"})
}

func setupAuthRoutes(app *fiber.App) {
	app.Get("/api/auth", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"required": pinRequired(), "ok": isTrusted(c)})
	})

	app.Post("/api/login", func(c *fiber.Ctx) error {
		var body struct {
			Pin string `json:"pin"`
		}
		_ = c.BodyParser(&body)
		ip := c.IP()

		auth.Lock()
		if until, locked := auth.lockedTo[ip]; locked && time.Now().Before(until) {
			wait := time.Until(until).Round(time.Second)
			auth.Unlock()
			return c.Status(429).JSON(fiber.Map{"status": "error", "msg": fmt.Sprintf("Trop d'essais : réessayer dans %v", wait)})
		}
		ok := auth.pin == "" || subtle.ConstantTimeCompare([]byte(body.Pin), []byte(auth.pin)) == 1
		if !ok {
			auth.failures[ip]++
			if auth.failures[ip] >= maxPinFailures {
				auth.lockedTo[ip] = time.Now().Add(pinLockDuration)
				auth.failures[ip] = 0
			}
			auth.Unlock()
			return c.Status(401).JSON(fiber.Map{"status": "error", "msg": "Code PIN incorrect"})
		}
		delete(auth.failures, ip)
		token := newToken()
		auth.sessions[token] = time.Now().Add(sessionDuration)
		auth.Unlock()

		c.Cookie(&fiber.Cookie{
			Name:     sessionCookie,
			Value:    token,
			Path:     "/",
			MaxAge:   int(sessionDuration.Seconds()),
			HTTPOnly: true,
			SameSite: "Strict",
		})
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Post("/api/logout", func(c *fiber.Ctx) error {
		auth.Lock()
		delete(auth.sessions, c.Cookies(sessionCookie))
		auth.Unlock()
		c.ClearCookie(sessionCookie)
		return c.JSON(fiber.Map{"status": "ok"})
	})
}
