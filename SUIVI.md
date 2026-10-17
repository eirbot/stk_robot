# Suivi du projet — à lire en début de session, à mettre à jour en fin de tâche

Dernière mise à jour : 2026-10-18. Compétition dans plus de 200 jours (pas avant ~mai 2027) :
les refontes sont acceptées.

## État du dépôt

- Branche `base_deporte`, **16 commits en avance sur origin, non poussés**.
- **Rien n'a été déployé** sur la base ni sur le robot depuis ces commits ; aucun test sur le vrai matériel.
- Tests : `tools/run_tests.sh` (tout passe : 49 Python, 4 JS, Go). `--rapide` saute test_strategies (~70 s).

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
  `playPrev()` / `playNext()` (appelées par la page Sons) n'existaient pas : ajoutées.
- Affichage téléphone ; mode test (pas d'arrêt à 100 s) ; notifications (`toast()`) ; pastille
  « Robot hors ligne » ; versions du code dans Debug.

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

## À faire

### Sur le matériel (priorité, rien de tout ça n'a été essayé)
- [ ] Pousser les commits, puis déployer **base et robot ensemble** (le protocole d'état a changé) :
      `tools/deploy.sh base` puis `tools/deploy.sh robot`.
- [ ] Flasher l'ESP moteurs (`tools/deploy.sh esp motors`) ; vérifier : pas de faux déclenchement du
      watchdog en match (`watchdog_count` dans esp_motors), arrêt si on débranche l'USB, pas de reprise
      au rebranchement. Si faux déclenchements : passer `RASP_TIMEOUT_MS` à 400-500.
- [ ] Sur la base : arrêter le `base_stk` lancé à la main, puis `sudo Base/install_service.sh`.
- [ ] Définir le PIN dans `Base/pin.txt` sur la base.
- [ ] Vérifier un match complet : tirette, fin à 100 s, réarmement par la tirette après un match,
      équipe/LEDs, mode test, écran 7" du robot.
- [ ] Recharger / vérifier la batterie (alerte < 18 V, rétablie > 19,5 V : seuils peut-être à revoir).

### Code
- [ ] IP en dur restantes côté Python : `Rasp/main_robot.py` et `Rasp/ihm/__init__.py`
      (`server_ip` par défaut), `Rasp/utils/system_info.py` (cible de ping).
- [ ] Fusion odométrie + caméra (aujourd'hui recalage ponctuel seulement, dans `actions.py`).
- [ ] Menu contextuel de la page Sons : peut dépasser l'écran sur téléphone.
- [ ] Pas d'icônes pause / flèches haut-bas dans le sprite (ajouter des symboles Lucide si besoin).
- [ ] `Rasp/stop.sh` arrête encore un ancien `robot.service` ; `Rasp/exec.sh` écrit dans `/var/log/ihm.log`.

## Points d'attention

- Le serveur de la base réécrivait `Rasp/config.json` : c'est corrigé, mais si un `config.json`
  modifié apparaît dans `git status` après un test local, le remettre (`git checkout -- Rasp/config.json`).
- Tests locaux à côté d'une base lancée : ports configurables (`STK_HTTP_PORT`, `STK_ZMQ_ROBOT_PORT`,
  `STK_ZMQ_BASE_PORT`), `STK_NO_VISION=1` pour ne pas ouvrir la webcam.
- Depuis `localhost`, la base fait confiance (pas de PIN demandé) : tester le PIN via l'IP réseau du PC.
