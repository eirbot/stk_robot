package main

import (
	"encoding/json"
	"os"
	"strings"
	"testing"
)

func TestUITheme(t *testing.T) {
	wd, _ := os.Getwd()
	if err := os.Chdir(t.TempDir()); err != nil { // ui_theme.txt écrit dans le dossier courant
		t.Fatal(err)
	}
	defer os.Chdir(wd)

	app := authTestApp("1234") // PIN actif : le thème doit rester libre
	setupUIThemeRoutes(app)

	get := func() string {
		var b struct{ Theme string }
		_ = json.NewDecoder(do(t, app, "GET", "/api/ui_theme", "", "").Body).Decode(&b)
		return b.Theme
	}
	if got := get(); got != "stk" {
		t.Fatalf("thème par défaut : %q", got)
	}
	if r := do(t, app, "POST", "/api/ui_theme", `{"theme":"win95"}`, ""); r.StatusCode != 200 {
		t.Fatalf("thème refusé sans PIN : %d", r.StatusCode)
	}
	if got := get(); got != "win95" {
		t.Fatalf("thème non retenu : %q", got)
	}
	if b, _ := os.ReadFile(uiThemeFile); strings.TrimSpace(string(b)) != "win95" {
		t.Fatalf("thème non enregistré : %q", b)
	}
	if r := do(t, app, "POST", "/api/ui_theme", `{"theme":"rose"}`, ""); r.StatusCode != 400 {
		t.Fatalf("thème inconnu accepté : %d", r.StatusCode)
	}
	// Relu au redémarrage
	loadUITheme()
	if got := get(); got != "win95" {
		t.Fatalf("thème perdu au redémarrage : %q", got)
	}
}
