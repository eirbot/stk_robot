# 🏰 Robot Eirbot - Eurobot 2026 : The Two Towers

![Banner](https://img.shields.io/badge/Eurobot-2026-blue?style=for-the-badge&logo=robot)
![License](https://img.shields.io/badge/License-Apache%202.0-green?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.9+-yellow?style=for-the-badge&logo=python)
![PlatformIO](https://img.shields.io/badge/Firmware-PlatformIO-orange?style=for-the-badge&logo=cplusplus)
![Status](https://img.shields.io/badge/Status-In%20Development-critical?style=for-the-badge)

> **Code source officiel du robot de l'association Eirbot pour la Coupe de France de Robotique 2026.**
> Une architecture hybride alliant la puissance de calcul d'une Raspberry Pi pour la stratégie et la réactivité de microcontrôleurs pour l'asservissement.

---

## 📑 Sommaire

1. [Architecture Globale](#-architecture-globale)
2. [Fonctionnalités Clés](#-fonctionnalités-clés)
3. [Structure du Projet](#-structure-du-projet)
4. [Installation & Démarrage](#-installation--démarrage)
5. [Hardware](#-hardware)
6. [Licence](#-licence)

---

## 🏗 Architecture Globale

Le robot repose sur une communication **Haut Niveau (High-Level)** et **Bas Niveau (Low-Level)**.

```mermaid
graph TD
  subgraph "🧠 Cerveau (Raspberry Pi 4)"
    Web[Interface Web / Flask]
    Strat[Moteur de Stratégie]
    Blockly[Studio No-Code]
    Lidar[Évitement Lidar]
    
    Web <--> Strat
    Blockly -->|Génère .py| Strat
    Lidar --> Strat
  end

  subgraph "💪 Muscles (Microcontrôleurs)"
    ESP[ESP32 / Teensy]
    Motors[Asservissement Moteurs]
    Actuators[Actionneurs & Servos]
    
    ESP --> Motors
    ESP --> Actuators
  end

  Strat <-->|Liaison Série / USB| ESP
```

## 🚀 Fonctionnalités Clés

### 🎨 Studio de Stratégie "No-Code"

Plus besoin de recompiler le code entre deux matchs !

- Interface Blockly intégrée hébergée sur le robot.
- Création de stratégies en Drag & Drop.
- Simulateur 2D temps réel pour valider les déplacements avant le match.

### 🌐 Dashboard de Contrôle

- Interface Web accessible via Wi-Fi (`http://<ip_robot>:5000`).
- Retour vidéo, état des capteurs et logs en direct.
- Lancement et arrêt d'urgence à distance.

### 📍 Navigation Avancée

- Localisation : odométrie des roues, recalée par la caméra zénithale de la base.
- Trajectoires Courbes : Génération de chemins fluides via courbes de Bézier.
- Évitement dynamique des adversaires.

---

## 📂 Structure du Projet

L'arborescence est divisée pour séparer clairement les responsabilités :

```
robot_3a_2026/
├── 🐍 Rasp/                   # --- HAUT NIVEAU (Python) ---
│   ├── ihm/                   # Serveur Web, Dashboard et Blockly
│   ├── LiDAR/                 # Driver Lidar et détection d'obstacles
│   ├── strat/                 # Logique de match, automates et actions
│   ├── interface_deplacement/ # Pathfinding et communication Série
│   ├── utils/                 # Gestion Audio, LEDs, Caméra
│   └── main_robot.py          # Point d'entrée principal
│
├── ⚡ ESP/                    # --- BAS NIVEAU (C++ / PlatformIO) ---
│   ├── platformio.ini         # Envs Motor, Actionneurs, native (tests PC)
│   ├── src/motors/            # Firmware moteurs (odométrie, GoTo, liaison série)
│   ├── src/actuators/         # Firmware actionneurs
│   └── test/                  # Tests PC du firmware moteurs (pio test -e native)
│
├── 🖥 Base/                   # Base déportée : serveur web (Go) et vision zénithale
├── 🧪 test/                   # Tests Python / JS (tools/run_tests.sh)
├── 🔧 tools/                  # Déploiement, simulation, réglages
└── 📄 docu/                   # Documentation, règles et datasheets
```

---

## 🛠 Installation & Démarrage

### 1. Prérequis Raspberry Pi (Cerveau)

Le code Python nécessite Python 3.9+.

```bash
# Cloner le dépôt
git clone https://github.com/ton-repo/robot_3a_2026.git
cd robot_3a_2026/Rasp

# Installer les dépendances
pip install -r requirements.txt

# Lancer le robot (Stratégie + Serveur Web)
python main_robot.py
```

L'interface est ensuite accessible sur le port 5000.

### 2. Prérequis Microcontrôleur (Muscles)

Le code bas niveau utilise PlatformIO.

- Installer VSCode.
- Installer l'extension PlatformIO IDE.
- Ouvrir le dossier racine du projet.
- Connecter la carte via USB et cliquer sur le bouton Upload (flèche droite) dans la barre d'état.

### 3. Déploiement (PC de dev -> base / robot)

`tools/deploy.sh` (aide : `tools/deploy.sh -h`, `--dry-run` pour voir les commandes sans les lancer) :

```bash
tools/deploy.sh base          # base : git pull, Base/build.sh, redémarrage du service base_stk
tools/deploy.sh robot         # rsync de Rasp/ vers le robot + fichier VERSION + redémarrage de robot_launcher
tools/deploy.sh --from-base robot   # idem mais poussé depuis la base
tools/deploy.sh esp motors    # compile, fusionne et flashe l'ESP moteurs via la Rasp (esp arms : actionneurs)
tools/deploy.sh status        # versions déployées et état des services
```

Hôtes et chemins : variables `BASE_HOST`, `ROBOT_HOST`, `ROBOT_USER`, `ROBOT_KEY`… (voir `-h`).
Version : `GET /api/version` sur la base, fichier `~/Documents/robot_stk/VERSION` sur le robot.
Service de la base, une seule fois : `sudo Base/install_service.sh` (logs : `journalctl -u base_stk -f`).

### 4. Code PIN de l'interface

Les commandes de l'interface (match, réglages, déplacements, actionneurs, stratégies, flash,
mise à jour) demandent un code PIN, mémorisé 12 h par appareil. STOP, la consultation, l'écran du
robot et la base elle-même restent libres. Le PIN se définit sur la base, au choix :

```bash
echo 4242 > Base/pin.txt        # fichier non versionné
STK_PIN=4242 ./Base/build.sh --run
```

Sans PIN défini, la protection est désactivée (pratique sur le PC de dev).

### 5. Tests et simulation (sans robot)

```bash
tools/run_tests.sh [--rapide]            # Python, JavaScript, Go (--rapide : sans test_strategies)
tools/check_strategy.py 3b_pouss_plus --team JAUNE   # trajectoire d'une stratégie
./Base/build.sh --run &                  # base locale, puis :
python3 tools/robot_sim.py               # vrai code robot + faux matériel, piloté depuis http://localhost:8080
```

Le robot est la source de vérité de l'état du match et de sa config (`Rasp/core/match_state.py`,
`Rasp/core/config_store.py`) ; la base affiche et transmet. Repères : `Rasp/core/frames.py`.

---

## 🔧 Hardware

| Composant | Modèle | Rôle |
|-----------|--------|------|
| Ordinateur de bord | Raspberry Pi 4B | Intelligence, Vision, Web |
| Microcontrôleur | ESP32 / Teensy 4.1 | Gestion temps réel, PWM, Encodeurs |
| Lidar | RPLIDAR C1 / M1 | Détection d'obstacles et recalage |
| Moteurs | Stepper avec MKS | Propulsion |
| Actionneurs | Servomoteurs AX-12 | Manipulation des éléments de jeu (Tour) |

---

## 📜 Licence

Ce projet est sous licence Apache License 2.0.

Copyright 2025-2026 Équipe Eirbot.

Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the specific language governing permissions and limitations under the License.