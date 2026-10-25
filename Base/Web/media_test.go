package main

import "testing"

func TestLedCommand(t *testing.T) {
	ok := map[[2]string]string{
		{"color", "255,0,10"}: "COLOR:255,0,10",
		{"color", "OFF"}:      "OFF",
		{"color", "0,0,0"}:    "OFF",
		{"pixel", "12,1,2,3"}: "PIXEL:12,1,2,3",
	}
	for in, want := range ok {
		if got, err := ledCommand(in[0], in[1]); err != nil || got != want {
			t.Errorf("ledCommand(%q, %q) = %q, %v ; attendu %q", in[0], in[1], got, err, want)
		}
	}
	for _, in := range [][2]string{{"color", "rouge"}, {"color", "1,2"}, {"pixel", "1,2,3"}, {"anim", "x"}, {"color", "1,2,3\nOFF"}} {
		if got, err := ledCommand(in[0], in[1]); err == nil {
			t.Errorf("ledCommand(%q, %q) = %q : refus attendu", in[0], in[1], got)
		}
	}
}

func TestNomsDeFichiers(t *testing.T) {
	for _, n := range []string{"intro.mp3", "fin de match.mp3", "son-2_b.mp3"} {
		if !validAudioName.MatchString(n) {
			t.Errorf("%q refusé", n)
		}
	}
	for _, n := range []string{"../x.mp3", "a/b.mp3", "x.wav", ".mp3x"} {
		if validAudioName.MatchString(n) {
			t.Errorf("%q accepté", n)
		}
	}
	if !validLogName.MatchString("blackbox_2026-10-25_14-03-12.csv") || validLogName.MatchString("../../etc/passwd") {
		t.Error("filtre des noms de journaux")
	}
}
