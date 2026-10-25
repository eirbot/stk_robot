# stk_robot — Eurobot 2026 (Eirbot)

Répondre en français. Réponses courtes : le résultat, pas le récit des étapes.

## Suivi (obligatoire)
- En début de session : lire `SUIVI.md` (ce qui est fait, ce qui reste, état du déploiement).
- En fin de tâche : mettre `SUIVI.md` à jour — ajouter ce qui a été fait dans « Fait », cocher ou
  retirer les éléments terminés de « À faire », ajouter ce qui reste ou ce qu'on a découvert,
  mettre à jour « État du dépôt » (commits poussés ou non, ce qui est déployé) et la date.
- Ne pas y recopier l'historique git en détail : l'essentiel, pour reprendre le travail ailleurs.

## Carte du repo (ne pas réexplorer)
- `Rasp/` : Python sur la Raspberry du robot. `main_robot.py`, `launcher.py`, `hardware.py` (ESP, caméra : créés une fois par `hardware.start()`, lus via `hardware.esp`...), `ihm/` (shared.py = état global, zmq_client.py = lien base), `strat/` (actions.py = primitives goto/set_pos/symétrie, `strategies/` = stratégies Blockly .xml/.py), `interface_deplacement/esp_motors.py`, `interface_actionneur/`, `LiDAR/` (lidar_udp.cpp + lidar_thread.py, évitement uniquement), `config.json`.
- `ESP/` : projet PlatformIO des deux ESP32 (`ESP/platformio.ini`, commandes `pio` lancées depuis `ESP/` ou avec `-d ESP`).
  `ESP/src/motors/` : firmware moteurs (env `Motor`), protocole série dans `protocol.h` (`G id x y theta` -> `D id` / `A id`, trame `T x y theta`) ;
  code pur testé sur PC (`ESP/test/`, env `native`) ; seuls `steppers`, `motion_task`, `link`, `main` touchent au matériel.
  `ESP/src/actuators/` : firmware actionneurs (env `Actionneurs`).
- `Base/Web/` : serveur Go (fiber + zmq4/cgo) -> binaire `Base/base_stk`, compilé par `Base/build.sh`, lancé depuis `Base/`. Pages `templates/*.html` + `static/js/*.js` ; les grosses pages ont un dossier par page
  (`static/js/debug/`, `blockly/`, `controle/`, `map/`) : fichiers classiques chargés dans l'ordre par le template, portée
  globale partagée (les `onclick=` des templates appellent ces fonctions). Menus Win95 par page : `win95_apps.js`.
- `Base/Vision/` : `vision_deporte_worker.py` (caméra zénithale -> pose) + sous-module `vision_deporte/` (uv).
- `docu/` : règles Eurobot (PDF), protocole LiDAR.
- `Rasp/core/` : modules purs, testés sans robot : `match_state.py` (seul écrivain de l'état du match), `config_store.py` (config du robot), `frames.py` (repères), `localisation.py` (fusion odométrie + caméra), `obstacles.py` (tours LiDAR -> état d'évitement L 0..3, points hors table), `vision_geom.py` (caméra embarquée : pose des tags ArUco dans le repère robot), `planif.py` (carte de coûts + A* pour `aller()`), `temps_match.py` (durées, retour de fin), `decision.py` (stratégie dynamique : choix de l'objectif), `preflight.py` (check-list avant match), `reglage_fusion.py` (analyse de `tools/regler_fusion.py` et de la calibration auto `strat/calibration.py`).
- `Rasp/Vision/` : `aruco.py` (détection ArUco + service `hardware.vision`), `mjpeg_streamer.py` (flux 8081). Env uv racine (`pyproject.toml`) pour les tests numpy/OpenCV.
- `tools/` : `deploy.sh`, `run_tests.sh`, `robot_sim.py` (robot simulé), `check_strategy.py`, `regler_fusion.py` (réglage de la fusion depuis un enregistrement), `win95_icons.py` (génère `static/icons/win95.svg`, ne pas éditer le SVG à la main), `calibrer_camera.py` (échelle/repère caméra). Tests Python/JS dans `test/`.

## Repère et conventions
- Repère robot : X = largeur 0..2000 mm, Y = longueur -1500..1500 mm, theta en degrés (0 = X+, 90 = Y+). Symétrie équipe JAUNE : y -> -y, theta -> -theta (`actions.py::_apply_sym`).
- map.js : conversions uniquement via `robotToThree` / `threeToRobot`.
- Localisation = fusion odométrie ESP + caméra zénithale (`Rasp/core/localisation.py`, Kalman simple avec compensation de latence). L'ESP garde son repère odo ; la Rasp tient la transformation odo -> table (`shared.loc`), `robot_pos` = pose fusionnée, les GoTo sont convertis (`esp_motors.goto`). Pas de localisation LiDAR.
- Après modif d'un JS/CSS : incrémenter `?v=` dans le template qui le charge (cache navigateur).

## Machines
- `ssh base` (192.168.10.2, repo `~/Documents/stk_robot`) : fait tourner `base_stk` et est le serveur DHCP (dnsmasq) du LAN robot.
- `ssh eirbot` : la Raspberry du robot.
- Un changement de Go impose `./Base/build.sh` SUR la base (glibc), jamais commiter un binaire compilé sur un autre PC.

## Économie de tokens
- Chercher avant de lire : `grep -n` / `rg` puis lire seulement la plage utile (`sed -n a,bp`, `Read` avec offset/limit). Ne jamais lire en entier un fichier > 300 lignes sans raison.
- Ne pas ouvrir : `Base/Web/static/js/vendor/`, `socket.io.js`, `*.min.js`, `*_compressed.js`, `.pio/`, `compile_commands.json`, `embedded/`, binaires (`base_stk`, `.elf`, `.bin`), PDF/audio/`.ods`, `.venv/`, `__pycache__/`, `Rasp/strat/strategies/*.xml` (une ligne géante).
- Pas de sous-agent pour une recherche ciblée (fichier ou symbole connu) : grep direct. Sous-agent `Explore` seulement pour un balayage large, avec une question précise et une réponse courte attendue.
- Regrouper les commandes indépendantes dans un seul appel ; filtrer les sorties (`| head`, `| tail`, `grep`, `--stat`, `-q`).
- Ne pas relire un fichier qu'on vient d'éditer ; ne pas afficher de longs diffs si `--stat` suffit.
- Valider à moindre coût : `node --check`, `python3 -m py_compile`, `go vet ./...` (dans `Base/Web`), plutôt que lancer l'appli.
