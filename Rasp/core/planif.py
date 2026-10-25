"""Planification de trajectoire sur la table (pur Python, testé) : carte de coûts, A*, lissage.

CARTE (repère table, cellules carrées de `res_mm`, cellule (i, j) : i le long de X, j le long de Y)
  Chaque cellule a un coût >= 1 (1 = libre) ou INF (interdite). On planifie pour le point de
  référence du robot : les obstacles sont gonflés du demi-encombrement latéral du robot
  (`rayon_robot_mm`), donc une cellule libre = le robot peut y passer sans toucher.
  Autour de la zone interdite, un surcoût qui décroît sur `marge_douce_mm` : le chemin garde ses
  distances quand il peut, mais passe quand même entre deux obstacles si c'est la seule voie.
  Sources : bords de la table, obstacles fixes (config planif.obstacles), robot(s) adverse(s)
  (caméra zénithale) avec leur position prédite, points LiDAR, heat map de l'adversaire
  (`Chaleur` : là où il est passé récemment, décroît avec le temps).

CHEMIN
  A* 8-voisins (pas de coupe de coin entre deux cellules interdites), heuristique octile ; puis
  lissage « string pulling » : on relie directement deux points du chemin quand le segment ne
  traverse que des cellules autorisées et pas plus chères que celles du chemin A* entre eux.
  Résultat : quelques points de passage, chacun = un GoTo de l'ESP (rotation puis ligne droite).
  Départ dans une zone interdite (robot collé à un obstacle) : on sort par la cellule libre la plus
  proche. Arrivée interdite : cellule libre la plus proche à moins de `tolerance_arrivee_mm`, sinon
  pas de chemin.
"""

import heapq
import json
import math
from dataclasses import dataclass, field

from core import frames

INF = float("inf")
SQRT2 = math.sqrt(2.0)

DEFAUTS = {
    "res_mm": 30.0,
    "rayon_robot_mm": 215.0,        # demi-largeur 188 mm + marge
    "marge_douce_mm": 250.0,
    "poids_doux": 3.0,              # surcoût max juste au bord de la zone interdite
    "rayon_adversaire_mm": 200.0,   # encombrement supposé du robot adverse (centre de son tag)
    "marge_adversaire_mm": 450.0,   # zone de surcoût autour de lui (plus large : il bouge)
    "poids_adversaire": 6.0,
    "prediction_s": 0.8,            # position prédite de l'adversaire (vitesse estimée) gonflée aussi
    "rayon_point_lidar_mm": 40.0,
    "poids_chaleur": 2.0,
    "tolerance_arrivee_mm": 120.0,
    "obstacles": [],                # [{"rect": [x0, y0, x1, y1]} | {"cercle": [x, y, r]}], repère table
    # Planification dans le temps (planifier_temps) : adversaires prédits (core/suivi_adversaire.py)
    "v_nominale_mm_s": 700.0,       # vitesse de croisière du suivi de trajectoire
    "w_nominale_deg_s": 180.0,      # vitesse de rotation (coût des virages)
    "horizon_s": 4.0,               # au-delà : adversaire figé à sa position prédite, sans surcoût
    "k_sigma": 0.5,                 # zone interdite autour de la position prédite = rayon + k_sigma x
    "sigma_dur_max_mm": 100.0,      #  incertitude, plafonnée : le reste de l'incertitude = surcoût
    "tampon_mm": 50.0,              # en plus pour CRÉER un chemin ; pour GARDER le chemin courant, sans
                                    # tampon : pas d'hésitation pour quelques millimètres
    "poids_dynamique": 8.0,
    "dimensions_pierre_mm": [320.0, 110.0],
    "ignorer_pres_cible_mm": 0.0,   # pierres / points LiDAR ignorés près de la cible (on va les prendre)
}


class Carte:
    def __init__(self, cfg=None):
        c = {**DEFAUTS, **(cfg or {})}
        self.cfg = c
        self.res = float(c["res_mm"])
        self.nx = int(math.ceil((frames.TABLE_X_MAX - frames.TABLE_X_MIN) / self.res))
        self.ny = int(math.ceil((frames.TABLE_Y_MAX - frames.TABLE_Y_MIN) / self.res))
        self.r = float(c["rayon_robot_mm"])
        self.cout = [1.0] * (self.nx * self.ny)
        self._bords()
        for o in c.get("obstacles") or []:
            if "rect" in o:
                self.ajouter_rect(*o["rect"])
            elif "cercle" in o:
                self.ajouter_disque(*o["cercle"])

    def copie(self):
        """Copie indépendante (la carte fixe est calculée une fois, puis copiée à chaque replanification)."""
        c = Carte.__new__(Carte)
        c.cfg, c.res, c.nx, c.ny, c.r = self.cfg, self.res, self.nx, self.ny, self.r
        c.cout = list(self.cout)
        return c

    # --- coordonnées ---------------------------------------------------------------------
    def cellule(self, x, y):
        i = int((x - frames.TABLE_X_MIN) / self.res)
        j = int((y - frames.TABLE_Y_MIN) / self.res)
        return min(max(i, 0), self.nx - 1), min(max(j, 0), self.ny - 1)

    def centre(self, i, j):
        return frames.TABLE_X_MIN + (i + 0.5) * self.res, frames.TABLE_Y_MIN + (j + 0.5) * self.res

    def cout_xy(self, x, y):
        if not frames.in_table(x, y):
            return INF
        i, j = self.cellule(x, y)
        return self.cout[i * self.ny + j]

    def libre(self, x, y):
        return self.cout_xy(x, y) < INF

    # --- obstacles -------------------------------------------------------------------------
    def _appliquer(self, dist, x0, y0, x1, y1, r_obstacle, marge, poids):
        """dist(x, y) = distance à l'obstacle ; interdit à moins de r_obstacle + r, surcoût ensuite."""
        dur = r_obstacle + self.r
        portee = dur + marge
        i0, j0 = self.cellule(x0 - portee, y0 - portee)
        i1, j1 = self.cellule(x1 + portee, y1 + portee)
        ny, cout, res = self.ny, self.cout, self.res
        xm, ym = frames.TABLE_X_MIN, frames.TABLE_Y_MIN
        for i in range(i0, i1 + 1):
            cx = xm + (i + 0.5) * res
            base = i * ny
            for j in range(j0, j1 + 1):
                d = dist(cx, ym + (j + 0.5) * res)
                if d < dur:
                    cout[base + j] = INF
                elif d < portee and marge > 0:
                    cout[base + j] += poids * (1.0 - (d - dur) / marge)

    def ajouter_disque(self, x, y, rayon, marge=None, poids=None):
        m = self.cfg["marge_douce_mm"] if marge is None else marge
        p = self.cfg["poids_doux"] if poids is None else poids
        self._appliquer(lambda a, b: math.hypot(a - x, b - y), x, y, x, y, rayon, m, p)

    def ajouter_rect(self, x0, y0, x1, y1, marge=None, poids=None):
        xa, xb, ya, yb = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        m = self.cfg["marge_douce_mm"] if marge is None else marge
        p = self.cfg["poids_doux"] if poids is None else poids

        def dist(a, b):
            return math.hypot(max(xa - a, 0.0, a - xb), max(ya - b, 0.0, b - yb))
        self._appliquer(dist, xa, ya, xb, yb, 0.0, m, p)

    def _bords(self):
        """Interdit à moins de r des bords, petit surcoût juste après."""
        marge = self.cfg["marge_douce_mm"] / 2
        p = self.cfg["poids_doux"] / 2
        for i in range(self.nx):
            for j in range(self.ny):
                x, y = self.centre(i, j)
                d = min(x - frames.TABLE_X_MIN, frames.TABLE_X_MAX - x, y - frames.TABLE_Y_MIN, frames.TABLE_Y_MAX - y)
                if d < self.r:
                    self.cout[i * self.ny + j] = INF
                elif d < self.r + marge:
                    self.cout[i * self.ny + j] += p * (1.0 - (d - self.r) / marge)

    def ajouter_rect_oriente(self, cx, cy, longueur, largeur, angle_deg, marge=None, poids=None):
        """Rectangle centré en (cx, cy), côté `longueur` le long de angle_deg (pierres vues d'en haut)."""
        c, sn = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
        hl, hw = longueur / 2.0, largeur / 2.0
        m = self.cfg["marge_douce_mm"] if marge is None else marge
        p = self.cfg["poids_doux"] if poids is None else poids

        def dist(a, b):
            u = (a - cx) * c + (b - cy) * sn
            v = -(a - cx) * sn + (b - cy) * c
            return math.hypot(max(abs(u) - hl, 0.0), max(abs(v) - hw, 0.0))
        r = math.hypot(hl, hw)
        self._appliquer(dist, cx - r, cy - r, cx + r, cy + r, 0.0, m, p)

    def ajouter_pierres(self, pierres):
        """Pierres vues par la caméra zénithale : [(x, y, theta[, nb])], théta = axe long de la boîte
        (une pile = un obstacle, quelle que soit sa hauteur)."""
        lg, la = self.cfg["dimensions_pierre_mm"]
        for p in pierres:
            self.ajouter_rect_oriente(p[0], p[1], lg, la, p[2])

    def ajouter_adversaire(self, x, y, vx=0.0, vy=0.0):
        c = self.cfg
        self.ajouter_disque(x, y, c["rayon_adversaire_mm"], c["marge_adversaire_mm"], c["poids_adversaire"])
        t = c["prediction_s"]
        if t > 0 and math.hypot(vx, vy) * t > self.res:
            self.ajouter_disque(x + vx * t, y + vy * t, c["rayon_adversaire_mm"] * 0.7,
                                c["marge_adversaire_mm"] / 2, c["poids_adversaire"] / 2)

    def ajouter_points(self, points):
        """Points LiDAR (repère table) : petits obstacles durs."""
        r = self.cfg["rayon_point_lidar_mm"]
        for x, y in points:
            self.ajouter_disque(x, y, r, self.cfg["marge_douce_mm"] / 2, self.cfg["poids_doux"])

    def ajouter_chaleur(self, chaleur, t):
        p = self.cfg["poids_chaleur"]
        if p <= 0:
            return
        acc = {}
        s2 = 2 * chaleur.sigma * chaleur.sigma
        portee = 3 * chaleur.sigma
        for to, xo, yo in chaleur.obs:
            w = math.exp(-(t - to) / chaleur.tau)
            if w < 0.05:
                continue
            i0, j0 = self.cellule(xo - portee, yo - portee)
            i1, j1 = self.cellule(xo + portee, yo + portee)
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    x, y = self.centre(i, j)
                    d2 = (x - xo) ** 2 + (y - yo) ** 2
                    if d2 < portee * portee:
                        k = i * self.ny + j
                        acc[k] = acc.get(k, 0.0) + w * math.exp(-d2 / s2)
        for k, v in acc.items():
            if self.cout[k] < INF:
                self.cout[k] += p * min(v / 3.0, 1.0)

    def resume(self, pas_mm=100.0):
        """Grille grossière (liste de lignes le long de X) de coûts 0..9, 9 = interdit : affichage."""
        k = max(1, int(round(pas_mm / self.res)))
        out = []
        for i0 in range(0, self.nx, k):
            ligne = []
            for j0 in range(0, self.ny, k):
                vals = [self.cout[i * self.ny + j] for i in range(i0, min(i0 + k, self.nx))
                        for j in range(j0, min(j0 + k, self.ny))]
                m = max(vals)
                ligne.append(9 if m == INF else min(8, int(round(m - 1.0))))
            out.append(ligne)
        return out


class Chaleur:
    """Heat map de l'adversaire : chaque observation ajoute une gaussienne qui s'efface avec le temps."""

    def __init__(self, sigma_mm=150.0, demi_vie_s=4.0, max_obs=200):
        self.sigma = sigma_mm
        self.tau = demi_vie_s / math.log(2.0)
        self.obs = []                    # (t, x, y)
        self.max_obs = max_obs

    def observer(self, x, y, t):
        self.obs.append((t, x, y))
        if len(self.obs) > self.max_obs:
            del self.obs[: len(self.obs) - self.max_obs]

    def valeur(self, x, y, t):
        s2 = 2 * self.sigma * self.sigma
        v = 0.0
        for to, xo, yo in self.obs:
            d2 = (x - xo) ** 2 + (y - yo) ** 2
            if d2 < 9 * self.sigma * self.sigma:
                v += math.exp(-d2 / s2 - (t - to) / self.tau)
        return min(v / 3.0, 1.0)       # ~3 observations récentes au même endroit = chaleur max


@dataclass
class Plan:
    points: list                     # [(x, y)] du départ (inclus) à l'arrivée (incluse)
    longueur: float
    cout: float
    arrivee_deplacee: bool = False   # arrivée interdite : on s'arrête au plus près
    cellules: list = field(default_factory=list)

    def caps(self, theta_final):
        """Cap à chaque point de passage (après le départ) : direction du segment suivant, puis final."""
        out = []
        for k in range(1, len(self.points)):
            if k + 1 < len(self.points):
                (xa, ya), (xb, yb) = self.points[k], self.points[k + 1]
                out.append(math.degrees(math.atan2(yb - ya, xb - xa)))
            else:
                out.append(theta_final)
        return out


def _voisins(carte, k):
    ny, nx = carte.ny, carte.nx
    i, j = divmod(k, ny)
    for di, dj, pas in ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                        (1, 1, SQRT2), (1, -1, SQRT2), (-1, 1, SQRT2), (-1, -1, SQRT2)):
        a, b = i + di, j + dj
        if 0 <= a < nx and 0 <= b < ny:
            if di and dj and (carte.cout[(i + di) * ny + j] == INF or carte.cout[i * ny + j + dj] == INF):
                continue
            yield a * ny + b, pas


def _plus_proche_libre(carte, k, rayon_cellules):
    """Cellule libre la plus proche de k (parcours en largeur), ou None."""
    if carte.cout[k] < INF:
        return k
    ny = carte.ny
    i0, j0 = divmod(k, ny)
    vus, file = {k}, [k]
    while file:
        suivant = []
        for c in file:
            i, j = divmod(c, ny)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    a, b = i + di, j + dj
                    n = a * ny + b
                    if not (0 <= a < carte.nx and 0 <= b < ny) or n in vus:
                        continue
                    if max(abs(a - i0), abs(b - j0)) > rayon_cellules:
                        continue
                    if carte.cout[n] < INF:
                        return n
                    vus.add(n)
                    suivant.append(n)
        file = suivant
    return None


def _astar(carte, s, g):
    ny, cout = carte.ny, carte.cout
    gi, gj = divmod(g, ny)
    g_score = {s: 0.0}
    parent = {s: None}
    tas = [(0.0, s)]
    ferme = set()
    while tas:
        _, k = heapq.heappop(tas)
        if k == g:
            chemin = []
            while k is not None:
                chemin.append(k)
                k = parent[k]
            return chemin[::-1], g_score[g]
        if k in ferme:
            continue
        ferme.add(k)
        gk = g_score[k]
        ck = cout[k]
        for n, pas in _voisins(carte, k):
            cn = cout[n]
            if cn == INF or n in ferme:
                continue
            ng = gk + pas * (ck + cn) * 0.5
            if ng < g_score.get(n, INF):
                g_score[n] = ng
                parent[n] = k
                ni, nj = divmod(n, ny)
                di, dj = abs(ni - gi), abs(nj - gj)
                h = (di + dj) + (SQRT2 - 2.0) * min(di, dj)
                heapq.heappush(tas, (ng + h, n))
    return None, INF


def segment_libre(carte, a, b, cout_max=INF):
    """Le segment a -> b ne traverse que des cellules autorisées, de coût <= cout_max."""
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, int(d / (carte.res * 0.5)))
    for k in range(n + 1):
        t = k / n
        c = carte.cout_xy(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if c == INF or c > cout_max:
            return False
    return True


def chemin_libre(carte, points):
    return all(segment_libre(carte, a, b) for a, b in zip(points, points[1:]))


def _lisser(carte, pts, couts):
    """String pulling : du point courant, on saute au plus loin qu'on peut joindre en ligne droite."""
    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        k = len(pts) - 1
        while k > i + 1:
            if segment_libre(carte, pts[i], pts[k], max(couts[i:k + 1]) + 0.25):
                break
            k -= 1
        out.append(pts[k])
        i = k
    return out


def planifier(carte, depart, arrivee):
    """Plan du point depart (x, y) au point arrivee (x, y), ou None s'il n'y a pas de chemin."""
    ny = carte.ny
    s = _plus_proche_libre(carte, carte.cellule(*depart)[0] * ny + carte.cellule(*depart)[1], 20)
    gi, gj = carte.cellule(*arrivee)
    g0 = gi * ny + gj
    g = _plus_proche_libre(carte, g0, int(carte.cfg["tolerance_arrivee_mm"] / carte.res))
    if s is None or g is None:
        return None
    if s == g:
        pts = [tuple(depart), tuple(arrivee) if g == g0 else carte.centre(*divmod(g, ny))]
        return Plan(pts, math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]), 0.0, g != g0)
    cells, total = _astar(carte, s, g)
    if cells is None:
        return None
    pts = [carte.centre(*divmod(k, ny)) for k in cells]
    couts = [carte.cout[k] for k in cells]
    pts[0] = tuple(depart)
    fin = tuple(arrivee) if g == g0 else pts[-1]
    pts[-1] = fin
    lisse = _lisser(carte, pts, couts)
    longueur = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(lisse, lisse[1:]))
    return Plan(lisse, longueur, total * carte.res, g != g0, cells)


_CARTES_FIXES = {}


def carte_fixe(cfg):
    """Bords + obstacles fixes, mémorisés par configuration (copie à modifier)."""
    cle = json.dumps(cfg or {}, sort_keys=True, default=str)
    if cle not in _CARTES_FIXES:
        if len(_CARTES_FIXES) > 8:
            _CARTES_FIXES.clear()
        _CARTES_FIXES[cle] = Carte(cfg)
    return _CARTES_FIXES[cle].copie()


def construire(cfg, adversaires=(), points_lidar=(), chaleur=None, t=0.0, pierres=(), cible=None, robot=None):
    """Carte complète : cfg = section planif de la config ; adversaires = [(x, y, vx, vy)] posés comme
    obstacles fixes (planifier) ; pour planifier_temps, passer adversaires=() et une Dynamique.
    cible : (x, y), on ignore pierres et points LiDAR à moins de ignorer_pres_cible_mm (on va les
    prendre) ; robot : (x, y), on ignore les points LiDAR sur le robot lui-même."""
    carte = carte_fixe(cfg)
    r_ign = carte.cfg["ignorer_pres_cible_mm"]

    def garder(x, y, rayon_robot=0.0):
        if cible is not None and r_ign > 0 and math.hypot(x - cible[0], y - cible[1]) < r_ign:
            return False
        return not (robot is not None and rayon_robot and math.hypot(x - robot[0], y - robot[1]) < rayon_robot)
    carte.ajouter_pierres([p for p in pierres if garder(p[0], p[1], 260.0)])
    for a in adversaires:
        carte.ajouter_adversaire(*a)
    carte.ajouter_points([p for p in points_lidar if garder(p[0], p[1], 260.0)])
    if chaleur is not None:
        carte.ajouter_chaleur(chaleur, t)
    return carte


# =============================================================================================
# PLANIFICATION DANS LE TEMPS : adversaires prédits
# =============================================================================================
# A* sur les cellules où le coût d'un arc est une DURÉE (s) : distance / vitesse x surcoût de la
# cellule, + rotation (changement de direction par rapport à l'arc d'arrivée) / vitesse de rotation.
# À l'instant d'arrivée prévu dans chaque cellule, on regarde où sera chaque adversaire (piste de
# Kalman) : interdit si on y est en même temps que lui (rayon + incertitude plafonnée), surcoût autour
# (plus large quand la prédiction est incertaine).
# Le robot passe donc DERRIÈRE un adversaire qui traverse, et ne se laisse pas bloquer par un
# endroit que l'adversaire aura quitté quand il y arrivera.

class Dynamique:
    """Adversaires prédits vus par planifier_temps (pistes de core/suivi_adversaire.py)."""

    def __init__(self, pistes, t0, cfg=None, rayon_robot_mm=None):
        c = {**DEFAUTS, **(cfg or {})}
        self.pistes = list(pistes)
        self.t0 = t0
        r_robot = c["rayon_robot_mm"] if rayon_robot_mm is None else rayon_robot_mm
        self.r_dur = c["rayon_adversaire_mm"] + r_robot
        self.marge = c["marge_adversaire_mm"]
        self.w = c["poids_dynamique"]
        self.h = c["horizon_s"]
        self.sig_dur = c["sigma_dur_max_mm"]
        self.k = c["k_sigma"]
        self.tampon = c["tampon_mm"]
        self._cache = {}

    def _positions(self, t_rel):
        cle = int(t_rel * 10)                         # 0,1 s
        pos = self._cache.get(cle)
        if pos is None:
            pos = [p.position(self.t0 + min(cle / 10.0, self.h)) for p in self.pistes]
            self._cache[cle] = pos
        return pos

    def evaluer(self, x, y, t_rel, tampon=True):
        """(interdit, surcoût) pour le robot en (x, y) à t_rel secondes d'ici."""
        if not self.pistes:
            return False, 0.0
        # au-delà de l'horizon : l'adversaire reste à sa dernière position prédite (l'ignorer ferait
        # passer un chemin lointain à travers un robot arrêté) ; le surcoût, lui, s'éteint
        sur = 0.0
        decroit = max(0.0, 1.0 - t_rel / self.h)
        r_dur = self.r_dur + (self.tampon if tampon else 0.0)
        for px, py, sig in self._positions(t_rel):
            d = math.hypot(x - px, y - py)
            if d < r_dur + self.k * min(sig, self.sig_dur):
                return True, 0.0
            portee = self.r_dur + self.marge + sig
            if d < portee and decroit > 0:
                sur += self.w * decroit * (1.0 - max(0.0, d - self.r_dur) / (portee - self.r_dur))
        return False, sur

    def marge_min(self, points, temps, pas_mm=50.0):
        """Plus petite distance (mm, au-delà de la zone interdite) entre le chemin et un adversaire,
        échantillonnée le long des segments (instants interpolés), dans l'horizon de prédiction."""
        best = INF
        for (a, b), (ta, tb) in zip(zip(points, points[1:]), zip(temps, temps[1:])):
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            n = max(1, int(d / pas_mm))
            for k in range(n + 1):
                f = k / n
                t = ta + (tb - ta) * f
                x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
                for px, py, _ in self._positions(t):
                    best = min(best, math.hypot(x - px, y - py) - self.r_dur)
        return best


@dataclass
class PlanTemps:
    points: list                     # [(x, y)] départ inclus
    temps: list                      # instant prévu à chaque point (s depuis le calcul)
    duree: float
    longueur: float
    arrivee_deplacee: bool = False
    marge_adversaire_mm: float = INF

    def caps(self, theta_final):
        return Plan(self.points, self.longueur, 0.0).caps(theta_final)


_DIRS = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))   # i (X), j (Y) ; d x 45°


def _rotation_s(a_deg, b_deg, w):
    d = abs((b_deg - a_deg + 180.0) % 360.0 - 180.0)
    return d / w


def _temps_chemin(points, theta0, theta_final, v, w):
    """Instants de passage (s) le long d'une polyligne : rotation sur place à chaque sommet puis ligne."""
    t, cap, out = 0.0, theta0, [0.0]
    for a, b in zip(points, points[1:]):
        nc = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        t += _rotation_s(cap, nc, w) + math.hypot(b[0] - a[0], b[1] - a[1]) / v
        cap = nc
        out.append(t)
    if theta_final is not None:
        return out, t + _rotation_s(cap, theta_final, w)
    return out, t


def segment_libre_temps(carte, dyn, a, b, t_a, v, cout_max=INF, tampon=True):
    """Segment statiquement libre ET sans croiser un adversaire prédit, parcouru à v depuis t_a."""
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, int(d / (carte.res * 0.5)))
    for k in range(n + 1):
        f = k / n
        x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        c = carte.cout_xy(x, y)
        if c == INF or c > cout_max:
            return False
        if dyn is not None and dyn.evaluer(x, y, t_a + d * f / v, tampon)[0]:
            return False
    return True


def planifier_temps(carte, depart, arrivee, dyn=None, theta_final=None):
    """PlanTemps de depart (x, y, theta) à arrivee (x, y), ou None. dyn : Dynamique (adversaires)."""
    cfg = carte.cfg
    v, w = float(cfg["v_nominale_mm_s"]), float(cfg["w_nominale_deg_s"])
    ny, cout, res = carte.ny, carte.cout, carte.res
    i_s, j_s = carte.cellule(depart[0], depart[1])
    s = _plus_proche_libre(carte, i_s * ny + j_s, 20)
    gi, gj = carte.cellule(arrivee[0], arrivee[1])
    g0 = gi * ny + gj
    g = _plus_proche_libre(carte, g0, int(cfg["tolerance_arrivee_mm"] / res))
    if s is None or g is None:
        return None
    theta0 = depart[2] if len(depart) > 2 and depart[2] is not None else None
    gi, gj = divmod(g, ny)

    def h(k):
        i, j = divmod(k, ny)
        di, dj = abs(i - gi), abs(j - gj)
        return ((di + dj) + (SQRT2 - 2.0) * min(di, dj)) * res / v

    g_score = {s: 0.0}               # coût (s, surcoûts et rotations compris)
    t_reel = {s: 0.0}                # heure de passage prévue (s)
    cap_arrivee = {s: theta0}
    parent = {s: None}
    tas = [(h(s), 0.0, s)]
    ferme = set()
    dt_pas = (res / v, res * SQRT2 / v)
    while tas:
        _, gk, k = heapq.heappop(tas)
        if k in ferme:
            continue
        if k == g:
            break
        ferme.add(k)
        i, j = divmod(k, ny)
        ck = cout[k]
        cap_k = cap_arrivee[k]
        tk = t_reel[k]
        for d, (di, dj) in enumerate(_DIRS):
            a, b = i + di, j + dj
            if not (0 <= a < carte.nx and 0 <= b < ny):
                continue
            n = a * ny + b
            cn = cout[n]
            if cn == INF or n in ferme:
                continue
            diag = di != 0 and dj != 0
            if diag and (cout[(i + di) * ny + j] == INF or cout[i * ny + j + dj] == INF):
                continue
            cap_n = d * 45.0
            rot = _rotation_s(cap_k, cap_n, w) if cap_k is not None else 0.0
            # Heure : distance seule (+ rotation initiale, réelle) ; les marches de 45° de la grille
            # disparaissent au lissage, les compter retarderait le robot et fausserait l'adversaire.
            t_arr = tk + dt_pas[diag] + (rot if k == s else 0.0)
            cout_arc = dt_pas[diag] * (ck + cn) * 0.5 + rot
            if dyn is not None:
                x, y = carte.centre(a, b)
                interdit, sur = dyn.evaluer(x, y, t_arr)
                if interdit:
                    continue
                cout_arc += sur * dt_pas[diag]
            ng = gk + cout_arc
            if ng < g_score.get(n, INF):
                g_score[n] = ng
                t_reel[n] = t_arr
                parent[n] = k
                cap_arrivee[n] = cap_n
                heapq.heappush(tas, (ng + h(n), ng, n))
    if g not in parent:
        return None
    cells = []
    k = g
    while k is not None:
        cells.append(k)
        k = parent[k]
    cells.reverse()
    pts = [carte.centre(*divmod(k, ny)) for k in cells]
    couts = [cout[k] for k in cells]
    tps = [t_reel[k] for k in cells]
    pts[0] = (depart[0], depart[1])
    pts[-1] = (arrivee[0], arrivee[1]) if g == g0 else pts[-1]

    # Lissage : on relie deux points quand le segment est libre ET ne croise pas l'adversaire prédit,
    # à l'heure où le robot y passera sur le chemin LISSÉ (plus court que le zigzag de l'A*, donc
    # plus tôt) : heure recalculée au fil du chemin, rotation sur place comprise.
    out, idx = [pts[0]], 0
    t_cur, cap_cur = 0.0, theta0
    while idx < len(pts) - 1:
        k = len(pts) - 1
        while k > idx + 1:
            a, b = pts[idx], pts[k]
            cap = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            t0 = t_cur + (_rotation_s(cap_cur, cap, w) if cap_cur is not None else 0.0)
            if (dyn is None or not dyn.evaluer(a[0], a[1], t0)[0]) and \
                    segment_libre_temps(carte, dyn, a, b, t0, v, max(couts[idx:k + 1]) + 0.25):
                break
            k -= 1
        a, b = pts[idx], pts[k]
        cap = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        t_cur += (_rotation_s(cap_cur, cap, w) if cap_cur is not None else 0.0) + math.hypot(b[0] - a[0], b[1] - a[1]) / v
        cap_cur = cap
        out.append(b)
        idx = k
    temps, duree = _temps_chemin(out, theta0 if theta0 is not None else 0.0, theta_final, v, w)
    longueur = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(out, out[1:]))
    marge = dyn.marge_min(out, temps) if dyn is not None and dyn.pistes else INF
    return PlanTemps(out, temps, duree, longueur, g != g0, marge)


def reste_du_plan(plan, pose):
    """Partie du plan encore à parcourir depuis pose (x, y) : [pose] + points après le plus proche."""
    pts = plan.points
    best, k_best = INF, 0
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy or 1.0
        f = max(0.0, min(1.0, ((pose[0] - a[0]) * dx + (pose[1] - a[1]) * dy) / l2))
        d = math.hypot(pose[0] - a[0] - f * dx, pose[1] - a[1] - f * dy)
        if d < best:
            best, k_best = d, k
    return [(pose[0], pose[1])] + list(pts[k_best + 1:]), best


def choisir_plan(ancien, nouveau, carte, dyn, pose, theta_final=None, gain_min=0.15, ecart_max_mm=150.0):
    """Hystérésis : garde l'ancien chemin (sa partie restante) tant qu'il est encore valable et que le
    nouveau ne fait pas gagner au moins gain_min (15 %) de temps : évite d'hésiter entre passer à
    gauche ou à droite d'un adversaire à chaque recalcul. Renvoie (plan, change)."""
    if ancien is None:
        return nouveau, True
    nouveau_ok = nouveau is not None
    reste, ecart = reste_du_plan(ancien, pose)
    if ecart > ecart_max_mm or len(reste) < 2:
        return (nouveau, True) if nouveau_ok else (None, True)
    v = float(carte.cfg["v_nominale_mm_s"])
    w = float(carte.cfg["w_nominale_deg_s"])
    temps, duree = _temps_chemin(reste, pose[2] if len(pose) > 2 else 0.0, theta_final, v, w)
    valable = all(segment_libre_temps(carte, dyn, a, b, t, v, tampon=False)
                  for a, b, t in zip(reste, reste[1:], temps))
    if not valable:
        return (nouveau, True) if nouveau_ok else (None, True)
    if nouveau_ok and nouveau.duree < (1.0 - gain_min) * duree:
        return nouveau, True
    longueur = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(reste, reste[1:]))
    marge = dyn.marge_min(reste, temps) if dyn is not None and dyn.pistes else INF
    return PlanTemps(reste, temps, duree, longueur, ancien.arrivee_deplacee, marge), False
