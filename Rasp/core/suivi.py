"""Suivi de trajectoire (pur Python, testé) : « regulated pure pursuit » pour robot différentiel.

À chaque pas (20 Hz), à partir de la pose et du chemin (points de passage) :
  1. avancement : point du chemin le plus proche, sans jamais revenir en arrière ;
  2. point visé à `anticipation` devant sur le chemin (grandit avec la vitesse) ;
  3. s'il est trop sur le côté / derrière (> angle_rotation_deg) : rotation sur place ;
     sinon arc de cercle vers lui : courbure k = 2 sin(alpha) / L, omega = v k ;
  4. vitesse régulée : plafond en virage (accélération latérale), freinage pour s'arrêter au bout
     (sqrt(2 a d)), ralentissement près d'un obstacle (points LiDAR devant) ou d'un adversaire
     prédit trop proche (marge du plan), rampe d'accélération ;
  5. arrivé à moins de `tolerance_mm` du bout : vitesse nulle, le GoTo final (précis) prend le relais.
Les consignes partent à l'ESP en « V vx omega » ; l'ESP garde son évitement LiDAR (L) et s'arrête
seul sans consigne pendant 500 ms.
"""

import math
from dataclasses import dataclass

DEFAUTS = {
    "v_max_mm_s": 700.0,
    "a_max_mm_s2": 600.0,          # rampe de vitesse (l'ESP limite à 1400 mm/s² par roue)
    "a_lat_max_mm_s2": 500.0,      # virages : v <= sqrt(a_lat / |k|)
    "w_max_deg_s": 180.0,
    "anticipation_min_mm": 150.0,
    "anticipation_max_mm": 450.0,
    "anticipation_s": 0.6,         # anticipation = v x anticipation_s, bornée
    "angle_rotation_deg": 50.0,    # au-delà : rotation sur place d'abord
    "gain_rotation": 3.0,          # omega = gain x erreur (deg/s par degré), borné
    "tolerance_mm": 30.0,
    "distance_securite_mm": 600.0, # obstacle LiDAR devant (depuis le point de référence ; l'avant du
    "distance_arret_mm": 350.0,    #  robot est à 245 mm) : vitesse réduite, nulle à distance_arret (= seuil ESP)
    "adv_securite_mm": 150.0,      # marge à la zone de l'adversaire : pleine vitesse au-delà,
    "adv_arret_mm": -30.0,         #  25 % de la vitesse à 0, arrêt si on est dedans de plus de 30 mm
    "v_min_mm_s": 60.0,            # en dessous, l'ESP / les pas à pas avancent mal
}


@dataclass
class Commande:
    v: float           # mm/s
    w: float           # deg/s
    etat: str          # "rotation" | "suivi" | "arrive"
    avancement: int    # index du segment courant
    reste_mm: float


def _norm(a):
    return (a + 180.0) % 360.0 - 180.0


class Suivi:
    def __init__(self, chemin, cfg=None):
        self.cfg = {**DEFAUTS, **(cfg or {})}
        self.chemin = [tuple(p) for p in chemin]
        self.seg = 0
        self.v = 0.0
        self._longueurs = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(self.chemin, self.chemin[1:])]

    def changer_chemin(self, chemin):
        """Nouveau chemin (replanification) : on garde la vitesse courante, l'avancement repart."""
        self.chemin = [tuple(p) for p in chemin]
        self.seg = 0
        self._longueurs = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(self.chemin, self.chemin[1:])]

    def _projeter(self, x, y):
        """(segment, fraction, distance) du point du chemin le plus proche, à partir de self.seg."""
        best = (self.seg, 0.0, math.inf)
        for k in range(self.seg, len(self.chemin) - 1):
            (ax, ay), (bx, by) = self.chemin[k], self.chemin[k + 1]
            dx, dy = bx - ax, by - ay
            l2 = dx * dx + dy * dy or 1.0
            f = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
            d = math.hypot(x - ax - f * dx, y - ay - f * dy)
            if d < best[2] - 1e-9:
                best = (k, f, d)
        return best

    def _point_a(self, seg, f, dist):
        """Point à `dist` mm plus loin sur le chemin depuis (seg, f) ; le bout s'il est plus près."""
        reste = (1.0 - f) * self._longueurs[seg]
        if dist <= reste:
            (ax, ay), (bx, by) = self.chemin[seg], self.chemin[seg + 1]
            g = f + dist / (self._longueurs[seg] or 1.0)
            return ax + (bx - ax) * g, ay + (by - ay) * g
        dist -= reste
        for k in range(seg + 1, len(self.chemin) - 1):
            if dist <= self._longueurs[k]:
                (ax, ay), (bx, by) = self.chemin[k], self.chemin[k + 1]
                g = dist / (self._longueurs[k] or 1.0)
                return ax + (bx - ax) * g, ay + (by - ay) * g
            dist -= self._longueurs[k]
        return self.chemin[-1]

    def commande(self, pose, dt, obstacle_devant_mm=math.inf, marge_adversaire_mm=math.inf):
        c = self.cfg
        x, y, th = pose
        if len(self.chemin) < 2:
            self.v = 0.0
            return Commande(0.0, 0.0, "arrive", 0, 0.0)
        seg, f, _ = self._projeter(x, y)
        self.seg = seg
        reste = (1.0 - f) * self._longueurs[seg] + sum(self._longueurs[seg + 1:])
        fin = self.chemin[-1]
        d_fin = math.hypot(fin[0] - x, fin[1] - y)
        if d_fin < c["tolerance_mm"] or (reste < c["tolerance_mm"] and seg == len(self.chemin) - 2):
            self.v = 0.0
            return Commande(0.0, 0.0, "arrive", seg, 0.0)

        L = min(c["anticipation_max_mm"], max(c["anticipation_min_mm"], abs(self.v) * c["anticipation_s"]))
        L = min(L, max(reste, 1.0))
        cx, cy = self._point_a(seg, f, L)
        if reste <= L + 1.0:
            cx, cy = fin
        alpha = _norm(math.degrees(math.atan2(cy - y, cx - x)) - th)
        L_reel = max(math.hypot(cx - x, cy - y), 1.0)

        w_max = c["w_max_deg_s"]
        if abs(alpha) > c["angle_rotation_deg"]:
            # trop de côté : on s'arrête (rampe) et on tourne sur place
            self.v = max(0.0, self.v - c["a_max_mm_s2"] * dt)
            w = max(-w_max, min(w_max, c["gain_rotation"] * alpha))
            return Commande(self.v, w if self.v == 0.0 else 0.0, "rotation", seg, reste)

        kappa = 2.0 * math.sin(math.radians(alpha)) / L_reel          # 1/mm
        v_cible = c["v_max_mm_s"]
        if abs(kappa) > 1e-9:
            v_cible = min(v_cible, math.sqrt(c["a_lat_max_mm_s2"] / abs(kappa)))
        v_cible = min(v_cible, math.sqrt(2.0 * c["a_max_mm_s2"] * max(0.0, reste - c["tolerance_mm"] * 0.5)))
        d = obstacle_devant_mm
        if d < c["distance_securite_mm"]:
            f_obs = (d - c["distance_arret_mm"]) / (c["distance_securite_mm"] - c["distance_arret_mm"])
            v_cible = min(v_cible, c["v_max_mm_s"] * max(0.0, f_obs))
        m = marge_adversaire_mm
        if m < c["adv_securite_mm"]:
            if m <= c["adv_arret_mm"]:
                v_cible = 0.0
            else:
                f_adv = max(0.0, m) / c["adv_securite_mm"]
                v_cible = min(v_cible, c["v_max_mm_s"] * (0.25 + 0.75 * f_adv))
        if 0.0 < v_cible < c["v_min_mm_s"] and reste > c["tolerance_mm"] and obstacle_devant_mm > c["distance_arret_mm"]:
            v_cible = c["v_min_mm_s"]
        # rampe
        if v_cible > self.v:
            self.v = min(v_cible, self.v + c["a_max_mm_s2"] * dt)
        else:
            self.v = max(v_cible, self.v - 2.0 * c["a_max_mm_s2"] * dt)   # freinage plus franc
        w = math.degrees(self.v * kappa)
        if abs(w) > w_max:
            # rotation saturée : on réduit la vitesse pour garder la courbure
            self.v *= w_max / abs(w)
            w = math.copysign(w_max, w)
        return Commande(self.v, w, "suivi", seg, reste)


def obstacle_devant(points, pose, demi_largeur_mm=200.0, portee_mm=800.0):
    """Distance (mm, depuis le point de référence) du point LiDAR le plus proche dans le couloir
    devant le robot (largeur 2 x demi_largeur), inf s'il n'y en a pas. points : repère table."""
    x, y, th = pose
    c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
    best = math.inf
    for px, py in points:
        u = (px - x) * c + (py - y) * s
        v = -(px - x) * s + (py - y) * c
        if 0.0 < u < portee_mm and abs(v) < demi_largeur_mm:
            best = min(best, u)
    return best
