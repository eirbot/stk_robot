# Agent Context: Robot 3A - Eurobot 2026

## 🤖 Projet & Objectif
Développement d'un robot pour la **Coupe de France de Robotique 2026**.
- **Cerveau :** Raspberry Pi (IA, Stratégie, IHM, LiDAR, Vision).
- **Contrôle Bas Niveau :** 2x ESP32 (Moteurs & Actionneurs).
- **Mission :** Manipulation de Kaplas, navigation précise et interface interactive.

## 🛠️ Stack Technique
- **Raspberry Pi (Python 3.11+) :**
  - **IHM :** Flask + SocketIO + PyWebView (Interface 7").
  - **Stratégie :** Thread IA dédié, support Blockly (XML).
  - **Localisation :** LiDAR RPLiDAR C1M1 + Beacons (balises fixes) + EKF.
  - **Évitement :** Détection dynamique de l'adversaire via LiDAR.
- **ESP32 (C++/PlatformIO) :**
  - **ESP32 "Motor" :** 2x NEMA 17 + MKS Servo 42D pilotés en **Step/Dir**.
  - **ESP32 "Actionneur" :** 4x NEMA 11 (Ascenseurs), 2x Servos, 1x Vérin (piloté en **PWM**).
  - **Librairies :** AccelStepper, ESP32Servo, ArduinoJson.

## 📁 Structure du Projet
- `/Rasp` : Code principal Python (Threads : Hardware, Strat, IHM, Buttons, Timer).
- `/embedded/src` : Code source C++ pour les ESP32 (Environnements : `Motor`, `Actionneur`).
- `/docu` : Documentation technique, protocole LiDAR et règles Eurobot.

## 📜 Règles de Développement (Mandates)
1. **Sécurité Matérielle :** Toujours vérifier les limites logicielles des ascenseurs et les timeouts de communication.
2. **Communication Pi-ESP32 :** Utilise principalement le format JSON via Liaison Série.
3. **Localisation :** Le LiDAR est critique ; toute modification du code `Rasp/hardware_thread.py` ou `Rasp/LiDAR/` doit préserver la détection des balises.
4. **Actionneurs :** Le vérin est géré comme un Servo (PWM) sur l'ESP Actionneur.
5. **Validation :** Avant de suggérer une modification bas niveau, vérifier l'impact sur les environnements `embedded/platformio.ini`.

## 💡 Conseils de Travail
- Pour le **déplacement**, réfère-toi à `Rasp/interface_deplacement.py` et `Rasp/bezier.py`.
- L'état global du robot est centralisé dans `Rasp/ihm/shared.py`.
- En cas de bug de communication, vérifie les ports dans `Rasp/config.json` (ex: `/dev/lidar`).
