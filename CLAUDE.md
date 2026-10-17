# stk_robot — Eurobot 2026 (Eirbot)

Répondre en français. Réponses courtes : le résultat, pas le récit des étapes.

## Carte du repo (ne pas réexplorer)
- `Rasp/` : Python sur la Raspberry du robot. `main_robot.py`, `launcher.py`, `ihm/` (shared.py = état global, zmq_client.py = lien base), `strat/` (actions.py = primitives goto/set_pos/symétrie, `strategies/` = stratégies Blockly .xml/.py), `interface_deplacement/esp_motors.py`, `interface_actionneur/`, `LiDAR/` (lidar_udp.cpp + lidar_thread.py, évitement uniquement), `config.json`.
- `src/`, `include/`, `platformio.ini` : firmware ESP32 (envs `Motor`, `Actionneurs`). Trame odométrie `T x y theta` (ComWithRasp.cpp).
- `Base/Web/` : serveur Go (fiber + zmq4/cgo) -> binaire `Base/base_stk`, compilé par `Base/build.sh`, lancé depuis `Base/`. Pages `templates/*.html` + `static/js/*.js`.
- `Base/Vision/` : `vision_deporte_worker.py` (caméra zénithale -> pose) + sous-module `vision_deporte/` (uv).
- `docu/` : règles Eurobot (PDF), protocole LiDAR.

## Repère et conventions
- Repère robot : X = largeur 0..2000 mm, Y = longueur -1500..1500 mm, theta en degrés (0 = X+, 90 = Y+). Symétrie équipe JAUNE : y -> -y, theta -> -theta (`actions.py::_apply_sym`).
- map.js : conversions uniquement via `robotToThree` / `threeToRobot`.
- Localisation = odométrie ESP + recalage ponctuel caméra (`actions.py`). Pas d'EKF, pas de localisation LiDAR.
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
