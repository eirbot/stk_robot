# strat/actions.py
import time
import math
import ihm.shared as shared

# --- AJOUT AU PATH GLOBAL POUR LES IMPORTS CROSS-FOLDERS ---
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import frames

# --- COM ACTIONNEURS (via module dédié) ---
try:
    from interface_actionneur.esp_actionneur import ESPActionneurs
    actionneurs = ESPActionneurs()
    actionneurs.start()
except Exception as e:
    print(f"⚠️ Attention : Erreur de chargement du module Actionneur ({e}) -> Mode simulation")
    actionneurs = None

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

_angle_diff = frames.angle_diff_deg

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
        """Coordonnées écrites côté BLEUE -> coordonnées réelles de l'équipe courante (core/frames.py)."""
        return frames.mirror_for_team(x, y, theta, team=shared.state["team"])
    
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
        
        print(f"[ACTION] SET_POS -> ({real_x}, {real_y}, {real_theta}°)")

        # 2. Envoi à l'ESP32 (Reset Odométrie) + remise à zéro de la fusion caméra
        if esp:
            esp.set_pos(real_x, real_y, real_theta)
        else:
            shared.set_known_pose(real_x, real_y, real_theta)
            print("[SIMU] SET_POS virtuel (Pas de com)")


    def goto(self, x, y, theta, manual=False, real=False):
        """
        Déplacement en ligne droite + Envoi ESP32
        """
        self._check_abort(manual=manual)

        vision_cfg = shared.cfg.get("vision_odom", {})
        if not manual and vision_cfg.get("auto", False):
            self.recalage_camera(attente_max=vision_cfg.get("attente_auto_s", 0.5))
        
        if not real:
            real_x, real_y, real_theta = self._apply_sym(x, y, theta)
        else:
            real_x, real_y, real_theta = x, y, theta

        if esp:
            success = esp.goto(real_x, real_y, real_theta, manual=manual)
            while not success:
                if manual and shared.state.get("fsm_state") == "STOPPED":
                    break
                if not manual and not shared.state.get("match_running", False):
                    break
                print(f"[ACTION] 🔄 GOTO annulé par l'ESP (Obstacle), recalcul et relance vers ({real_x}, {real_y}, {real_theta}°)")
                self._check_abort(manual=manual)
                time.sleep(0.5)
                success = esp.goto(real_x, real_y, real_theta, manual=manual)
            if success:
                self._rattrapage(real_x, real_y, real_theta, manual)
        else:
            print("[SIMU] GOTO virtuel (Pas de com)")
        
    def _rattrapage(self, x, y, theta, manual):
        """Fin de GoTo : l'ESP a visé la cible dans SON repère, calculé au départ. Si la caméra
        a corrigé la pose pendant le trajet, le robot n'est pas où on voulait : petit GoTo
        de rattrapage (l'ESP ignore une nouvelle consigne pendant un mouvement)."""
        cfg = shared.cfg.get("vision_odom", {})
        if not shared.loc.enabled():
            return
        tol_mm = cfg.get("rattrapage_mm", 25)
        tol_deg = cfg.get("rattrapage_deg", 3)
        for _ in range(int(cfg.get("rattrapages_max", 1))):
            pose = shared.loc.pose()
            if pose is None:
                return
            ecart = math.hypot(x - pose[0], y - pose[1])
            ecart_theta = frames.angle_diff_deg(theta, pose[2])
            if ecart < tol_mm and abs(ecart_theta) < tol_deg:
                return
            self._check_abort(manual=manual)
            print(f"[ACTION] Rattrapage caméra : {ecart:.0f} mm, {ecart_theta:+.1f}° de la cible")
            if not esp.goto(x, y, theta, manual=manual):
                return

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

    # --- Actions de jeu ----------------------------------------------------------------
    # Actions de 2025 (Kapla, thermomètre) vidées : les noms restent (blocs Blockly,
    # stratégies existantes), le contenu est à redéfinir pour 2027.

    def _a_definir(self, nom):
        self._check_abort()
        print(f"[ACTION] {nom} : action à définir (2027)")

    def approcheKapla(self) -> bool:
        """Approche visuelle d'un élément de jeu. Retourne True si l'alignement a réussi."""
        self._a_definir("approcheKapla")
        return False

    def thermometre(self):
        self._a_definir("thermometre")

    def attendre(self, secondes: float):
        """Attend un nombre de secondes (interruptible par abort)."""
        self._check_abort()
        print(f"[ACTION] Attente de {secondes}s...")
        fin = time.time() + secondes
        while time.time() < fin:
            self._check_abort()
            time.sleep(0.05)

    def recalage_camera(self, attente_max=1.0):
        """
        Recalage franc sur la caméra zénithale, robot immobile (médiane de plusieurs images).
        En plus de la fusion continue (vision_odom.fusion), utile après un choc ou au départ.
        Retourne True si la pose a été corrigée.
        """
        self._check_abort()
        if not esp:
            print("[SIMU] Recalage caméra virtuel (Pas de com)")
            return False

        cfg = shared.cfg.get("vision_odom", {})
        latence = cfg.get("latence_s", 0.3)
        nb_mesures = cfg.get("nb_mesures", 5)

        # 1. Uniquement des mesures reçues `latence` après le dernier mouvement :
        #    les images ont alors été prises robot immobile
        fin = time.time() + attente_max
        while True:
            t_min = esp.last_motion_time + latence
            mesures = [m for m in shared.vision_poses if m[0] >= t_min]
            if len(mesures) >= nb_mesures:
                break
            if time.time() >= fin:
                print(f"[VISION] Recalage annulé : {len(mesures)}/{nb_mesures} mesures caméra robot immobile")
                return False
            self._check_abort()
            time.sleep(0.05)
        mesures = mesures[-nb_mesures:]

        # 2. Médiane, puis on ne garde que les mesures proches : il en faut une majorité
        milieu = len(mesures) // 2
        x_med = sorted(m[1] for m in mesures)[milieu]
        y_med = sorted(m[2] for m in mesures)[milieu]
        dispersion_max = cfg.get("dispersion_max_mm", 30)
        coherentes = [m for m in mesures if math.hypot(m[1] - x_med, m[2] - y_med) <= dispersion_max]
        if len(coherentes) <= len(mesures) // 2:
            print(f"[VISION] Recalage annulé : mesures trop dispersées "
                  f"({len(coherentes)}/{len(mesures)} à moins de {dispersion_max} mm de la médiane)")
            return False
        milieu = len(coherentes) // 2
        x_cam = sorted(m[1] for m in coherentes)[milieu]
        y_cam = sorted(m[2] for m in coherentes)[milieu]
        theta_ref = coherentes[0][3]
        theta_cam = theta_ref + sorted(_angle_diff(m[3], theta_ref) for m in coherentes)[milieu]

        # 3. Repère caméra -> repère odométrie (identité par défaut)
        repere = cfg.get("repere", {})
        x_cam, y_cam, theta_cam = frames.apply_camera_repere(x_cam, y_cam, theta_cam, repere)

        # 4. Application via la fusion (gain forcé, robot immobile) : garde-fou écart_max_mm /
        #    ecart_max_deg ; l'ESP garde son repère, plus de « S » arrondi au degré
        avant = shared.loc.pose()
        res = shared.loc.on_camera(time.time(), x_cam, y_cam, theta_cam, gain=cfg.get("gain", 1.0))
        if not res["ok"]:
            print(f"[VISION] Recalage refusé : {res['raison']}")
            return False
        shared.refresh_robot_pos()
        apres = shared.loc.pose()
        print(f"[VISION] Recalage : ({avant[0]:.0f}, {avant[1]:.0f}, {avant[2]:.1f}°) -> "
              f"({apres[0]:.0f}, {apres[1]:.0f}, {apres[2]:.1f}°) "
              f"[écart {res['ecart_mm']:.0f} mm, {res['ecart_deg']:+.1f}°]")
        return True

    def prendreKapla(self):
        self._a_definir("prendreKapla")

    def poseKapla(self):
        self._a_definir("poseKapla")

    def pousse_kapla(self):
        self._a_definir("pousse_kapla")

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