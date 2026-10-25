# Suivi du projet — à lire en début de session, à mettre à jour en fin de tâche

Dernière mise à jour : 2026-10-25 (soir). Compétition dans plus de 200 jours (pas avant ~mai 2027) :
les refontes sont acceptées.

## État du dépôt

- Branche `base_deporte` poussée le 2026-10-25 (d498846) : échelle caméra (02b83a8), firmware moteurs réécrit
  (6bb0374), rangement (`ESP/`, d498846). Rien de tout ça n'est déployé ni testé sur le robot.
- Tests : `tools/run_tests.sh` (tout passe le 2026-10-25 : 177 Python, JS, Go, firmware natif). `--rapide` saute test_strategies.
- Commit `4fbf9d8` (« le tux ») poussé et **déployé sur la base** le 2026-10-19 : service `base_stk` installé
  et actif. Anciennes modifs locales de la base : `git stash` + `~/sauvegarde_base_20261019.tgz` ; stratégie
  `carre.py/.xml` (faite sur la base) non suivie, à commiter si on la garde.
- Robot pas encore mis à jour : son code n'envoie pas sa version, donc Windows Update ne le propose pas ;
  première fois par Debug > Outils > Mettre à jour la Rasp (ou `tools/deploy.sh robot`).
- Réseau (2026-10-19) : la base sort sur internet via le PC (NAT `-o wlp192s0` dans `/etc/ufw/before.rules` ;
  `ufw reload` ne recharge pas la table nat : règle ajoutée à la main avec iptables). dnsmasq de la base
  plantait au démarrage (adresse pas encore là) : `bind-dynamic` au lieu de `bind-interfaces`.
- Env uv à la racine (`pyproject.toml` : numpy, OpenCV headless, pyzmq) : `tools/run_tests.sh` lance les tests
  Python avec `uv run python` si uv est là (le python3 de ce PC n'a pas numpy). 129 tests Python OK le 2026-10-25.
- Caméra embarquée refaite (2026-10-25) : commit b3afb38 poussé sur `base_deporte`, **non essayée sur le robot**.
- Préparation des essais (2026-10-25, voir « Essais robot prévus ») : check-list, calibration auto, LiDAR hors table,
  aller() + planificateur, temps de match, boîte noire / Replay, stratégie dynamique. Commité et poussé sur
  `base_deporte`, rien d'essayé sur le robot ; un changement Go (types.go, media.go) : `./Base/build.sh` sur la base.

## Fait (récent, du plus ancien au plus récent)

### Interface web (Base/Web)
- Thèmes : STK jour (palette `#ff9300` / `#000000` / `#c2c2c8`, police Luckiest Guy), STK nuit,
  Sombre, Windows 95. Variables dans `static/css/common.css`, choix par appareil via `static/js/theme.js`
  (ou `?theme=xxx`).
- Toutes les pages migrées sur le thème ; Debug réorganisée ; icônes Lucide (sprite
  `static/icons/sprite.svg`, `icon('nom')` en JS) à la place des emojis.
- Menus déroulants thémés dans tous les navigateurs (composant de `theme.js`, le `<select>` natif
  reste la source de vérité).
- Windows 95 : boutons réduire/agrandir/fermer (décoratifs) sur les barres de titre et l'en-tête ;
  accueil = explorateur de fichiers (C:\EIRBOT, dossiers) ; page Sons = lecteur multimédia façon
  Windows Media Player (écran + visualiseur, barre de position, lecture/pause/arrêt, préc./suiv.).
  Clippy (`static/js/clippy.js`, toutes les pages, Win95 seulement, pas sur l'écran robot) : blagues,
  piques par page et sur les toasts d'erreur, sons synthétisés en Web Audio ; « Ferme-la » = muet pour l'onglet.
  Barre des tâches (`static/js/win95.js`, toutes les pages sauf écran robot) : menu Démarrer (pages,
  sous-menu Thèmes, « Arrêter Windows… » = retour au thème STK), infos système + horloge dans la zone
  de notification. Pages à fenêtres : `<section data-task="Nom" data-icon="icone">` -> une fenêtre
  à la fois, sans défilement de page (Debug : Robot / Caméras / Conso & logs / Système).
  Ascenseurs façon Win95. Icônes pixel art 16x16 colorées (dessins maison, palette Win95) :
  `static/icons/win95.svg`, généré par `tools/win95_icons.py` (une grille de lettres par icône).
  Icône aussi dans chaque barre de titre (en-tête + fenêtres, choisie d'après le titre : `TITLE_ICONS`
  dans win95.js). Icônes des boutons : icône Win95 colorée ou supprimée (table `SWAP` dans win95.js ;
  un bouton qui n'a qu'une icône la garde). Le générateur produit aussi `static/css/win95-icons.css`
  (classes `.w95i .w95i-NOM`, icônes en image de fond).
- Strat Studio : l'éditeur Blockly suit le thème (fond, grille, boîte à outils, volet des blocs,
  ascenseurs, police) via les variables `--bk-*` de `blockly.css` ; avant, boîte à outils bleu ardoise
  en dur quel que soit le thème. En Win95 : rendu de blocs « win95 » (geras à coins carrés, encoches
  et tenons rectangulaires, dans blockly.js ; l'éditeur est recréé avec ses blocs quand on entre ou
  sort de Win95), boîte à outils en arborescence avec icônes, menus déroulants / clic droit / infobulles Win95.
  Blocs recolorés dans la palette Win95 (`w95Colour`), reflet blanc / ombre noire. Page en appli Win95 :
  barre de menus fonctionnelle (Fichier, Édition, Affichage, Exécuter, ?), barre d'outils plate,
  fenêtres Éditeur / Simulation / Invite MS-DOS dans une zone grise, barre d'état (message, blocs,
  équipe), nom de la strat dans le titre. Pas de corbeille Blockly en Win95 (glisser sur la boîte à outils).
- Boîtes de dialogue Win95 (win95.js `messageBox`) : erreurs de `toast(…, 'err')` et tous les `alert()`
  (icône erreur / avertissement / information devinée d'après le texte), confirmations via
  `askConfirm()` (common.js, Promise<bool> : Oui / Non en Win95, `confirm()` du navigateur sinon).
  Fenêtre déplaçable, Entrée / Échap, son « chord ». Les erreurs émettent l'événement `stk:error` (Clippy).
- Chaque page est une application Win95 (win95.js `APPS`, par page) : titre à gauche avec icône,
  barre de menus fonctionnelle, contenu qui défile dans la fenêtre, barre d'état (champs recopiés de
  la page), cartes en cadres de groupe, pas de capitales (`fixCaps`, sigles gardés). Debug = feuille
  de propriétés « Propriétés de EIRBOT » à onglets (sections `data-task`) avec OK / Annuler / Appliquer.
- Police Win95 partout : W95FA (Alina Sava, SIL OFL 1.1, `static/fonts/w95fa.woff2` + `W95FA-OFL.txt`),
  sauf journaux / consoles en Courier New.
  `playPrev()` / `playNext()` (appelées par la page Sons) n'existaient pas : ajoutées.
- Affichage téléphone ; mode test (pas d'arrêt à 100 s) ; notifications (`toast()`) ; pastille
  « Robot hors ligne » ; versions du code dans Debug.

### Calibration odométrie + caméra sur le vrai robot (2026-10-19)
- Rotation : 10 tours demandés (cmd_vel 90°/s, 40 s) -> 10 tours + 60° réels. Entraxe firmware
  `ecartRoues` 345 -> 339,3 mm (ancien `src/common.h`, aujourd'hui `config::WHEEL_BASE_MM` ; commit e9bab55, ESP moteurs flashé depuis la base).
  Après : odométrie et caméra d'accord à 5° près sur 10 tours (avant : 55°).
- Caméra : bruit à l'arrêt 11,8 mm / 0,13° ; tag du robot bien centré (4 mm de l'axe de rotation).
  Réglages appliqués sur le robot : `vision_odom.latence_s` 0,333, `cam_sigma_mm` 11,8, `cam_sigma_deg` 0,2.
- **Défaut trouvé dans la vision** (`Base/Vision/vision_deporte/.../computePosition.py`, dépôt d'antonythiery) :
  le repère monde est lié au robot, la pose de la table y bouge quand le robot bouge, et elle est filtrée
  (`passe_bas_expo`, 0,3) -> ~0,2 s de retard -> ~290 mm d'erreur pendant une rotation à 90°/s (exact à
  l'arrêt). Explique la latence apparente 0,33 s, les 94 % de rejets de la fusion et les +19,6 % d'« erreur
  d'odométrie » de regler_fusion (diamètre des roues : NE PAS corriger sur cette base).
  Contournement **sur la base uniquement** (non poussé, sous-module modifié localement) : coefficient 1.0.
  À faire : remonter à Antony ; solution propre = filtrer la table dans le repère caméra (fixe) et
  utiliser la rotation filtrée ligne 113 (rotation brute aujourd'hui).
- Vérifié avec le coefficient 1.0 : bruit à l'arrêt σ 9,8 / 3,9 mm, 0,32° ; 10 tours -> odométrie 3609°,
  caméra 3608° ; position caméra pendant la rotation à ~8 mm de la position à l'arrêt (avant : 290 mm).
  Robot posé en (880, 10, 0), caméra (870, 38) : ~28 mm en y à confirmer ailleurs (vision_odom.repere).
- Reste : `carre` puis `tools/regler_fusion.py` (latence, rejets), test 1 m au mètre (diamètre des roues).

### Windows Update : robot proposé à tort / pas redémarré (2026-10-19)
- Le robot était déclaré en retard dès que le commit changeait (même pour des fichiers de la base) ; le
  déploiement ne redémarrait que si des fichiers avaient été copiés -> robot jamais redémarré, version
  annoncée inchangée, mise à jour reproposée en boucle. Le nouveau launcher.py avait été copié (20:33)
  sans redémarrage du launcher.
- Corrigé : robot en retard seulement si `git diff <commit du robot> HEAD -- Rasp ':!Rasp/config.json'`
  n'est pas vide ; installation « Code du robot » = redémarrage forcé (`deployRaspCode(..., forceRestart)`).
  Debug > Mettre à jour la Rasp garde l'ancien comportement (redémarre si des fichiers ont changé).

### PIN et menus de stratégie (2026-10-19)
- PIN `2023` actif sur la base (`Base/pin.txt`, droits 600) ; vérifié : POST sans session -> 401, GET libre.
- Menus de stratégie (Debug, accueil) qui « clignotaient » : la page remettait la valeur du robot toutes les
  ~1,6 s même pendant la demande de PIN / avant la confirmation du robot. common.js : `sendConfigEdit` +
  `syncSelect` (le choix est gardé 10 s ou jusqu'à confirmation, abandonné si la commande est refusée).
- Vrai clignotement STATIQUE <-> DYNAMIQUE (et caméra / LiDAR) dans Debug : la config n'arrive que dans ~1
  message d'état sur 15 ; debug.js prenait `{}` sinon. Corrigé : dernière config reçue (`window.localConfig`).

### Relance du robot après une mise à jour (2026-10-19)
- Avant : redémarrer `robot_launcher` tuait `main_robot.py`, qu'il fallait relancer au bouton 3.
- Le déploiement (`robotRestartCmd` dans winupdate.go, utilisé par Windows Update et Debug ; même commande
  dans deploy.sh) pose `~/Documents/robot_stk/.relance_apres_maj` si le programme tournait ; au démarrage,
  `Rasp/launcher.py` (`autostart_after_update`) supprime le témoin et relance le programme.
- Windows Update : avertissement (Continuer / Annuler) « le robot va redémarrer », attente du retour du
  robot avec la nouvelle version (90 s max), puis fenêtre « installée avec succès » (aussi après un
  redémarrage de la base, via sessionStorage).

### Thème de l'écran du robot (2026-10-19)
- L'écran 7" (`?mode=robot`) suit le dernier thème choisi sur un autre appareil : `setTheme()` (theme.js)
  envoie le choix à la base (`POST /api/ui_theme`, sans PIN), qui le garde dans `Base/ui_theme.txt` et le
  diffuse par WebSocket (`ui_theme`). Les autres appareils gardent leur propre thème. Go : `uitheme.go` + test.

### Démineur (2026-10-19)
- Page `/demineur` (`demineur.html/js/css`) : niveaux Débutant / Intermédiaire / Expert, premier clic jamais
  sur une mine (ni à côté), drapeau au clic droit / appui long / « mode drapeau » (tactile), clic sur un
  chiffre = découvrir autour, F2, meilleurs temps dans le navigateur. Menus Partie en Win95, tuile sur
  l'accueil, icônes Win95 `mine` et `flag`. Une défaite émet `stk:error` (Clippy, Tux).
- Idées suivantes : Solitaire (moyen), Pinball (gros : moteur physique).

### Windows Update et Tux (2026-10-19)
- `Base/Web/winupdate.go` : git fetch au démarrage puis toutes les 15 min (hors match), comparaison dépôt de la
  base / branche distante / binaire qui tourne (`buildVersion`) / code du robot (`RobotVersion`). Routes
  `GET /api/update/status`, `GET /api/update/check` (fetch, sans PIN), `POST /api/update/install`
  (`targets` : depot | base | robot, PIN), `GET /api/update/job?since=N` (journal). Installation : git pull,
  puis rsync robot (code partagé avec `/api/update_rasp` : `deployRaspCode`) et/ou `Base/build.sh` puis
  `sudo -n systemctl restart base_stk` (la page attend le retour de la base). Refus pendant un match,
  même verrou que le flash ESP. Tests : `winupdate_test.go` (vrai dépôt git temporaire).
- Page `/update` (`update.html/js/css`) : site Windows Update de 1998 en Win95, cartes en STK. Tuile sur
  l'accueil (nombre de mises à jour), entrée en haut du menu Démarrer, icône + bulle dans la zone de
  notification quand il y a des mises à jour (win95.js `checkUpdates`, `balloon`).
- `git pull --ff-only --no-rebase` partout (winupdate.go, deploy.sh) : avec `pull.rebase=true`, un pull
  échoue dès qu'un fichier est modifié.
- Tux (`static/js/tux.js`, Win95) : « Avez-vous essayé Linux ? » une fois par session (2 min 30 à 5 min 30,
  ou après une erreur) ; Oui -> proposition d'arrêter Windows ; Clippy réagit (`stk:tux`).
  `window.tuxShow()` dans la console pour le voir tout de suite.

### Règlement 2027 / Internet Explorer (2026-10-19)
- Nouvelles règles dans `docu/` (non suivies par git) : `Eurobot2027_Rules_FR.pdf` (thème Camelot) et
  règles générales 1.4 (`Eurobot_General_Rules_SR_FR.pdf`).
- Page `/regles` (`templates/regles.html`, `static/js/regles.js`, `static/css/regles.css`) : règlement 2027
  résumé, règles générales, barème, plan, calculateur de score, liens vers les PDF (route `/docu/<x>.pdf`).
  Navigation par ancre (`#jeu/points`). En Win95 : Internet Explorer (barres d'outils / adresse / liens,
  logo animé, volet Favoris, menus dans `APPS`, page « Impossible d'afficher la page »), contenu en Times.
- Images extraites du PDF dans `static/img/regles/` (~480 Ko). Icônes Win95 `ie` et `calc`, Lucide
  `book-open`, `calculator`, `arrow-right` ajoutées. Tuile sur l'accueil (« Internet Explorer » en Win95).

### Diagnostic réseau (2026-10-18)
- Nouveau test du lien base ↔ robot : allers-retours ZMQ ping / pong (`Base/Web/robotping.go`,
  `/api/robot_ping?n=30` -> moyenne, p95, max, gigue, pertes ; réponse immédiate dans zmq_client.py).
- Page : 4 mesures (base ↔ robot, navigateur ↔ base, débits), délai maximum sur chaque requête,
  seuils adaptés au robot (pics et pertes plutôt que débit). Tests réseau refusés pendant un match (409).
- Tests : Go (`robotping_test.go`) et e2e (ping avec le robot simulé, refus en match).

### Architecture (les 6 points d'amélioration)
1. **Robot = source de vérité** de l'état du match et de la config : `Rasp/core/match_state.py`
   (seul écrivain de l'état), `Rasp/core/config_store.py` (config validée, écriture atomique).
   La base applique l'instantané `robot_state` publié par le robot (`Base/Web/robotstate.go`) et
   transmet les commandes ; refus 503 si robot hors ligne.
2. **Repère unique** : `Rasp/core/frames.py` + `Base/Web/static/js/frames.js` (mêmes formules).
3. **Watchdog ESP moteurs** : battement de cœur Rasp toutes les 100 ms, arrêt moteurs après 300 ms
   de silence, trame `W` (src/ComWithRasp.*, esp_motors.py).
4. **Déploiement** : `tools/deploy.sh` (base | robot | esp | status | all, `--dry-run`), fichier
   VERSION sur le robot, `/api/version`, service `Base/systemd/base_stk.service`, rotation des logs.
5. **Tests et simulation** : `tools/robot_sim.py` (vrai code robot + faux matériel),
   `tools/check_strategy.py`, test de bout en bout base Go + robot simulé, test de toutes les stratégies.
6. **Code PIN** (`Base/Web/auth.go`) : `Base/pin.txt` ou `STK_PIN` ; STOP, lecture, écran du robot
   et base toujours libres.

### Localisation : fusion odométrie + caméra (2026-10-18)
- `Rasp/core/localisation.py` : l'ESP garde son odométrie, la Rasp tient la transformation
  odo -> table corrigée par chaque image caméra (Kalman sur la pose, latence compensée par un
  historique d'odométrie, rejet des mesures aberrantes). `robot_pos` = pose fusionnée.
- `esp_motors.goto` convertit la cible dans le repère de l'ESP ; `set_pos` remet la fusion à zéro
  (et rattrape l'arrondi entier de « S ») ; `recalage_camera` passe par la fusion (plus de « S »).
- Fin de `goto` : petit GoTo de rattrapage si la caméra a corrigé la pose pendant le trajet
  (le firmware ignore un G pendant un mouvement). Réglages dans `vision_odom` (config.json),
  `fusion: false` pour revenir à l'odométrie seule.
- Réglage automatique : le robot enregistre odométrie brute + caméra (`Rasp/utils/loc_recorder.py`,
  `Rasp/logs/localisation/`) ; `tools/regler_fusion.py` en déduit latence, bruit caméra, dérive et
  erreur d'échelle des roues, et rejoue l'enregistrement pour comparer (validé sur données synthétiques).
- Simulateur et tests : `test/test_localisation.py`, `test/test_regler_fusion.py` ; `test_esp_motors.py` (ex-`test_esp_heartbeat.py`) n'était pas lancé par
  `run_tests.sh` (écrit pour pytest) : corrigé.

### Réécriture du firmware moteurs (en cours, commencée le 2026-10-24)
- Nouveau firmware dans `ESP/src/motors/` ; l'env `Motor` le compile (C++17), ancien code supprimé
  (commit 6bb0374). **Ne pas flasher l'ESP moteurs avant d'avoir adapté `esp_motors.py`** : le
  protocole a changé (`G id x y theta`, `D id` / `A id`, `E`), l'ancien code Rasp ne marcherait plus.
- Décisions : Arduino + fonctions ESP-IDF/FreeRTOS (UART IDF, files) ; une seule tâche commande les moteurs ;
  chaque segment part de l'odométrie ; arrêt aussi en rotation si `L 1` ; profil trapèze FastAccelStepper ;
  tests PC (env `native`, Unity, 61 tests).
- Fichiers : config.h, kinematics, pose.h + odometry, goto_planner, protocol (+ LineReader, RaspWatchdog),
  wheel_driver.h + steppers, motion (machine d'états pure) + motion_task (FreeRTOS), link (UART, T à 10 Hz,
  watchdog), main.cpp. `esp_motors.py` adapté (GoTo numérotés, flottants, trames E, `ESPError` si l'ESP
  est absent, GoTo abandonné après 30 s sans réponse ; `test/test_esp_motors.py`, 11 tests).
  À flasher ENSEMBLE : firmware moteurs + code Rasp. Reste : checklist sur le robot (vérifier :
  rotation +90° vers +Y, broches 16/4 = roue droite, lignes de boot de l'ESP ignorées par la Rasp).
- Drivers MKS SERVO42D en boucle fermée CR_CLOSE (CR_vFOC : à-coups). Micro-pas 16 gardé (`config::MICROSTEPS`,
  doit correspondre au menu MStep des drivers) ; 256 refusé à la compilation (fréquence de pas trop haute).
- Un nouveau `G` pendant un GoTo le remplace (`A ancien_id` puis départ vers la nouvelle cible).
- Pas d'ESP32 sous la main pour l'instant : tout est vérifié par compilation + tests PC, essais réels plus tard.
- Tests firmware : `pio test -d ESP -e native` (dossier `ESP/test/`, lancés aussi par `tools/run_tests.sh`).
  Chaque nouveau fichier pur s'ajoute au `build_src_filter` de l'env native.

### Rangement du dépôt (2026-10-25)
- Firmware dans `ESP/` : `ESP/platformio.ini`, `ESP/src/motors`, `ESP/src/actuators`, `ESP/test`, `.clangd` /
  `.clang-tidy`. Suivis : flash depuis la base (`espProjectDir()` dans settings.go, compile dans `ESP/`),
  `tools/deploy.sh`, `tools/run_tests.sh`, Windows Update (`ESP/` = touche l'ESP). La base doit être
  recompilée (`./Base/build.sh` sur la base) pour flasher depuis `ESP/`.
  VSCode : l'extension PlatformIO ne voit le projet que si `ESP/` est ouvert comme dossier de travail.
- Supprimés : `build/` (sorties CMake commitées par erreur, désormais ignorées), `GEMINI.md`,
  `platformio-core.README.md`, `conv.py`, `include/`, `lib/`, `Base/Vision/vision_worker.py`.
- Actions 2025 vidées (noms gardés pour Blockly / stratégies / IHM, contenu « à définir (2027) ») :
  `approcheKapla`, `thermometre`, `prendreKapla`, `poseKapla`, `pousse_kapla` (actions.py) et `pose_*`
  (esp_actionneur.py). `Rasp/Vision/cam.py` (vision Kapla) n'est plus importé : à supprimer ou refaire.

### Refactor LiDAR (2026-10-25)
- `lidar_udp.cpp` envoie, à chaque tour, le minimum de chaque secteur de 5° (paquet « LDR2 », 300 octets) au
  lieu du seul point le plus proche ; code des balises supprimé (pas de localisation LiDAR).
- Décision dans `Rasp/core/obstacles.py` (pur, `test/test_obstacles.py`, 15 tests) : cônes avant / arrière,
  côtés ignorés (sauf < 130 mm -> STOP), avant + arrière -> STOP ; le délai de 1 s avant CLEAR s'applique
  maintenant aussi à l'ESP (avant : seulement à l'affichage). `lidar_thread.py` ne garde que UDP + driver.
- À vérifier sur le robot : le binaire est recompilé par main_robot.py (.cpp plus récent) ; seuils à régler.

### Matériel démarré une seule fois (2026-10-25)
- `Rasp/hardware.py` : `start(cfg)` ouvre les ESP et la caméra (appelé par main_robot.py, robot_sim, check_strategy,
  test d'intégration) ; ailleurs on lit `hardware.esp` / `hardware.actionneurs` / `hardware.camera`. Importer
  `strat.actions` ou `ihm.shared` n'ouvre plus rien. Un seul `RobotActions` (LiDAR + stratégie : `strat_loop(robot)`).
- Supprimés : `LedStrip` (utils/leds_manager.py, inutilisé), `EndOfMatchException`, `_check_time`, `toggle_lidar`,
  `is_returning`, constantes mortes. `test_integration.py` (écrit/effacé par le test) n'est plus suivi par git.
- Son coupé dans les tests et le simulateur (`audio.enabled` false ; `tools/robot_sim.py --son` pour l'entendre).

### zmq_client : table de commandes (2026-10-25)
- `_handle_msg` : table « type -> méthode » (`_on_config`, `_on_action`, `_on_actuator`...) au lieu de 180 lignes de elif.
- Commandes manuelles (cmd_vel, goto, set_robot_pos, cmd_actuator) refusées pendant un match (règlement : robot
  autonome ; un joystick égaré annulait les GoTo de la stratégie), signalé dans les journaux (au plus toutes les 2 s).
  Test : `test_6_commandes_manuelles_refusees_pendant_match`.

### Base Go découpée (2026-10-25)
- `routes.go` (881 -> 383 lignes) : pages, commandes robot, WebSocket. Sortis : `vision.go` (worker vision +
  routes /api/vision, /api/stream_usb), `flash.go` (/api/update_rasp, /api/flash_esp, flashMutex),
  `strategies.go` (liste / lecture / sauvegarde Blockly) ; `fileExists` dans settings.go.
- `zmq.go` : état allégé construit par `lightStateLocked()` (était recopié 3 fois). `gofmt` propre partout.
- Tests e2e : quand `setUpClass` échouait (ex. numpy absent côté robot simulé), la base de test restait lancée
  et occupait les ports 18080 / 15555 / 15556 (tests suivants sautés). Corrigé (`addClassCleanup`).

### Carte 3D et Strat Studio aux vraies dimensions (2026-10-25)
- Carte 3D (map.js) : table et robot = modèles MuJoCo de vision_deporte (servis par la base sous `/models/`,
  `mujocoModelsDir()` dans vision.go), lus par `static/js/mujoco_model.js` (XML + STL binaires, sans
  dépendance). Tapis de jeu texturé, bordures, pieds ; robot détaillé (31 Mo, pas chargé sur l'écran du robot).
  Boîtes de secours aux vraies dimensions si les modèles manquent. Vérifié par capture Chromium headless.
  `/models` servi SANS compression : avec, Fiber écrivait un `.fiber.gz` par fichier dans le sous-module.
- Encombrement réel du robot (modèle MuJoCo, `tools/encombrement_robot.py`) : avant 245,5 mm, arrière 102 mm
  (l'axe des roues n'est pas au centre), demi-largeur 188,2 mm, hauteur 450 mm. Dans `frames.py` / `frames.js`
  (`ROBOT_*`, `robot_corners`), testé des deux côtés. Strat Studio : robot dessiné à l'échelle (avant 320 x 370
  centré + image du robot 2025) ; tunnel de trajectoire à la vraie largeur.
- Image du robot vu de dessus dans le Strat Studio (`static/img/robot_dessus.png`) rendue depuis le modèle MuJoCo :
  `uv run --with websockets python tools/rendu_robot_dessus.py` (base lancée ; page `static/tools/rendu_robot.html`).
  À relancer quand le modèle du robot change.
- À vérifier sur le robot : X du modèle MuJoCo = avant du robot (sens de marche quand theta augmente le X).
- 11 routes appelées par le JS manquaient dans la base Go (restes de l'ancienne IHM Flask : menus Blockly vides,
  Sons, LED Studio, luminosité, Replay cassés). Recréées dans `Base/Web/media.go` : sons (liste, envoi + scp vers
  le robot, lecture, arrêt, volume), LED (`led_control`, `play_animation`, `set_brightness`, animations lues /
  enregistrées puis envoyées au robot), journaux de match (lus sur le robot par ssh). Robot : commandes ZMQ
  `led_cmd` (liste blanche) et `led_animations` ; le journal de télémétrie démarre / s'arrête avec le match
  (`Rasp/logs/telemetry/blackbox_*.csv`, jamais démarré avant). Tests Go + `test_7_commandes_led`.

### Découpage du JS (2026-10-25)
- Pas de framework ni de modules ES (122 `onclick=` dans les templates appellent des fonctions globales) : les gros
  fichiers sont coupés par sujet en fichiers classiques, chargés dans l'ordre par leur template.
  `debug.js` -> `static/js/debug/` (7), `blockly.js` -> `blockly/` (8, en defer après Blockly), `controle.js` ->
  `controle/` (8), `map.js` -> `map/` (6), menus Win95 -> `win95_apps.js`. Plus aucun fichier > 600 lignes.
- Vérification : chaque ligne de code retrouvée une fois ; captures Chromium headless identiques au pixel avant /
  après ; script qui vérifie que toutes les fonctions des attributs on* existent ; scénarios (Strat Studio :
  chargement + aperçu + simulation, Python généré identique ; carte : vue de dessus).
- Jauges de vitesse des roues (Pilotage) : entraxe 339,3 et convention du nouveau firmware (étaient inversées).
- `static/js/socket.io.js` (6000 lignes, chargé nulle part) supprimé ; la copie de `vendor/` reste (non vérifiée).
- Outil de vérification utilisé (non commité, à refaire si besoin) : Chromium headless piloté par CDP
  (`uv run --with websockets`), base locale sur des ports libres (`STK_HTTP_PORT=28080`...).

### Caméra embarquée : ArUco réutilisable + optimisé Pi 4 (2026-10-25)
- `Rasp/Vision/cam.py` (2025, inutilisé, valeurs en pixels codées en dur) supprimé, remplacé par :
  - `core/vision_geom.py` (pur, `test/test_vision_geom.py`) : modèle caméra (intrinsèques + distorsion OpenCV +
    montage sur le robot), pose d'un tag dans le repère robot (X avant, Y gauche, Z haut). Pas de PnP libre :
    orientation imposée (`vertical` = 2027, normale horizontale ; `horizontal` = 2025), LM sur la reprojection
    des 4 coins, z connu / inconnu / liste de hauteurs, rotation du tag dans son plan essayée. Le trapèze
    donne bien l'angle : bruit 0,5 px sur les coins -> < 3° et < 5 mm à 50 cm sur une image (médiane ensuite).
    ~0,3 ms par tag sur PC : pas besoin de C++ (la détection est déjà du C++ dans OpenCV).
  - `Vision/aruco.py` : `DetecteurAruco` (recherche sur image réduite, coins affinés en pleine résolution,
    fenêtres de suivi, 2 seuillages, 2 threads OpenCV ; « ArUco 3 » désactivé : coins faux de 5-7 px) et
    `VisionAruco` = `hardware.vision` (thread à la demande ; `mesurer(ids, n)` = médiane, `derniere()`,
    `PoseTag.distance / .y / .ecart_angle / .point_devant(d) / .vers_table(pose)`). Test sur images
    synthétiques `test/test_vision_aruco.py` (OpenCV, coins à 0,25-0,5 px).
  - `utils/sensors/camera_libcamera.py` : flux YUV420 (gris = plan Y, sans conversion), flux d'affichage séparé
    converti seulement si regardé, rotation 180° par le capteur, `queue=False`. Webcam PC si `camera.webcam`.
  - `Vision/mjpeg_streamer.py` : une image encodée par image caméra (avant : la même 2 fois), `?aruco=1` dessine
    les tags (active la détection), `/snapshot` = gris pleine résolution.
  - `tools/calibrer_camera_robot.py` : capture des photos de damier via `/snapshot` + calibrateCamera
    -> `camera.intrinseques` (validé sur images synthétiques).
- Image rosée : l'ancien code demandait « BGR888 » (= octets R,G,B dans picamera2) puis inversait : l'ordre
  final était a priori correct. Avec YUV420 la question disparaît ; si c'est encore rosé, ce n'est pas une
  inversion mais un module NoIR / mauvais réglage -> `camera.tuning` (ex. `imx219_noir.json`).

### Préparation des essais : évitement, check-list, calibration, temps, replay, stratégie dynamique (2026-10-25)
- **LiDAR hors table** (`core/obstacles.py`) : avec une pose fiable (`shared.pose_fiable` : set_pos fait ou
  caméra acceptée, incertitude < 150 mm), les secteurs dont le point tombe hors table (moins `lidar.marge_table_mm`)
  sont ignorés : plus d'arrêt pour les gens au bord. `lidar.montage` (x, y, angle, sens) sert aussi à la décision
  avant/arrière (défaut = comportement d'avant ; l'ancien `lidar.angle_offset_deg: -90`, lu nulle part, a été
  retiré). Points restants publiés (`shared.lidar_points`, repère table) : carte, planificateur, boîte noire.
- **Commandes manuelles pendant un match** : déjà refusées par `zmq_client.MANUAL_COMMANDS` (la ligne « À faire »
  était périmée) ; `calibration` ajoutée.
- **Check-list avant match** (`core/preflight.py`, 1 Hz dans `sys_info.checks`, `static/js/checklist.js`) : ESP
  moteurs (trames), actionneurs, LiDAR (mode, tours), caméra zénithale, batterie, stratégie, **position de départ**
  (caméra vs premier `set_pos` de la stratégie, symétrie comprise), tirette, mode test, caméra embarquée, temp.
  Accueil / écran 7" : résumé + problèmes ; Debug > Robot : tout.
- **Calibration automatique** (`strat/calibration.py`, carte dans Debug > Robot) : recalage, 2 carrés, rotations,
  lignes droites, puis analyse sur le robot (`core/reglage_fusion.py`, extrait de `tools/regler_fusion.py` qui
  l'importe) ; résultat dans Debug avec « Appliquer » (vision_odom.*) et facteurs diamètre / entraxe firmware.
- **aller(x, y, θ)** (`strat/actions.py`, bloc « Aller (évitement) ») : `core/planif.py` = grille 30 mm, obstacles
  gonflés du demi-encombrement (215 mm), surcoût autour (heat map), adversaires de la caméra zénithale + position
  prédite, points LiDAR, `planif.obstacles` (fixes, à remplir pour 2027), A* + lissage. Un GoTo par segment,
  replanifié à chaque point de passage et quand l'ESP s'arrête. Chemin + carte de coûts envoyés à la carte 3D
  (`map/plan.js`). ~6 ms par plan sur PC. Adversaires : `vision_deporte_worker.py` publie les tags 1-10 (sauf 2)
  dans `vision_update.adversaires` (base : `VisionPose.Adversaires`), seulement quand notre robot est vu.
- **Temps de match** (`core/temps_match.py`) : durée d'un GoTo = t0 + d/v + rotation/w, appris sur les vrais GoTo
  (`logs/durees_goto.jsonl`). `retour_fin(x, y, θ, marge)` : avant chaque déplacement, s'il ne reste plus que le
  temps de rentrer, `RetourFin` interrompt la stratégie et `main_strat` fait rentrer le robot (aussi quand la
  stratégie finit plus tôt). `si_temps(s)` : bloc « S'il reste le temps de faire N s ».
- **Caméra embarquée** : `aligner_tag(ids, distance_mm)` (bloc « S'aligner sur le tag »), mesure à l'arrêt, recule
  si le décalage latéral est grand, `approche_reussie` ; bouton « Tags » sur le flux embarqué de Debug.
- **Boîte noire** (`utils/telemetry_logger.py`) : `match_*.jsonl` (trames 10 Hz : pose, caméra, adversaires, LiDAR,
  évitement, incertitude ; événements goto / plan / retour / tag / objectif). Page Replay réécrite : bon repère
  (l'ancienne dessinait X sur 3000 mm), robot à ses vraies dimensions, fantôme caméra, adversaires, LiDAR, chemin,
  liste d'événements cliquable ; lit encore les anciens `blackbox_*.csv`.
- **Stratégie dynamique** (`core/decision.py`, `robot.jouer(objectifs)`, exemple `strategies/demo_dynamique.py`) :
  objectifs écrits à la main (pose, points, durée, proba, prérequis, action), ordre décidé en match : points espérés
  par seconde sur une suite de 2 objectifs (actualisée), temps restant et retour compris, proba baissée près de
  l'adversaire et après un échec.
- `strat/__init__.py` ne réexporte plus rien (importer `strat.calibration` chargeait tout le robot).

### Navigation : planificateur sur la base + suivi de trajectoire (2026-10-25, soir)
- **Base** : `Base/Planif/planif_worker.py` (lancé / relancé par `base_stk` : `Base/Web/planif.go`, prise PUB dédiée
  5557, `STK_NO_PLANIF=1` pour ne pas le lancer). Il reçoit caméra zénithale (adversaires + **pierres**), télémétrie,
  points LiDAR, demandes `nav_demande` / `nav_fin` du robot ; renvoie `plan` à 10 Hz (relayé au robot et à la
  carte 3D) et `carte_planif` à 2 Hz (carte de coûts, trajectoires prédites, pierres). Logique :
  `core/navigation.py` (même code que le secours du robot).
- **Prédiction** (`core/suivi_adversaire.py`) : Kalman vitesse constante par tag adverse, vitesse amortie au-delà
  d'1 s, incertitude croissante (plafonnée à 500 mm).
- **Planification** (`core/planif.planifier_temps`) : A* dont le coût est une durée (distance, surcoûts, rotations) ;
  à l'heure de passage prévue, zone interdite autour de la position PRÉDITE de l'adversaire (rayon + 0,5 x
  incertitude plafonnée à 100 mm) + surcoût autour : le robot passe derrière un adversaire qui traverse. Lissage
  vérifié à l'heure réelle du chemin lissé. Pierres = rectangles orientés 320 x 110. Hystérésis : un chemin se CRÉE
  avec 50 mm de tampon et se GARDE sans tampon tant qu'il est valable et qu'un autre ne fait pas gagner 15 %.
  Base : ~15 ms par plan.
- **Vision** : pierres = tag 13 face vers le haut, pose calculée par détection (computePosition n'en garde qu'une par
  numéro) ; `VISION_TAG_PIERRE_MM` (50 par défaut, **à mesurer**), `VISION_PIERRE_AXE_TAG_DEG`.
- **Robot** (`strat/actions.py : aller`) : plan de la base s'il a moins de 0,4 s, sinon planificateur embarqué ;
  `planif.execution = "suivi"` : suivi continu (`core/suivi.py`, pure pursuit régulé, consignes `V` à 20 Hz, pose
  extrapolée entre deux trames T, ralentit en virage / près d'un point LiDAR devant / près de l'adversaire), puis
  GoTo final précis ; `"goto"` : un GoTo par segment (ancien comportement). L'évitement LiDAR de l'ESP (L) reste
  actif en mode vitesse (vérifié dans `motion.cpp`).
- Simulateur : le faux ESP exécute les consignes `V` (rampe, arrêt sans consigne en 500 ms) ; `check_strategy`
  force `execution = "goto"` (déplacements instantanés).
- Essai de bout en bout fait sur PC (binaire base + worker + messages caméra / robot simulés) : 29 plans en 3 s
  reçus sur le canal du robot, contournant adversaire et pierre.

### Vidéo de simulation, piles de pierres (2026-10-25, nuit)
- `tools/video_simu.py` (`uv run tools/video_simu.py -o simu.mp4`) : vidéo de dessus avec le vrai planificateur et le
  vrai suivi (monde simulé : robot, adversaire en allers-retours, caméra, LiDAR, piles de pierres). Le décor est
  vérifié avec le planificateur (pas de couloir trop étroit).
- Corrigé grâce à elle : points LiDAR déjà expliqués (adversaire suivi, pierre connue) ignorés comme obstacles
  fixes (`Navigateur.points_inexpliques`) ; robot bloqué devant un obstacle -> il tourne vers le chemin au lieu de
  rester figé (`suivi.py`) ; adversaire gardé à sa dernière position prédite au-delà de l'horizon (sinon un chemin
  lointain passait à travers un robot arrêté).
- Pierres empilées : `nb` = hauteur du tag / 110 mm (vision -> base -> carte 3D : pile de nb boîtes + nombre,
  dessinée depuis `vision_update`, même sans planificateur). **Vérifier le signe de z** sur la vraie caméra.

## Essais robot prévus (dans l'ordre)
1. Déployer base (`./Base/build.sh` sur la base : Go modifié ; **`uv sync` à la racine du dépôt sur la base**, avec
   internet, pour l'env du planificateur) et robot ; **copier dans le config.json du robot** les sections `camera`,
   `lidar` (montage, filtre_table, marge_table_mm), `planif` (dont `execution`).
2. Check-list : accueil et Debug ; débrancher un ESP / la tirette / la caméra zénithale -> l'item passe au rouge.
3. LiDAR : objet posé à gauche du robot -> vérifier sur la carte 3D que les points rouges sont à gauche (sinon
   `lidar.montage.sens: -1` ou `angle`) ; quelqu'un le long de la bordure pendant un GoTo -> pas d'arrêt.
4. Calibration auto (Debug > Robot, carré 500) -> appliquer, noter les facteurs firmware.
5. `aller()` : d'abord `planif.execution = "goto"` (comportement connu), puis `"suivi"` à vitesse réduite
   (`planif.v_max_mm_s` 300) ; obstacle, pierre (tag 13 posé à plat), autre robot avec un tag 1-10 : chemin,
   prédiction et carte de coûts sur la carte 3D ; couper la base en route -> le robot continue (plan embarqué).
6. Caméra embarquée : tag 13 imprimé sur une boîte, bouton Tags, `aligner_tag` (mesurer au réglet).
7. Match `demo_dynamique` avec chrono court (mode test off) : retour à temps, puis Replay du match.

## À faire

### Sur le matériel (priorité, rien de tout ça n'a été essayé)
- [ ] Déployer le **robot** (la base est faite ; le protocole d'état a changé, les deux doivent suivre).
- [ ] ESP moteurs flashé le 2026-10-19 (entraxe) ; reste à vérifier : pas de faux déclenchement du
      watchdog en match (`watchdog_count` dans esp_motors), arrêt si on débranche l'USB, pas de reprise
      au rebranchement. Si faux déclenchements : passer `RASP_TIMEOUT_MS` à 400-500.
- [ ] Définir le PIN dans `Base/pin.txt` sur la base.
- [ ] Vérifier un match complet : tirette, fin à 100 s, réarmement par la tirette après un match,
      équipe/LEDs, mode test, écran 7" du robot.
- [ ] Recharger / vérifier la batterie (alerte < 18 V, rétablie > 19,5 V : seuils peut-être à revoir).
- [ ] Caméra embarquée : `config.json` n'est pas déployé -> recopier la section `camera` (resolution, montage,
      aruco.tags...) dans celui du robot. Vérifier sur la Pi : version d'OpenCV, démarrage YUV420 + lores,
      couleur (rosé ?), `ms/image` affiché par `http://<robot>:8081/stream?aruco=1`.
- [ ] Caméra : calibrer (`tools/calibrer_camera_robot.py`), mesurer `camera.montage` (position, tangage) et la
      **taille réelle du tag 13** des pierres (50 mm mis par défaut, le règlement ne la donne pas).
- [ ] Robot simulé (`tools/robot_sim.py`) : pas de LiDAR ni d'adversaire simulés -> le planificateur n'y voit
      que les obstacles fixes. Ajouter un adversaire qui bouge pour tester `aller()` / `jouer()` en simulation.
- [ ] `planif.obstacles` : saisir les éléments fixes de la table 2027 (château, remparts, douves...) ; les pierres
      vues par le LiDAR deviennent des obstacles : approcher avec `aller()` à distance, puis `aligner_tag`.
- [ ] Suivi continu : régler `v_max_mm_s`, `a_max_mm_s2`, `a_lat_max_mm_s2`, anticipation sur le vrai robot
      (pas à pas : vérifier qu'il ne décroche pas) ; latence réelle base -> robot à mesurer (plan.t vs réception).
- [ ] Test automatique de la chaîne base <-> planificateur (aujourd'hui : essai manuel, cf. « Navigation »).
- [ ] Rotation sur place aux points de passage : le planificateur garantit le passage du robot de profil
      (215 mm), pas sa rotation (rayon ~310 mm autour du point de référence) près d'un obstacle.

### Code
### Revue de code firmware -> Rasp -> base (2026-10-24, rien de corrigé)
- [ ] **Firmware GoTo** (`GoToPosition.cpp`) : part de sa pose « supposée », pas de l'odométrie (cap = cap
      demandé, jamais relu ; pose non mise à jour après un joystick `V` ; `UpdateFinalPoseAfterStop` faux après
      `H`). Angles tronqués à l'entier (`(int)abs(pangle)`) -> jusqu'à ~2° d'erreur de cap par GoTo, qui
      s'accumule sans que la fusion le voie. Corriger : `mot.GetPosition()` au début de `Go()`, arrondir.
- [ ] Firmware : `WaitUntilDone` peut répondre « D » trop tôt (file vide + moteurs pas encore lancés au
      début du dernier segment). `TransferQueueBuffer` / `RestoreQueueBuffer` : code mort.
- [ ] LiDAR : `clear_delay` ne retarde que l'affichage, l'ESP repart tout de suite (`lidar_thread.py`) ;
      seul le point le plus proche par tour est envoyé (un mur latéral masque un robot devant) ; secteurs
      latéraux classés « arrière ».
- [ ] ESP moteurs absent : `esp` existe avec `ser=None`, les GoTo attendent jusqu'à la fin du match.
- [ ] Un « A » en retard après un `H` peut terminer le GoTo suivant (les commandes manuelles pendant un match,
      elles, sont bien refusées : `zmq_client.MANUAL_COMMANDS`).
- [ ] `approcheKapla` sans caméra : symétrie appliquée à une pose réelle puis `goto(0, 0, 0)` (bord de table).
- [ ] Fermer la fenêtre webview de l'écran robot arrête tout le programme (`main_robot.py`, `sys.exit`).
- [ ] Vision : pas de `CAP_PROP_BUFFERSIZE=1` (images en retard) ni d'âge de l'image envoyé.
- [ ] Ménage : `EndOfMatchException` / `GoBase` auto jamais déclenchés, code 2025 (Kapla, thermomètre),
      actionneurs sans accusé de réception.

- [ ] Régler la fusion sur le vrai robot : Debug > Robot > Calibration automatique (ou, à la main, rouler 2-3 min
      puis `tools/regler_fusion.py logs/localisation/loc_*.csv --appliquer <config.json du robot>`).
      Corriger diamètre / entraxe dans le firmware si l'erreur dépasse 1 %. Vérifier que les rattrapages de fin
      de goto ne font pas de demi-tours inutiles.
- [ ] Afficher l'état de la fusion (écart-type, mesures acceptées/rejetées) dans Debug ou sur la carte.
- [ ] IP en dur restantes côté Python : `Rasp/main_robot.py` et `Rasp/ihm/__init__.py`
      (`server_ip` par défaut), `Rasp/utils/system_info.py` (cible de ping).
- [ ] Menu contextuel de la page Sons : peut dépasser l'écran sur téléphone.
- [ ] **Carte 2027** : redessiner la table dans map.js (carrières, remparts, douves, écuries, salles du
      trône) d'après `static/img/regles/plan.jpg` (plan : x 0..2000, y 0..3000, jaune en bas).
- [ ] Règles 2027 à prendre en compte côté robot : évitement des **PAMI** (le LiDAR voit-il un objet de
      150 mm ?), **support de balise obligatoire** (sommet à 430 mm), phase d'attaque à 85 s (chrono).
- [ ] Windows Update sur la vraie base : tester l'installation robot et base (redémarrage du service via
      sudoers de `install_service.sh`), vérifier que `git fetch` marche avec les accès GitHub de la base.
- [ ] Calculateur : nombres maxi de murs / tours / douves devinés d'après le plan (4 tours, 3 douves) : à vérifier.
- [ ] Pas d'icônes pause / flèches haut-bas dans le sprite (ajouter des symboles Lucide si besoin).
- [ ] `Rasp/stop.sh` arrête encore un ancien `robot.service` ; `Rasp/exec.sh` écrit dans `/var/log/ihm.log`.

## Points d'attention

- Le serveur de la base réécrivait `Rasp/config.json` : c'est corrigé, mais si un `config.json`
  modifié apparaît dans `git status` après un test local, le remettre (`git checkout -- Rasp/config.json`).
- Tests locaux à côté d'une base lancée : ports configurables (`STK_HTTP_PORT`, `STK_ZMQ_ROBOT_PORT`,
  `STK_ZMQ_BASE_PORT`), `STK_NO_VISION=1` pour ne pas ouvrir la webcam.
- Depuis `localhost`, la base fait confiance (pas de PIN demandé) : tester le PIN via l'IP réseau du PC.
