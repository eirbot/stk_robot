# strat/actions.py
import time
import math
import ihm.shared as shared

# --- AJOUT AU PATH GLOBAL POUR LES IMPORTS CROSS-FOLDERS ---
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- COM ACTIONNEURS (via module dédié) ---
try:
    from interface_actionneur.esp_actionneur import ESPActionneurs
    actionneurs = ESPActionneurs()
    actionneurs.start()
except Exception as e:
    print(f"⚠️ Attention : Erreur de chargement du module Actionneur ({e}) -> Mode simulation")
    actionneurs = None

# --- VISION KAPLAS ---
try:
    # On importe ta nouvelle classe cam
    from Vision.cam import cam
    print("[VISION] Lancement de la caméra...")
    # On initialise avec l'état défini dans la config
    cam_enabled = shared.cfg.get('camera', {}).get('enabled', True)
    vision_cam = cam(use_camera=cam_enabled)
except Exception as e:
    print(f"  Attention : Erreur de chargement du module Vision ({e}) -> Mode aveugle")
    vision_cam = None

try:
    # On essaie d'importer la classe ESPMotors
    from interface_deplacement.esp_motors import ESPMotors
    esp = ESPMotors()
    esp.start()

except ImportError as e:
    print(f"⚠️ Attention : Modules de déplacement non trouvés ({e}) -> Mode Simulation pur")
    esp = None

# --- CONSTANTES ---
TABLE_WIDTH = 3000
TIME_TO_RETURN = 90

class EndOfMatchException(Exception):
    pass

class RobotActions:
    def __init__(self):
        self.is_returning = False
        shared.state["is_returning"] = False
        self.base_pos = None # (x, y, theta) stockés avant symétrie

    @property
    def is_yellow(self):
        return shared.state["team"] == "JAUNE"

    def _check_time(self):
        # On ne lève plus d'exception automatique à 90s
        # On vérifie juste si le match est arrêté (STOP)
        pass

    def _check_abort(self, manual=False):
        if not manual and not shared.state["match_running"]: raise Exception("Stop")
        self._check_time()

    def _apply_sym(self, x, y, theta=None):
        """Symétrie axiale pour l'équipe JAUNE (Y négatif)"""
        if self.is_yellow:
            new_x = x
            new_y = -y
            # Pour une symétrie sur l'axe Y (miroir horizontal), l'angle s'inverse
            new_theta = (-theta) % 360 if theta is not None else None
            return new_x, new_y, new_theta
        return x, y, theta
    
    def set_pos(self, x, y, theta):
        """
        Définit la position du robot (Triche / Recalage).
        Met à jour l'IHM Web ET l'odométrie de l'ESP32.
        """
        # On mémorise la première position comme étant la "Base" pour le retour fin de match
        if self.base_pos is None:
            self.base_pos = (x, y, theta)
            print(f"[ACTION] Base enregistrée : ({x}, {y}, {theta}°)")

        # 1. Calcul de la position réelle (Symétrie équipe)
        real_x, real_y, real_theta = self._apply_sym(x, y, theta)
        
        # 2. Mise à jour Interface Web (Shared)
        shared.robot_pos.update({'x': real_x, 'y': real_y, 'theta': real_theta})
        print(f"[ACTION] SET_POS -> ({real_x}, {real_y}, {real_theta}°)")

        # 3. Envoi à l'ESP32 (Reset Odométrie)
        if esp:
            esp.set_pos(real_x, real_y, real_theta)
        else:
            print("[SIMU] SET_POS virtuel (Pas de com)")


    def goto(self, x, y, theta, manual=False, real=False):
        """
        Déplacement en ligne droite + Envoi ESP32
        """
        self._check_abort(manual=manual)
        
        if not real:
            real_x, real_y, real_theta = self._apply_sym(x, y, theta)
        else:
            real_x, real_y, real_theta = x, y, theta

        if esp:
            success = esp.goto(real_x, real_y, real_theta)
            while not success:
                print(f"[ACTION] 🔄 GOTO annulé par l'ESP (Obstacle), recalcul et relance vers ({real_x}, {real_y}, {real_theta}°)")
                self._check_abort()
                time.sleep(0.5)
                success = esp.goto(real_x, real_y, real_theta)
        else:
            print("[SIMU] GOTO virtuel (Pas de com)")
        
    def set_speed(self, vx, vtheta):
        """Consigne de vitesse pour contrôle joystick."""
        if esp:
            esp.set_speed(vx, vtheta)
        else:
            print(f"[SIMU] SET_SPEED ({vx}, {vtheta}) virtuel")

    def stop(self):
        print("[ACTION] STOP")
        if esp:
            esp.stop_robot()
        else:
            print("[SIMU] STOP virtuel (Pas de com)")

    def set_lidar_state(self, val):
        """Définit l'état du LiDAR sur l'ESP32 (0: Libre, 1: Stop, 2: Front, 3: Back)"""
        if esp:
            esp.set_lidar_state(val)
        else:
            print(f"[SIMU] SET LIDAR STATE {val} virtuel")

    def toggle_lidar(self):
        """Ancienne fonction de toggle (Legacy)"""
        print("[ACTION] TOGGLE LIDAR")
        if esp:
            # On simule un toggle simple 0/1
            new_val = 1 if shared.state.get("obstacle_detected", False) else 0
            esp.set_lidar_state(1 - new_val)
        else:
            print("[SIMU] TOGGLE LIDAR virtuel")

    def approcheKapla(self) -> bool:
        """Approche visuelle des Kaplas. Retourne True si l'alignement a réussi, False sinon."""
        self._check_abort()
        print("[ACTION] Recalage visuel : Latéral (Y) puis Profondeur (X)...")
        self.approche_reussie = False

        if not vision_cam:
            print("[VISION] Caméra indisponible, mouvement à l'aveugle.")
            x_robot, y_robot, theta_robot = shared.robot_pos['x'], shared.robot_pos['y'], shared.robot_pos['theta']
            x = x_robot - math.cos(math.radians(theta_robot)) * 100
            y = y_robot - math.sin(math.radians(theta_robot)) * 100
            self.goto(x, y, theta_robot)
            self.goto(0, 0, 0)
            return False

        MAX_TENTATIVES = 3
        x_garde, y_garde, theta_garde = shared.robot_pos['x'], shared.robot_pos['y'], shared.robot_pos['theta']

        for tentative_globale in range(MAX_TENTATIVES):
            self._check_abort()
            print(f"\n[VISION] === Tentative globale {tentative_globale + 1}/{MAX_TENTATIVES} ===")
                
            # ----- ÉTAPE 2 : LECTURE POSITION DEPUIS LA GARDE -----
            if vision_cam.check_aruco_position():
                print("[VISION] ✅ Alignement parfait depuis la garde ! Approche finale...")
                self.approche_reussie = True
                return True

            if not vision_cam.is_salvagable():
                print("[VISION] ArUco non visible depuis la garde, on abandonne cette tentative.")
                return False

            err_x, err_y, err_angle = vision_cam.get_errors()

            if err_x is None:
                print("[VISION] ArUco non visible depuis la garde, on abandonne cette tentative.")
                return False

            vision_cam.save_debug(prefix=f"garde_T{tentative_globale+1}")
            print(f"[VISION] ❌ Non aligné (Y={err_y:.1f}mm, A={err_angle:.1f}°). Recul + Recalage...")
            
            # Recul de 180mm
            x_actuel, y_actuel, theta_actuel = shared.robot_pos['x'], shared.robot_pos['y'], shared.robot_pos['theta']
            theta_rad = math.radians(theta_actuel)
            recul = 180
            self.goto(x_actuel - recul * math.cos(theta_rad), y_actuel - recul * math.sin(theta_rad), theta_actuel, real=True)
            time.sleep(0.5)

            # Correction Y et angle uniquement
            x_actuel, y_actuel, theta_actuel = shared.robot_pos['x'], shared.robot_pos['y'], shared.robot_pos['theta']
            theta_rad = math.radians(theta_actuel)
            cible_x = x_actuel - (err_y*0.9) * math.sin(theta_rad)
            cible_y = y_actuel + (err_y*0.9) * math.cos(theta_rad)
            self.goto(cible_x, cible_y, theta_actuel, real=True)
            time.sleep(0.5)

            # Avance de 180mm
            x_actuel, y_actuel, theta_actuel = shared.robot_pos['x'], shared.robot_pos['y'], shared.robot_pos['theta']
            theta_rad = math.radians(theta_actuel)
            avance = 180
            self.goto(x_actuel + (avance+err_x*0.9) * math.cos(theta_rad), y_actuel + (avance+err_x*0.9) * math.sin(theta_rad), theta_actuel+err_angle*0.9, real=True)
            time.sleep(0.5)

            # On reboucle : on va ré-avancer à la garde et re-vérifier

        print("[VISION] ❌ ÉCHEC : Impossible de s'aligner après toutes les tentatives !")
        self.approche_reussie = False
        return False

    def thermometre(self):
        """Déploie le thermomètre (actionneur selon la couleur d'équipe)."""
        self._check_abort()
        print(f"[ACTION] Déploiement Thermomètre (Équipe {'JAUNE' if self.is_yellow else 'BLEUE'})...")
        if actionneurs:
            actionneurs.pose_temperature(self.is_yellow)
        else:
            print("[SIMU] Thermomètre (pas d'actionneurs)")

        self.attendre(1)
        x_actuel, y_actuel, theta_actuel = shared.robot_pos['x'], shared.robot_pos['y'], shared.robot_pos['theta']

        self.goto(x_actuel, 1025, -90, real=False)

        if actionneurs:
            actionneurs.pose_camera()
        else:
            print("Feur")

    def attendre(self, secondes: float):
        """Attend un nombre de secondes (interruptible par abort)."""
        self._check_abort()
        print(f"[ACTION] Attente de {secondes}s...")
        fin = time.time() + secondes
        while time.time() < fin:
            self._check_abort()
            time.sleep(0.05)

    def prendreKapla(self):
        self._check_abort()
        print(f"[ACTION] Analyse couleurs pour les 4 Kaplas (Equipe JAUNE={self.is_yellow})...")
        
        if vision_cam:
            # On déclenche une nouvelle capture et analyse
            actionneurs.pose_deploy()

            vision_cam.check_aruco_position()
            vision_cam.save_debug(prefix="prise")
            
            actionneurs.pose_grab()

            # On récupère le tableau de booléens (True = bonne couleur)
            bonnes_couleurs = vision_cam.get_colors(self.is_yellow)
            actionneurs_ids = [i+1 for i in range(len(bonnes_couleurs)) if not bonnes_couleurs[i]]
            actionneurs.pose_retourne(actionneurs_ids)
            
        time.sleep(1)

    def poseKapla(self):
        self._check_abort()
        actionneurs.pose_poser()
        actionneurs.pose_camera()

    def pousse_kapla(self):
        self._check_abort()
        print("[ACTION] Pousse Kapla")
        if vision_cam:
            # On récupère le tableau de booléens (True = bonne couleur)
            print(vision_cam.check_aruco_position())
            vision_cam.save_debug(prefix="pousse")
            bonnes_couleurs = vision_cam.get_colors_pousse(self.is_yellow)
            if len(bonnes_couleurs) < 3:
                print(f"[VISION] Detection incomplète ({len(bonnes_couleurs)}/3), complétion par défaut.")
                while len(bonnes_couleurs) < 4:
                    bonnes_couleurs.append(True)

        else:
            print("[VISION/SIMU] Simulation des Kaplas (Caméra non dispo).")
            bonnes_couleurs = [True, True, True, True]
        
        x_actuel = shared.robot_pos['x']
        y_actuel = shared.robot_pos['y']
        theta_actuel = shared.robot_pos['theta']
        theta_rad = math.radians(theta_actuel)

        print("bonnes_couleurs = ", bonnes_couleurs)

        avancer_mm = 25
        if bonnes_couleurs[0] == True:
            print("bonnes_couleurs[0] = True")
            avancer_mm += 0
            if bonnes_couleurs[1] == True:
                print("bonnes_couleurs[1] = True")
                avancer_mm += 50 # on met les 2 premier kaplas
            else :
                print("bonnes_couleurs[1] = False")
                if bonnes_couleurs[2] == True:
                    avancer_mm += 100 # on met les 3 premier kaplas
                # pas de else on ne met que le premier kapla
        else :
            print("bonnes_couleurs[0] = False")
            if bonnes_couleurs[1] == True and bonnes_couleurs[2] == True :
                print("bonnes_couleurs[1] = True and bonnes_couleurs[2] = True")
                avancer_mm += 100 # on met les 3 premier kaplas
            else :
                print("bonnes_couleurs[1] = False and bonnes_couleurs[2] = False")
                avancer_mm += 250 # on met les 3 dernier kaplas
        
        print("avancer_mm =", avancer_mm)

        x_kapla = x_actuel + avancer_mm * math.cos(theta_rad)
        y_kapla = y_actuel + avancer_mm * math.sin(theta_rad)

        self.goto(x_kapla, y_kapla, theta_actuel, real=True)
        
    def GoBase(self):
        self.is_returning = True
        shared.state["is_returning"] = True
        print("⚡ RETOUR BASE")
        if self.base_pos:
            bx, by, bt = self.base_pos
            # On revient aux coordonnées de départ avec un angle inversé (180°)
            target_theta = (bt + 0)
            # Normalisation entre -180 et 180 (optionnel mais propre)
            while target_theta > 180: target_theta -= 360
            while target_theta <= -180: target_theta += 360
            
            self.goto(bx + 650, by + 100, target_theta)
            self.goto(bx, by + 100, target_theta)
        else:
            # Fallback historique si set_pos n'a pas été appelé
            self.goto(250, 0, 180)
        time.sleep(1)

    def wait_until_and_return(self, target_second):
        self._check_abort()
        print(f"[ACTION] Attente de la seconde {target_second} pour retour base...")
        while shared.state["match_running"]:
            elapsed = time.time() - shared.state["start_time"]
            if elapsed >= target_second:
                break
            time.sleep(0.5)
        self.GoBase()

    def play_animation(self, anim_name):
        self._check_abort()
        print(f"[ACTION] Playing Animation: {anim_name}")
        shared.send_led_cmd(f"PLAY:{anim_name}")

    def play_sound(self, sound_name):
        self._check_abort()
        print(f"[ACTION] Playing Sound: {sound_name}")
        shared.audio.play(sound_name)


    def cmd_actionneurs(self, command_string=None, act1=None, act2=None, act3=None, act4=None):
        """
        Interface Blockly vers le module Actionneur dédié.
        """
        self._check_abort()
        if actionneurs:
            if command_string is not None:
                actionneurs.send_raw(command_string)
            else:
                actionneurs.send_cmd(act1, act2, act3, act4)
        else:
            print("[SIMU] Pas d'interface Actionneur connectée (Mode sans matériel).")