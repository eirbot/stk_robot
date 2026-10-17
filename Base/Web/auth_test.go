package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
)

func authTestApp(pin string) *fiber.App {
	auth.Lock()
	auth.pin = pin
	auth.sessions = map[string]time.Time{}
	auth.failures = map[string]int{}
	auth.lockedTo = map[string]time.Time{}
	auth.Unlock()
	app := fiber.New()
	app.Use("/api", authMiddleware)
	setupAuthRoutes(app)
	ok := func(c *fiber.Ctx) error { return c.JSON(fiber.Map{"status": "ok"}) }
	app.Post("/api/action/:act", ok)
	app.Get("/api/state", ok)
	return app
}

func do(t *testing.T, app *fiber.App, method, path, body, cookie string) *http.Response {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	if cookie != "" {
		req.Header.Set("Cookie", cookie)
	}
	resp, err := app.Test(req, -1)
	if err != nil {
		t.Fatal(err)
	}
	return resp
}

func TestSansPinToutEstLibre(t *testing.T) {
	app := authTestApp("")
	if r := do(t, app, "POST", "/api/action/start", "", ""); r.StatusCode != 200 {
		t.Fatalf("sans PIN : %d", r.StatusCode)
	}
}

func TestPinProtegeLesCommandes(t *testing.T) {
	app := authTestApp("4242")
	if r := do(t, app, "POST", "/api/action/start", "", ""); r.StatusCode != 401 {
		t.Fatalf("commande sans session : %d, attendu 401", r.StatusCode)
	}
	if r := do(t, app, "POST", "/api/action/stop", "", ""); r.StatusCode != 200 {
		t.Fatalf("STOP doit rester libre : %d", r.StatusCode)
	}
	if r := do(t, app, "GET", "/api/state", "", ""); r.StatusCode != 200 {
		t.Fatalf("lecture libre : %d", r.StatusCode)
	}
}

func TestLoginEtSession(t *testing.T) {
	app := authTestApp("4242")
	if r := do(t, app, "POST", "/api/login", `{"pin":"0000"}`, ""); r.StatusCode != 401 {
		t.Fatalf("mauvais PIN : %d", r.StatusCode)
	}
	r := do(t, app, "POST", "/api/login", `{"pin":"4242"}`, "")
	if r.StatusCode != 200 {
		t.Fatalf("bon PIN : %d", r.StatusCode)
	}
	var cookie string
	for _, c := range r.Cookies() {
		if c.Name == sessionCookie {
			cookie = c.Name + "=" + c.Value
			if !c.HttpOnly {
				t.Fatal("cookie de session non HttpOnly")
			}
		}
	}
	if cookie == "" {
		t.Fatal("pas de cookie de session")
	}
	if r := do(t, app, "POST", "/api/action/start", "", cookie); r.StatusCode != 200 {
		t.Fatalf("commande avec session : %d", r.StatusCode)
	}
	do(t, app, "POST", "/api/logout", "", cookie)
	if r := do(t, app, "POST", "/api/action/start", "", cookie); r.StatusCode != 401 {
		t.Fatalf("après déconnexion : %d", r.StatusCode)
	}
}

func TestBlocageApresErreurs(t *testing.T) {
	app := authTestApp("4242")
	for i := 0; i < maxPinFailures; i++ {
		do(t, app, "POST", "/api/login", `{"pin":"0000"}`, "")
	}
	if r := do(t, app, "POST", "/api/login", `{"pin":"4242"}`, ""); r.StatusCode != 429 {
		t.Fatalf("après %d erreurs : %d, attendu 429", maxPinFailures, r.StatusCode)
	}
}

func TestSessionExpiree(t *testing.T) {
	authTestApp("4242")
	auth.Lock()
	auth.sessions["vieux"] = time.Now().Add(-time.Minute)
	auth.Unlock()
	if validSession("vieux") {
		t.Fatal("une session expirée ne doit plus être valide")
	}
}
