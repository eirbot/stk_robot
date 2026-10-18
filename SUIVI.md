# Suivi du projet — à lire en début de session, à mettre à jour en fin de tâche

Dernière mise à jour : 2026-10-19. Compétition dans plus de 200 jours (pas avant ~mai 2027) :
les refontes sont acceptées.

## État du dépôt

- Branche `base_deporte` poussée jusqu'au commit Clippy ; fusion odométrie + caméra **non commitée**.
- **Rien n'a été déployé** sur la base ni sur le robot depuis ces commits ; aucun test sur le vrai matériel.
- Tests : `tools/run_tests.sh` (tout passe : 67 Python, 4 JS, Go). `--rapide` saute test_strategies (~70 s).
- Page Règlement / Internet Explorer (2026-10-19) **non commitée**, rien de déployé.
- Sur ce PC, `test_robot_integration` échoue faute de `numpy` dans le Python système (environnement, pas le code).

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
- Simulateur et tests : `test/test_localisation.py`, `test/test_regler_fusion.py` ; `test_esp_heartbeat.py` n'était pas lancé par
  `run_tests.sh` (écrit pour pytest) : corrigé.

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
- [ ] Régler la fusion sur le vrai robot : rouler 2-3 min caméra allumée (déplacements, rotations,
      arrêts de quelques secondes), récupérer `Documents/robot_stk/logs/localisation/loc_*.csv` et lancer
      `tools/regler_fusion.py <fichier> --appliquer <config.json du robot>` (config.json n'est pas déployé).
      L'outil donne aussi l'erreur de diamètre de roue / d'entraxe à corriger dans le firmware.
      Vérifier que les rattrapages de fin de goto ne font pas de demi-tours inutiles.
- [ ] Afficher l'état de la fusion (écart-type, mesures acceptées/rejetées) dans Debug ou sur la carte.
- [ ] IP en dur restantes côté Python : `Rasp/main_robot.py` et `Rasp/ihm/__init__.py`
      (`server_ip` par défaut), `Rasp/utils/system_info.py` (cible de ping).
- [ ] Menu contextuel de la page Sons : peut dépasser l'écran sur téléphone.
- [ ] **Carte 2027** : redessiner la table dans map.js (carrières, remparts, douves, écuries, salles du
      trône) d'après `static/img/regles/plan.jpg` (plan : x 0..2000, y 0..3000, jaune en bas).
- [ ] Règles 2027 à prendre en compte côté robot : évitement des **PAMI** (le LiDAR voit-il un objet de
      150 mm ?), **support de balise obligatoire** (sommet à 430 mm), phase d'attaque à 85 s (chrono).
- [ ] Calculateur : nombres maxi de murs / tours / douves devinés d'après le plan (4 tours, 3 douves) : à vérifier.
- [ ] Pas d'icônes pause / flèches haut-bas dans le sprite (ajouter des symboles Lucide si besoin).
- [ ] `Rasp/stop.sh` arrête encore un ancien `robot.service` ; `Rasp/exec.sh` écrit dans `/var/log/ihm.log`.

## Points d'attention

- Le serveur de la base réécrivait `Rasp/config.json` : c'est corrigé, mais si un `config.json`
  modifié apparaît dans `git status` après un test local, le remettre (`git checkout -- Rasp/config.json`).
- Tests locaux à côté d'une base lancée : ports configurables (`STK_HTTP_PORT`, `STK_ZMQ_ROBOT_PORT`,
  `STK_ZMQ_BASE_PORT`), `STK_NO_VISION=1` pour ne pas ouvrir la webcam.
- Depuis `localhost`, la base fait confiance (pas de PIN demandé) : tester le PIN via l'IP réseau du PC.
