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


def construire(cfg, adversaires=(), points_lidar=(), chaleur=None, t=0.0):
    """Carte complète : cfg = section planif de la config ; adversaires = [(x, y, vx, vy)]."""
    carte = Carte(cfg)
    for a in adversaires:
        carte.ajouter_adversaire(*a)
    carte.ajouter_points(points_lidar)
    if chaleur is not None:
        carte.ajouter_chaleur(chaleur, t)
    return carte
