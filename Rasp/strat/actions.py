"""Actions de haut niveau appelées par les stratégies (et les blocs Blockly) : déplacements avec
symétrie d'équipe, recalage caméra, actions de jeu. Le matériel vient de hardware.py
(None en simulation : chaque action le tolère)."""
import json
import math
import os
import time

import hardware
import ihm.shared as shared
from core import decision, frames, planif, temps_match

_angle_diff = frames.angle_diff_deg

# Durées des GoTo réels (distance, rotation, durée) : modèle de temps appris (core/temps_match.py)
# (ROBOT_TELEMETRY_DIR : dossier des journaux du simulateur / des tests, pour ne pas mélanger)
DUREES_PATH = os.path.join(os.environ.get("ROBOT_TELEMETRY_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"), "durees_goto.jsonl")
DUREES_MAX = 400


class RetourFin(Exception):
    """Plus assez de temps : la stratégie s'arrête, le robot rentre (strat/main_strat.py)."""


class RobotActions:
    def __init__(self):
        self.base_pos = None  # première pose set_pos (côté BLEUE), pour GoBase
        self.retour = None    # (x, y, theta) réels, marge_s : retour de fin de match (retour_fin)
        self.en_retour = False
        self.approche_reussie = False
        self._plan_local = None
        self._durees = self._charger_durees()
        self.modele_temps = temps_match.ajuster(self._durees)

    @property
    def is_yellow(self):
        return shared.state["team"] == "JAUNE"

    def _check_abort(self, manual=False):
        """Interrompt la stratégie (exception) si le match est arrêté."""
        if not manual and not shared.state["match_running"]:
            raise Exception("Stop")

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
        if hardware.esp:
            hardware.esp.set_pos(real_x, real_y, real_theta)
        else:
            shared.set_known_pose(real_x, real_y, real_theta)
            print("[SIMU] SET_POS virtuel (Pas de com)")


    def goto(self, x, y, theta, manual=False, real=False, retry=True, rattrapage=True):
        """Déplacement en ligne droite (rotation, avance, rotation) : un GoTo de l'ESP.

        retry : relance tant que l'ESP l'annule (obstacle) ; sinon renvoie False au premier refus.
        Pendant un match, vérifie d'abord qu'il reste le temps de rentrer (retour_fin)."""
        self._check_abort(manual=manual)
        if not manual:
            self._verifier_temps()

        vision_cfg = shared.cfg.get("vision_odom", {})
        if not manual and vision_cfg.get("auto", False):
            self.recalage_camera(attente_max=vision_cfg.get("attente_auto_s", 0.5))

        if not real:
            real_x, real_y, real_theta = self._apply_sym(x, y, theta)
        else:
            real_x, real_y, real_theta = x, y, theta

        if not hardware.esp:
            print("[SIMU] GOTO virtuel (Pas de com)")
            return True
        shared.evenement("goto", x=round(real_x), y=round(real_y), theta=round(real_theta, 1))
        depart, t0 = shared.loc.pose(), time.time()
        success = hardware.esp.goto(real_x, real_y, real_theta, manual=manual)
        while not success and retry:
            if manual and shared.state.get("fsm_state") == "STOPPED":
                break
            if not manual and not shared.state.get("match_running", False):
                break
            print(f"[ACTION] 🔄 GOTO annulé par l'ESP (Obstacle), recalcul et relance vers ({real_x}, {real_y}, {real_theta}°)")
            self._check_abort(manual=manual)
            time.sleep(0.5)
            depart, t0 = shared.loc.pose(), time.time()
            success = hardware.esp.goto(real_x, real_y, real_theta, manual=manual)
        if success:
            self._noter_duree(depart, (real_x, real_y, real_theta), time.time() - t0)
            if rattrapage:
                self._rattrapage(real_x, real_y, real_theta, manual)
        else:
            shared.evenement("goto_annule", x=round(real_x), y=round(real_y))
        return success

    # --- Temps de match ----------------------------------------------------------------------
    def _charger_durees(self):
        try:
            with open(DUREES_PATH, encoding="utf-8") as f:
                return [tuple(json.loads(l)) for l in f.readlines()[-DUREES_MAX:] if l.strip()]
        except (OSError, ValueError):
            return []

    def _noter_duree(self, depart, cible, duree):
        """GoTo réussi : (distance, rotation, durée) pour le modèle de temps (sans les GoTo bloqués)."""
        if depart is None or duree <= 0 or duree > 20:
            return
        d, r = temps_match.rotations_goto(depart, cible)
        if d < 5 and r < 2:
            return
        e = (round(d, 1), round(r, 1), round(duree, 3))
        self._durees.append(e)
        del self._durees[:-DUREES_MAX]
        self.modele_temps = temps_match.ajuster(self._durees)
        try:
            os.makedirs(os.path.dirname(DUREES_PATH), exist_ok=True)
            with open(DUREES_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(e) + "\n")
        except OSError:
            pass

    def temps_restant(self):
        """Secondes avant la fin du match (100 s si pas de match)."""
        return temps_match.temps_restant(shared.state.get("start_time"), time.time())

    def duree_retour(self):
        """Durée estimée du retour (ligne droite x 1,25 pour les détours), 0 sans retour déclaré."""
        if self.retour is None:
            return 0.0
        pose = shared.loc.pose() or (shared.robot_pos["x"], shared.robot_pos["y"], shared.robot_pos["theta"])
        (x, y, theta), _ = self.retour
        d, r = temps_match.rotations_goto(pose, (x, y, theta))
        return temps_match.duree_goto(d * 1.25, r, self.modele_temps)

    def retour_fin(self, x, y, theta, marge_s=3.0):
        """Déclare la pose de fin de match (côté BLEUE) : le robot y rentrera à temps, quoi qu'il arrive."""
        self.retour = (self._apply_sym(x, y, theta), float(marge_s))
        print(f"[ACTION] Retour de fin de match : {self.retour[0]} (marge {marge_s} s)")

    def si_temps(self, secondes):
        """True s'il reste le temps de faire une action de `secondes` s ET de rentrer ensuite."""
        marge = self.retour[1] if self.retour else 0.0
        ok = temps_match.assez_de_temps(self.temps_restant(), float(secondes), self.duree_retour(), marge)
        if not ok:
            print(f"[ACTION] Pas le temps ({self.temps_restant():.1f} s restantes) : action de {secondes} s sautée")
            shared.evenement("action_sautee", duree=secondes, restant=round(self.temps_restant(), 1))
        return ok

    def _verifier_temps(self):
        if self.retour is None or self.en_retour or not shared.state.get("match_running"):
            return
        if temps_match.doit_rentrer(self.temps_restant(), self.duree_retour(), self.retour[1]):
            raise RetourFin()

    def executer_retour(self):
        """Rentre à la pose de retour_fin (évitement compris), sans plus regarder l'heure."""
        if self.retour is None:
            return
        (x, y, theta), _ = self.retour
        self.en_retour = True
        print(f"[ACTION] ⏱ Retour de fin de match vers ({x:.0f}, {y:.0f}) ({self.temps_restant():.1f} s restantes)")
        shared.evenement("retour", x=round(x), y=round(y), restant=round(self.temps_restant(), 1))
        try:
            self.aller(x, y, theta, real=True)
        finally:
            self.en_retour = False

    # --- Déplacement avec évitement (planificateur) --------------------------------------------
    # Le plan vient de la base (Base/Planif : caméra zénithale, adversaires prédits, pierres, LiDAR ;
    # 10 Hz) ; si la base se tait plus de PLAN_BASE_MAX_S, le robot replanifie lui-même avec le même
    # code (core/navigation.py). Exécution (config planif.execution) :
    #   "suivi" : suivi de trajectoire continu (core/suivi.py, consignes V à 20 Hz), puis GoTo final ;
    #   "goto"  : un GoTo par segment, replanifié à chaque point de passage.
    PLAN_BASE_MAX_S = 0.4
    PERIODE_SUIVI_S = 0.05
    PERIODE_PLAN_LOCAL_S = 0.25

    def _pose_extrapolee(self, v, w):
        """Pose fusionnée avancée de l'âge de la dernière trame odométrie (10 Hz) à la vitesse commandée."""
        pose = shared.loc.pose() or (shared.robot_pos["x"], shared.robot_pos["y"], shared.robot_pos["theta"])
        t_odo = getattr(hardware.esp, "last_odom_time", None) if hardware.esp else None
        dt = min(0.15, max(0.0, time.time() - t_odo)) if t_odo else 0.0
        x, y, th = pose
        th2 = th + w * dt
        return (x + v * dt * math.cos(math.radians((th + th2) / 2)),
                y + v * dt * math.sin(math.radians((th + th2) / 2)), th2)

    def _marge_adversaire(self, pose, now):
        """Distance (mm) entre le robot et la zone d'un adversaire, maintenant et dans 0,5 s (le suivi
        ralentit en dessous de quelques centimètres). Pistes de Kalman du navigateur embarqué."""
        c = {**planif.DEFAUTS, **shared.cfg.get("planif", {})}
        r = c["rayon_adversaire_mm"] + c["rayon_robot_mm"]
        best = math.inf
        for p in shared.navigateur.suivi.actives(now):
            for dt in (0.0, 0.5):
                px, py, _ = p.position(now + dt)
                best = min(best, math.hypot(px - pose[0], py - pose[1]) - r)
        return best

    def _publier_plan(self, plan, cible, source):
        shared.plan_courant = {"points": [[round(x), round(y)] for x, y in plan.points], "cible": list(cible),
                               "source": source}
        if source == "robot" and shared.zmq_client_instance:
            shared.zmq_client_instance.send_event("plan", {**shared.plan_courant, "ok": True})
        shared.evenement("plan", points=shared.plan_courant["points"], source=source)

    def _plan(self, nav_id, pose, now):
        """(points, marge adversaire mm, source) du plan à suivre maintenant, ou None si pas de chemin."""
        recu = shared.plan_base
        if recu and recu[1].get("id") == nav_id and now - recu[0] <= self.PLAN_BASE_MAX_S:
            m = recu[1]
            if not m.get("ok"):
                return None
            marge = m.get("marge_adversaire_mm")
            return [tuple(p) for p in m["points"]], (math.inf if marge is None else marge), "base"
        # secours : planificateur embarqué, recalculé à PERIODE_PLAN_LOCAL_S
        if now - getattr(self, "_t_plan_local", 0.0) >= self.PERIODE_PLAN_LOCAL_S or self._plan_local is None:
            self._t_plan_local = now
            nav = shared.navigateur
            nav.cfg = shared.cfg.get("planif", {})
            nav.observer_pose(*pose, now)
            plan, _ = nav.planifier(now, pose)
            self._plan_local = plan
        p = self._plan_local
        return ([tuple(q) for q in p.points], p.marge_adversaire_mm, "robot") if p is not None else None

    def aller(self, x, y, theta, real=False, manual=False, timeout_s=10.0, ignorer_pres_cible_mm=None):
        """Va à (x, y, theta) en contournant obstacles, pierres et adversaires (prédits), en
        replanifiant en continu. ignorer_pres_cible_mm : pierres / points LiDAR ignorés près de la cible
        (on va prendre la pierre). Renvoie True une fois arrivé, False si aucun chemin pendant timeout_s."""
        self._check_abort(manual=manual)
        if not manual:
            self._verifier_temps()
        cx, cy, ctheta = (x, y, theta) if real else self._apply_sym(x, y, theta)
        if not hardware.esp:
            print(f"[SIMU] ALLER virtuel vers ({cx}, {cy}, {ctheta})")
            return True
        cfg = dict(shared.cfg.get("planif", {}))
        if ignorer_pres_cible_mm is not None:
            cfg["ignorer_pres_cible_mm"] = ignorer_pres_cible_mm
        self._nav_id = getattr(self, "_nav_id", 0) + 1
        nav_id, cible = self._nav_id, (cx, cy, ctheta)
        pose = shared.loc.pose() or (shared.robot_pos["x"], shared.robot_pos["y"], shared.robot_pos["theta"])
        shared.navigateur.cfg = shared.cfg.get("planif", {})
        shared.navigateur.demander(nav_id, cible, cfg)
        self._plan_local = None
        if shared.zmq_client_instance:
            shared.zmq_client_instance.send_event("nav_demande", {"id": nav_id, "cible": list(cible), "cfg": cfg,
                                                                  "pose": list(pose)})
        shared.evenement("nav", x=round(cx), y=round(cy), theta=round(ctheta, 1))
        try:
            if cfg.get("execution", "suivi") == "goto":
                return self._aller_goto(nav_id, cible, manual, timeout_s)
            return self._aller_suivi(nav_id, cible, manual, timeout_s, cfg)
        finally:
            shared.navigateur.terminer(nav_id)
            if shared.zmq_client_instance:
                shared.zmq_client_instance.send_event("nav_fin", {"id": nav_id})

    def _aller_suivi(self, nav_id, cible, manual, timeout_s, cfg):
        from core import suivi as suivi_mod
        cx, cy, ctheta = cible
        reglages = {k: cfg[k] for k in suivi_mod.DEFAUTS if k in cfg}
        suiveur, chemin, source = None, None, None
        v = w = 0.0
        sans_chemin = None
        try:
            while True:
                t_tour = time.time()
                self._check_abort(manual=manual)
                pose = self._pose_extrapolee(v, w)
                res = self._plan(nav_id, pose, t_tour)
                if res is None:
                    v = w = 0.0
                    hardware.esp.set_speed(0, 0)
                    sans_chemin = sans_chemin or t_tour
                    if t_tour - sans_chemin > timeout_s:
                        print(f"[ACTION] Aucun chemin vers ({cx:.0f}, {cy:.0f}) depuis {timeout_s:.0f} s : abandon")
                        shared.evenement("aller_echec", x=round(cx), y=round(cy))
                        return False
                    time.sleep(self.PERIODE_SUIVI_S)
                    continue
                sans_chemin = None
                points, _, src = res
                if points != chemin:
                    if suiveur is None:
                        suiveur = suivi_mod.Suivi(points, reglages)
                    else:
                        suiveur.changer_chemin(points)
                    if source != src:
                        print(f"[ACTION] Plan fourni par : {src}")
                    chemin, source = points, src
                    self._publier_plan(planif.Plan(points, 0.0, 0.0), cible, src)
                obstacle = math.inf
                if time.time() - shared.lidar_points_t < 0.5:
                    obstacle = suivi_mod.obstacle_devant(shared.lidar_points, pose)
                cmd = suiveur.commande(pose, self.PERIODE_SUIVI_S, obstacle, self._marge_adversaire(pose, t_tour))
                if cmd.etat == "arrive":
                    break
                v, w = cmd.v, cmd.w
                hardware.esp.set_speed(v, w)
                time.sleep(max(0.0, self.PERIODE_SUIVI_S - (time.time() - t_tour)))
        finally:
            hardware.esp.set_speed(0, 0)
        # Fin : GoTo de l'ESP pour la position et le cap exacts (il gère sa propre précision)
        return self.goto(cx, cy, ctheta, manual=manual, real=True, retry=True, rattrapage=True)

    def _aller_goto(self, nav_id, cible, manual, timeout_s):
        cx, cy, ctheta = cible
        sans_chemin = None
        while True:
            self._check_abort(manual=manual)
            now = time.time()
            pose = shared.loc.pose()
            if pose is None:
                return self.goto(cx, cy, ctheta, manual=manual, real=True)
            if math.hypot(cx - pose[0], cy - pose[1]) < 15 and abs(_angle_diff(ctheta, pose[2])) < 3:
                return True
            self._plan_local = None
            res = self._plan(nav_id, pose, now)
            if res is None:
                sans_chemin = sans_chemin or now
                if now - sans_chemin > timeout_s:
                    print(f"[ACTION] Aucun chemin vers ({cx:.0f}, {cy:.0f}) depuis {timeout_s:.0f} s : abandon")
                    shared.evenement("aller_echec", x=round(cx), y=round(cy))
                    return False
                time.sleep(0.3)   # l'adversaire va peut-être bouger
                continue
            sans_chemin = None
            points, _, src = res
            plan = planif.Plan(points, 0.0, 0.0)
            self._publier_plan(plan, cible, src)
            # Premier segment seulement : on replanifie à chaque point de passage
            px, py = points[1] if len(points) > 1 else (cx, cy)
            dernier = len(points) <= 2
            cap = ctheta if dernier else plan.caps(ctheta)[0]
            if not self.goto(px, py, cap, manual=manual, real=True, retry=False, rattrapage=dernier):
                time.sleep(0.3)   # obstacle : l'ESP s'est arrêté, on replanifie avec le LiDAR
                continue
            if dernier:
                return True

    # --- Stratégie dynamique : l'ordre des objectifs est décidé en match (core/decision.py) ----
    def jouer(self, objectifs, profondeur=2):
        """Enchaîne les objectifs (dicts aux champs de core.decision.Objectif, côté BLEUE) dans l'ordre
        le plus rentable à chaque instant : aller() à la pose d'approche, puis l'action (méthode de
        RobotActions, échec si elle renvoie False). S'arrête quand plus rien n'est faisable dans le
        temps restant (retour de fin compris). Renvoie l'état (objectifs réussis, échecs)."""
        objs = []
        for o in objectifs:
            d = dict(o)
            d["x"], d["y"], d["theta"] = self._apply_sym(d["x"], d["y"], d.get("theta", 0.0))
            d["prerequis"] = tuple(d.get("prerequis", ()))
            objs.append(decision.Objectif(**d))
        etat = decision.Etat()
        while True:
            self._check_abort()
            self._verifier_temps()
            pose = shared.loc.pose() or (shared.robot_pos["x"], shared.robot_pos["y"], shared.robot_pos["theta"])
            retour, marge = (self.retour if self.retour else (None, 0.0))
            adv = [(a[0], a[1]) for a in shared.adversaires_recents(1.0)]
            o, valeur = decision.choisir(objs, etat, pose, self.temps_restant(), retour, marge, adv,
                                         self.modele_temps, profondeur)
            if o is None:
                print(f"[STRAT] Plus d'objectif faisable ({self.temps_restant():.1f} s restantes, "
                      f"réussis : {sorted(etat.reussis)})")
                return etat
            print(f"[STRAT] Objectif {o.nom} ({o.points} pts, valeur {valeur:.2f})")
            shared.evenement("objectif", nom=o.nom, valeur=round(valeur, 2))
            ok = self.aller(o.x, o.y, o.theta, real=True)
            if ok and o.action:
                res = getattr(self, o.action)(**o.args)
                ok = res is not False and not (o.action == "aligner_tag" and res is None)
            if ok:
                etat.reussis.add(o.nom)
            else:
                etat.essais[o.nom] = etat.essais.get(o.nom, 0) + 1
                print(f"[STRAT] Objectif {o.nom} raté ({etat.essais[o.nom]}/{o.max_essais})")
            shared.evenement("objectif_fin", nom=o.nom, ok=ok)

    # --- Caméra embarquée : se placer face à un tag (pierres 2027) ---------------------------
    def aligner_tag(self, ids=(13,), distance_mm=None, essais=3, tolerance_mm=10.0, tolerance_deg=3.0,
                    recul_mm=150.0, manual=False):
        """Se met face au tag le plus proche vu par la caméra embarquée, son point de référence à
        distance_mm de la face (défaut : camera.prise.distance_mm). Mesure à l'arrêt (médiane), petit
        GoTo, puis nouvelle mesure, jusqu'à `essais` fois. Si le décalage latéral est grand, recule
        d'abord (le robot ne se déplace pas de côté) puis revient dans l'axe du tag.
        Renvoie la dernière mesure (PoseTag, repère robot) si aligné, sinon None ; robot.approche_reussie."""
        self.approche_reussie = False
        if distance_mm is None:
            distance_mm = float(shared.cfg.get("camera", {}).get("prise", {}).get("distance_mm", 300.0))
        vision = hardware.vision
        if vision is None:
            print("[VISION] Caméra embarquée absente : alignement impossible")
            return None
        tag = None
        for _ in range(int(essais)):
            self._check_abort(manual=manual)
            tag = vision.mesurer(ids=list(ids), n=5, timeout=1.5)
            if tag is None:
                print(f"[VISION] Tag {list(ids)} non vu")
                shared.evenement("tag_non_vu", ids=list(ids))
                return None
            pose = shared.loc.pose()
            ex, ey, ecap = tag.point_devant(distance_mm)      # cible, repère robot
            ok = (abs(ey) < tolerance_mm and abs(ex) < tolerance_mm and abs(tag.ecart_angle) < tolerance_deg)
            print(f"[VISION] Tag {tag.id} : à {tag.distance:.0f} mm, latéral {tag.y:+.0f} mm, angle {tag.ecart_angle:+.1f}°"
                  f" -> correction ({ex:+.0f}, {ey:+.0f}, {ecap:+.1f}°)")
            shared.evenement("tag", id=tag.id, x=round(tag.x), y=round(tag.y), angle=round(tag.ecart_angle, 1))
            if ok or pose is None:
                break
            tx, ty, tcap = tag.vers_table(*pose)
            fx = tx + distance_mm * math.cos(math.radians(tcap))
            fy = ty + distance_mm * math.sin(math.radians(tcap))
            fcap = frames.normalize_deg(tcap + 180.0)
            if abs(ey) > 3 * tolerance_mm:
                rx = tx + (distance_mm + recul_mm) * math.cos(math.radians(tcap))
                ry = ty + (distance_mm + recul_mm) * math.sin(math.radians(tcap))
                self.goto(rx, ry, fcap, manual=manual, real=True, rattrapage=False)
            self.goto(fx, fy, fcap, manual=manual, real=True, rattrapage=False)
        else:
            tag = vision.mesurer(ids=list(ids), n=5, timeout=1.5)
        if tag is not None:
            ex, ey, _ = tag.point_devant(distance_mm)
            self.approche_reussie = abs(ey) < 2 * tolerance_mm and abs(tag.ecart_angle) < 2 * tolerance_deg
        return tag if self.approche_reussie else None

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
            if not hardware.esp.goto(x, y, theta, manual=manual):
                return

    def set_speed(self, vx, vtheta):
        """Consigne de vitesse pour contrôle joystick."""
        if hardware.esp:
            hardware.esp.set_speed(vx, vtheta)
        else:
            print(f"[SIMU] SET_SPEED ({vx}, {vtheta}) virtuel")

    def stop(self):
        print("[ACTION] STOP")
        if hardware.esp:
            hardware.esp.stop_robot()
        else:
            print("[SIMU] STOP virtuel (Pas de com)")

    def set_lidar_state(self, val):
        """Définit l'état du LiDAR sur l'ESP32 (0: Libre, 1: Stop, 2: Front, 3: Back)"""
        if hardware.esp:
            hardware.esp.set_lidar_state(val)
        else:
            print(f"[SIMU] SET LIDAR STATE {val} virtuel")

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

    def recalage_camera(self, attente_max=1.0, manual=False):
        """
        Recalage franc sur la caméra zénithale, robot immobile (médiane de plusieurs images).
        En plus de la fusion continue (vision_odom.fusion), utile après un choc ou au départ.
        Retourne True si la pose a été corrigée.
        """
        self._check_abort(manual=manual)
        if not hardware.esp:
            print("[SIMU] Recalage caméra virtuel (Pas de com)")
            return False

        cfg = shared.cfg.get("vision_odom", {})
        latence = cfg.get("latence_s", 0.3)
        nb_mesures = cfg.get("nb_mesures", 5)

        # 1. Uniquement des mesures reçues `latence` après le dernier mouvement :
        #    les images ont alors été prises robot immobile
        fin = time.time() + attente_max
        while True:
            t_min = hardware.esp.last_motion_time + latence
            mesures = [m for m in shared.vision_poses if m[0] >= t_min]
            if len(mesures) >= nb_mesures:
                break
            if time.time() >= fin:
                print(f"[VISION] Recalage annulé : {len(mesures)}/{nb_mesures} mesures caméra robot immobile")
                return False
            self._check_abort(manual=manual)
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
        if hardware.actionneurs:
            if command_string is not None:
                hardware.actionneurs.send_raw(command_string)
            else:
                hardware.actionneurs.send_cmd(act1, act2, act3, act4)
        else:
            print("[SIMU] Pas d'interface Actionneur connectée (Mode sans matériel).")