package main

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

func git(t *testing.T, dir string, args ...string) string {
	t.Helper()
	cmd := exec.Command("git", append([]string{"-C", dir}, args...)...)
	cmd.Env = append(os.Environ(), "GIT_AUTHOR_NAME=test", "GIT_AUTHOR_EMAIL=t@t", "GIT_COMMITTER_NAME=test", "GIT_COMMITTER_EMAIL=t@t")
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v : %v\n%s", args, err, out)
	}
	return string(out)
}

func commitFile(t *testing.T, dir, name string) {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(p, []byte(name), 0o644); err != nil {
		t.Fatal(err)
	}
	git(t, dir, "add", name)
	git(t, dir, "commit", "-q", "-m", "ajout "+name)
}

func TestComputeUpdateStatus(t *testing.T) {
	if _, err := exec.LookPath("git"); err != nil {
		t.Skip("git absent")
	}
	defer func(v string) { buildVersion = v }(buildVersion)
	tmp := t.TempDir()
	remote, base, dev := filepath.Join(tmp, "remote.git"), filepath.Join(tmp, "base"), filepath.Join(tmp, "dev")
	git(t, tmp, "init", "-q", "--bare", "-b", "main", remote)
	git(t, tmp, "clone", "-q", remote, dev)
	commitFile(t, dev, "README")
	git(t, dev, "push", "-q", "origin", "HEAD:main")
	git(t, tmp, "clone", "-q", remote, base)

	ctx := context.Background()
	head := func() string { return git(t, base, "rev-parse", "--short", "HEAD")[:7] }

	// À jour : binaire et robot au même commit que le dépôt
	buildVersion = head() + " 2026-10-19T00:00:00"
	globalState.Lock()
	globalState.RobotVersion = map[string]string{"commit": head()}
	globalState.Unlock()
	st := computeUpdateStatus(ctx, base)
	if st.Behind != 0 || st.Available != 0 || st.BaseOutdated || st.RobotOutdated {
		t.Fatalf("dépôt à jour mal vu : %+v", st)
	}

	// Deux commits distants (base + robot) : 2 mises à jour proposées
	commitFile(t, dev, "Base/Web/x.go")
	commitFile(t, dev, "Rasp/y.py")
	git(t, dev, "push", "-q", "origin", "HEAD:main")
	git(t, base, "fetch", "-q")
	st = computeUpdateStatus(ctx, base)
	if st.Behind != 2 || len(st.Commits) != 2 || !st.TouchesBase || !st.TouchesRobot || st.TouchesESP {
		t.Fatalf("retard mal vu : %+v", st)
	}
	if st.Available != 2 {
		t.Fatalf("2 mises à jour attendues, %d", st.Available)
	}
	if st.Commits[0].Subject != "ajout Rasp/y.py" {
		t.Fatalf("commit le plus récent d'abord : %+v", st.Commits)
	}

	// Après pull : dépôt à jour, mais binaire et robot en retard sur HEAD
	git(t, base, "pull", "-q", "--ff-only")
	st = computeUpdateStatus(ctx, base)
	if st.Behind != 0 || !st.BaseOutdated || !st.RobotOutdated || st.Available != 2 {
		t.Fatalf("versions déployées en retard mal vues : %+v", st)
	}

	// Version inconnue (binaire « dev », robot sans VERSION) : rien de proposé
	buildVersion = "dev"
	globalState.Lock()
	globalState.RobotVersion = nil
	globalState.Unlock()
	if st = computeUpdateStatus(ctx, base); st.Available != 0 {
		t.Fatalf("versions inconnues : rien à proposer, %+v", st)
	}
}

func TestSameCommit(t *testing.T) {
	cases := []struct {
		a, b string
		want bool
	}{
		{"abc1234", "abc1234", true},
		{"abc1234", "abc12345", true},
		{"abc1234", "def5678", false},
		{"", "abc1234", true},
	}
	for _, c := range cases {
		if got := sameCommit(c.a, c.b); got != c.want {
			t.Errorf("sameCommit(%q, %q) = %v", c.a, c.b, got)
		}
	}
	if commitOf("abc1234-dirty 2026-10-19") != "abc1234" || commitOf("dev") != "" {
		t.Error("commitOf")
	}
}
