package main

// « Windows Update » : mises à jour du code depuis le dépôt distant (GitHub).
//
// - Vérification : git fetch (au démarrage puis toutes les 15 min, hors match, et à la demande),
//   puis comparaison du dépôt de la base, du binaire qui tourne et du code du robot avec la
//   branche distante. GET /api/update/status (sans fetch) et GET /api/update/check (avec fetch).
// - Installation (POST /api/update/install, protégée par le PIN comme tout POST) : git pull
//   (cible « depot », toujours faite), puis robot (rsync de Rasp/, comme /api/update_rasp) et/ou base (Base/build.sh puis
//   redémarrage du service base_stk : la base se coupe elle-même, la page attend son retour).
//   Le journal se lit avec GET /api/update/job?since=N.

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gofiber/fiber/v2"
)

const updateCheckEvery = 15 * time.Minute

type updateCommit struct {
	Hash    string `json:"hash"`
	Author  string `json:"author"`
	Date    string `json:"date"`
	Subject string `json:"subject"`
}

type updateStatus struct {
	CheckedAt  time.Time      `json:"checked_at"`
	Online     bool           `json:"online"` // dernier git fetch réussi
	FetchError string         `json:"fetch_error,omitempty"`
	Branch     string         `json:"branch"`
	Upstream   string         `json:"upstream"`
	Head       string         `json:"head"`
	Behind     int            `json:"behind"` // commits distants pas encore récupérés
	Ahead      int            `json:"ahead"`  // commits locaux de la base pas poussés
	Dirty      bool           `json:"dirty"`  // fichiers suivis modifiés sur la base
	Commits    []updateCommit `json:"commits"`
	// Parties touchées par les commits distants
	TouchesBase  bool `json:"touches_base"`
	TouchesRobot bool `json:"touches_robot"`
	TouchesESP   bool `json:"touches_esp"`
	// Binaire de la base et code du robot par rapport au dépôt de la base (HEAD)
	BaseVersion   string `json:"base_version"`
	BaseOutdated  bool   `json:"base_outdated"`
	RobotCommit   string `json:"robot_commit"`
	RobotOutdated bool   `json:"robot_outdated"`
	Available     int    `json:"available"` // nombre de mises à jour proposées (base, robot)
}

type updateJob struct {
	Targets    []string  `json:"targets"`
	Lines      []string  `json:"lines"`
	Running    bool      `json:"running"`
	OK         bool      `json:"ok"`
	Error      string    `json:"error,omitempty"`
	Restarting bool      `json:"restarting"` // la base va redémarrer : attendre son retour
	Started    time.Time `json:"started"`
	Ended      time.Time `json:"ended,omitempty"`
}

var updates struct {
	sync.Mutex
	status   updateStatus
	fetching bool
	job      *updateJob
}

// git dans le dépôt du projet, sortie nettoyée
func gitOut(ctx context.Context, root string, args ...string) (string, error) {
	cmd := exec.CommandContext(ctx, "git", append([]string{"-C", root}, args...)...)
	out, err := cmd.CombinedOutput()
	return strings.TrimSpace(string(out)), err
}

// Commit d'une version « abc1234[-dirty] [date] » -> « abc1234 » (vide si inconnu)
func commitOf(v string) string {
	f := strings.Fields(v)
	if len(f) == 0 || f[0] == "dev" || f[0] == "inconnu" {
		return ""
	}
	return strings.TrimSuffix(f[0], "-dirty")
}

// Même commit, quelle que soit la longueur des sha courts
func sameCommit(a, b string) bool {
	if a == "" || b == "" {
		return true // inconnu : on ne propose rien
	}
	n := len(a)
	if len(b) < n {
		n = len(b)
	}
	return a[:n] == b[:n]
}

// État du dépôt (sans réseau) : branche, retard / avance, commits distants, versions déployées
func computeUpdateStatus(ctx context.Context, root string) updateStatus {
	var st updateStatus
	st.Branch, _ = gitOut(ctx, root, "rev-parse", "--abbrev-ref", "HEAD")
	st.Head, _ = gitOut(ctx, root, "rev-parse", "--short", "HEAD")
	if out, err := gitOut(ctx, root, "status", "--porcelain", "--untracked-files=no"); err == nil {
		st.Dirty = out != ""
	}
	if up, err := gitOut(ctx, root, "rev-parse", "--abbrev-ref", "@{u}"); err == nil {
		st.Upstream = up
		if out, err := gitOut(ctx, root, "rev-list", "--left-right", "--count", "HEAD...@{u}"); err == nil {
			if f := strings.Fields(out); len(f) == 2 {
				st.Ahead, _ = strconv.Atoi(f[0])
				st.Behind, _ = strconv.Atoi(f[1])
			}
		}
		if st.Behind > 0 {
			if out, err := gitOut(ctx, root, "log", "-n", "50", "--format=%h%x1f%an%x1f%cI%x1f%s", "HEAD..@{u}"); err == nil {
				for _, l := range strings.Split(out, "\n") {
					if f := strings.Split(l, "\x1f"); len(f) == 4 {
						st.Commits = append(st.Commits, updateCommit{Hash: f[0], Author: f[1], Date: f[2], Subject: f[3]})
					}
				}
			}
			if out, err := gitOut(ctx, root, "diff", "--name-only", "HEAD..@{u}"); err == nil {
				for _, f := range strings.Split(out, "\n") {
					switch {
					case strings.HasPrefix(f, "Base/"):
						st.TouchesBase = true
					case strings.HasPrefix(f, "Rasp/"):
						st.TouchesRobot = true
					case strings.HasPrefix(f, "src/"), strings.HasPrefix(f, "include/"), f == "platformio.ini":
						st.TouchesESP = true
					}
				}
			}
		}
	}

	st.BaseVersion = buildVersion
	st.BaseOutdated = !sameCommit(commitOf(buildVersion), st.Head)
	globalState.Lock()
	if globalState.RobotVersion != nil {
		st.RobotCommit = globalState.RobotVersion["commit"]
	}
	globalState.Unlock()
	st.RobotOutdated = !sameCommit(commitOf(st.RobotCommit), st.Head)

	if st.TouchesBase || st.BaseOutdated {
		st.Available++
	}
	if st.TouchesRobot || st.RobotOutdated {
		st.Available++
	}
	return st
}

// git fetch puis recalcul ; garde le résultat du dernier fetch si on ne fetch pas
func refreshUpdateStatus(fetch bool) updateStatus {
	root := findProjectRoot()
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	updates.Lock()
	prev := updates.status
	doFetch := fetch && !updates.fetching
	if doFetch {
		updates.fetching = true
	}
	updates.Unlock()

	online, fetchErr, checked := prev.Online, prev.FetchError, prev.CheckedAt
	if doFetch {
		// Pas de demande d'identifiants : sans clé ni accès, échouer tout de suite
		cmd := exec.CommandContext(ctx, "git", "-C", root, "fetch", "--quiet", "--prune")
		cmd.Env = append(os.Environ(), "GIT_TERMINAL_PROMPT=0", "GIT_SSH_COMMAND=ssh -o BatchMode=yes -o ConnectTimeout=8")
		out, err := cmd.CombinedOutput()
		online, fetchErr, checked = err == nil, "", time.Now()
		if err != nil {
			fetchErr = strings.TrimSpace(string(out))
			if fetchErr == "" {
				fetchErr = err.Error()
			}
		}
	}

	st := computeUpdateStatus(ctx, root)
	st.Online, st.FetchError, st.CheckedAt = online, fetchErr, checked

	updates.Lock()
	updates.status = st
	if doFetch {
		updates.fetching = false
	}
	updates.Unlock()
	return st
}

// Vérification périodique, jamais pendant un match
func startUpdateChecker() {
	go func() {
		time.Sleep(20 * time.Second) // laisser le réseau et le robot arriver
		for {
			globalState.Lock()
			running := globalState.MatchRunning
			globalState.Unlock()
			if !running {
				refreshUpdateStatus(true)
			}
			time.Sleep(updateCheckEvery)
		}
	}()
}

// --- Installation ---

func (j *updateJob) logf(format string, a ...interface{}) {
	line := fmt.Sprintf(format, a...)
	updates.Lock()
	j.Lines = append(j.Lines, line)
	updates.Unlock()
	fmt.Println("[UPDATE]", line)
}

// Lance une commande en recopiant sa sortie ligne par ligne dans le journal
func (j *updateJob) run(ctx context.Context, dir string, name string, args ...string) error {
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "GIT_TERMINAL_PROMPT=0")
	pr, pw := io.Pipe()
	cmd.Stdout, cmd.Stderr = pw, pw
	done := make(chan struct{})
	go func() {
		sc := bufio.NewScanner(pr)
		for sc.Scan() {
			j.logf("  %s", sc.Text())
		}
		close(done)
	}()
	err := cmd.Run()
	pw.Close()
	<-done
	return err
}

func runUpdateJob(j *updateJob, wantBase, wantRobot bool) {
	defer flashMutex.Unlock()
	root := findProjectRoot()
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()

	fail := func(msg string) {
		j.logf("ÉCHEC : %s", msg)
		updates.Lock()
		j.Running, j.OK, j.Error, j.Ended = false, false, msg, time.Now()
		updates.Unlock()
		refreshUpdateStatus(false)
	}

	j.logf("Téléchargement des mises à jour (git pull)…")
	if err := j.run(ctx, root, "git", "pull", "--ff-only", "--no-rebase"); err != nil {
		fail("git pull impossible (pas d'accès au dépôt, ou modifications locales sur la base)")
		return
	}

	if wantRobot {
		j.logf("Installation sur le robot (copie de Rasp/)…")
		r := deployRaspCode(ctx, false, j)
		if r.Step != "" {
			if out := strings.TrimSpace(r.Output); out != "" {
				for _, l := range strings.Split(out, "\n") {
					j.logf("  %s", l)
				}
			}
			fail(r.Msg)
			return
		}
		if r.Warning != "" {
			j.logf("Attention : %s", r.Warning)
		}
		j.logf("Robot : %s", r.Msg)
	}

	if wantBase {
		j.logf("Compilation du serveur de la base (Base/build.sh)…")
		if err := j.run(ctx, filepath.Join(root, "Base"), "./build.sh"); err != nil {
			fail("compilation de la base impossible : l'ancien serveur continue de tourner")
			return
		}
		if exec.Command("systemctl", "cat", "base_stk.service").Run() != nil {
			j.logf("Service base_stk non installé : relancer base_stk à la main pour utiliser la nouvelle version.")
		} else {
			j.logf("Redémarrage de la base (service base_stk)…")
			updates.Lock()
			j.Restarting = true
			j.Running, j.OK, j.Ended = false, true, time.Now()
			updates.Unlock()
			// Laisser la page lire « Restarting » avant que le service ne nous coupe
			time.Sleep(1500 * time.Millisecond)
			if out, err := exec.Command("sudo", "-n", "systemctl", "restart", "base_stk").CombinedOutput(); err != nil {
				updates.Lock()
				j.Restarting = false
				updates.Unlock()
				fail("redémarrage refusé (" + strings.TrimSpace(string(out)) + ") : sudo systemctl restart base_stk")
			}
			return
		}
	}

	j.logf("Terminé.")
	updates.Lock()
	j.Running, j.OK, j.Ended = false, true, time.Now()
	updates.Unlock()
	refreshUpdateStatus(false)
}

func setupUpdateRoutes(app *fiber.App) {
	app.Get("/api/update/status", func(c *fiber.Ctx) error {
		return c.JSON(refreshUpdateStatus(false))
	})

	// Vérification immédiate (git fetch) : sans effet sur le code, donc GET et sans PIN
	app.Get("/api/update/check", refuseDuringMatch, func(c *fiber.Ctx) error {
		return c.JSON(refreshUpdateStatus(true))
	})

	app.Post("/api/update/install", func(c *fiber.Ctx) error {
		var req struct {
			Targets []string `json:"targets"`
		}
		_ = c.BodyParser(&req)
		wantBase, wantRobot, wantRepo := false, false, false
		for _, t := range req.Targets {
			switch t {
			case "base":
				wantBase = true
			case "robot":
				wantRobot = true
			case "depot": // git pull seul (docs, outils...)
				wantRepo = true
			}
		}
		if !wantBase && !wantRobot && !wantRepo {
			return c.Status(400).JSON(fiber.Map{"status": "error", "msg": "Rien à installer (depot, base et/ou robot)"})
		}
		globalState.Lock()
		running := globalState.MatchRunning
		globalState.Unlock()
		if running {
			return c.Status(409).JSON(fiber.Map{"status": "error", "msg": "Match en cours : mise à jour refusée"})
		}
		// Même verrou que le flash ESP et /api/update_rasp ; libéré par runUpdateJob
		if !flashMutex.TryLock() {
			return c.Status(409).JSON(fiber.Map{"status": "error", "msg": "Une mise à jour ou un flash est déjà en cours"})
		}
		j := &updateJob{Running: true, Started: time.Now(), Targets: []string{"depot"}}
		if wantBase {
			j.Targets = append(j.Targets, "base")
		}
		if wantRobot {
			j.Targets = append(j.Targets, "robot")
		}
		updates.Lock()
		updates.job = j
		updates.Unlock()
		go runUpdateJob(j, wantBase, wantRobot)
		return c.JSON(fiber.Map{"status": "ok"})
	})

	// Journal de l'installation en cours (lignes à partir de ?since=N)
	app.Get("/api/update/job", func(c *fiber.Ctx) error {
		since := c.QueryInt("since", 0)
		updates.Lock()
		defer updates.Unlock()
		j := updates.job
		if j == nil {
			return c.JSON(fiber.Map{"job": nil})
		}
		if since < 0 || since > len(j.Lines) {
			since = len(j.Lines)
		}
		cp := *j
		cp.Lines = append([]string(nil), j.Lines[since:]...)
		return c.JSON(fiber.Map{"job": cp, "next": len(j.Lines)})
	})

	startUpdateChecker()
}

// --- Déploiement du code Python sur le robot (partagé avec /api/update_rasp) ---

type raspDeployResult struct {
	Changed []string
	Warning string
	Msg     string
	Step    string // étape en échec (vide = succès)
	Output  string
}

// git pull (si pull, best effort), rsync de Rasp/ vers le robot, fichier VERSION, redémarrage
// du launcher si des fichiers ont changé. log reçoit les fichiers copiés (peut être nil).
func deployRaspCode(ctx context.Context, pull bool, log *updateJob) raspDeployResult {
	var r raspDeployResult
	projectRoot := findProjectRoot()

	// 1. git pull : un échec (pas d'accès internet, modifs locales) n'empêche pas le déploiement
	if pull {
		pullCmd := exec.CommandContext(ctx, "git", "pull", "--ff-only", "--no-rebase")
		pullCmd.Dir = projectRoot
		pullCmd.Env = append(os.Environ(), "GIT_TERMINAL_PROMPT=0")
		if out, err := pullCmd.CombinedOutput(); err != nil {
			r.Warning = "git pull a échoué, déploiement du code présent sur la base : " + strings.TrimSpace(string(out))
			fmt.Printf("[UPDATE RASP] %s\n", r.Warning)
		}
	}

	// 2. rsync (config.json exclu : il porte les réglages runtime du robot)
	raspIP := resolveRaspIP()
	sshOpts := "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5"
	rsyncCmd := exec.CommandContext(ctx, "rsync", "-rc", "--out-format=%n",
		"--exclude=.venv", "--exclude=__pycache__", "--exclude=*.pyc", "--exclude=*.log", "--exclude=config.json",
		"--exclude=LiDAR/lidar_udp", // binaire compilé sur la Rasp (aarch64) par main_robot.py
		"-e", sshOpts, projectRoot+"/Rasp/", robotTarget(raspIP)+":"+robotDir+"/")
	rsyncOut, err := rsyncCmd.CombinedOutput()
	if err != nil {
		r.Step, r.Output = "rsync", string(rsyncOut)
		r.Msg = fmt.Sprintf("Copie vers la Rasp (%s) impossible : %v", raspIP, err)
		return r
	}
	for _, l := range strings.Split(strings.TrimSpace(string(rsyncOut)), "\n") {
		if l != "" && !strings.HasSuffix(l, "/") {
			r.Changed = append(r.Changed, l)
			if log != nil {
				log.logf("  %s", l)
			}
		}
	}

	// 3. Fichier VERSION (même format que tools/deploy.sh), écrit à chaque déploiement
	versionCmd := exec.CommandContext(ctx, "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
		robotTarget(raspIP), fmt.Sprintf("cat > %s/VERSION", robotDir))
	versionCmd.Stdin = strings.NewReader(raspVersionFile(projectRoot))
	if out, err := versionCmd.CombinedOutput(); err != nil {
		r.Warning = strings.TrimSpace(r.Warning + " ; écriture de VERSION impossible : " + strings.TrimSpace(string(out)))
		fmt.Printf("[UPDATE RASP] Écriture de VERSION impossible : %v %s\n", err, string(out))
	}

	// 4. Redémarrage du launcher seulement si quelque chose a changé
	if len(r.Changed) > 0 {
		restartCmd := exec.CommandContext(ctx, "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
			robotTarget(raspIP), "sudo systemctl restart robot_launcher")
		if out, err := restartCmd.CombinedOutput(); err != nil {
			r.Step, r.Output = "restart", string(out)
			r.Msg = fmt.Sprintf("Code copié mais redémarrage du launcher impossible : %v", err)
			return r
		}
	}
	fmt.Printf("[UPDATE RASP] %d fichier(s) mis à jour sur %s\n", len(r.Changed), raspIP)

	r.Msg = "Code Rasp déjà à jour"
	if len(r.Changed) > 0 {
		r.Msg = fmt.Sprintf("%d fichier(s) mis à jour, launcher redémarré", len(r.Changed))
	}
	return r
}
