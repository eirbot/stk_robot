"""Caméra embarquée : pixels -> repère robot, pose d'un tag ArUco (pur Python, testé sur PC).

REPÈRE ROBOT (corps) : origine = point de référence du robot (milieu de l'axe des roues, cf. frames),
  X vers l'avant, Y vers la gauche, Z vers le haut (Z = 0 au sol), millimètres.
  cap : degrés, 0 = X+ (devant), 90 = Y+ (gauche), normalisé dans ]-180, 180].
REPÈRE CAMÉRA (OpenCV) : x vers la droite de l'image, y vers le bas, z le long de l'axe optique.
MONTAGE (config camera.montage) : position (x, y, z) de la caméra dans le repère robot, puis
  lacet (0 = regarde devant, > 0 = tournée vers la gauche), tangage (> 0 = penchée vers le sol),
  roulis (rotation autour de l'axe optique, > 0 = côté droit de l'image vers le bas).

POSE D'UN TAG
  Un tag carré vu de biais apparaît en trapèze : le bord le plus proche est plus grand, la largeur
  est réduite d'environ cos(angle). C'est cette déformation qui donne l'angle. Un PnP libre
  (6 degrés de liberté) est ambigu pour un petit tag vu presque de face (deux solutions
  symétriques à quelques pixels près) ; on impose donc ce qu'on sait du tag :
  - "vertical"   : tag sur une face verticale (pierres 2027). Inconnues : x, y du centre, cap de la
                   normale à la face (vers l'extérieur de la face imprimée), et z s'il n'est pas donné.
                   Les 4 rotations du tag dans son plan (multiples de 90°) sont essayées.
  - "horizontal" : tag à plat, face vers le haut (2025). Inconnues : x, y, cap du bord haut du tag
                   (direction coin 3 -> coin 0), et z s'il n'est pas donné.
  Résolution : moindres carrés (Levenberg-Marquardt) sur l'écart entre coins observés et coins
  reprojetés, avec plusieurs points de départ. `err_px` = écart moyen résiduel, en pixels.
  z peut être None (inconnu), un nombre, ou une liste de hauteurs possibles (la meilleure gagne).
"""

import math
from dataclasses import dataclass, field

from core.frames import normalize_deg

# Ordre des coins ArUco (vus de face) : haut gauche, haut droit, bas droit, bas gauche.
# Coordonnées dans le plan du tag (a vers la droite, b vers le haut), en côtés de tag.
_COINS_TAG = ((-0.5, 0.5), (0.5, 0.5), (0.5, -0.5), (-0.5, -0.5))


# ---------------------------------------------------------------------------------------------
# Petite algèbre 3D (listes de 3 flottants, matrices = liste de lignes)

def _rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def _matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _matvec(m, v):
    return [m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2]]


def _transpose(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def _cross(u, v):
    return [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]


def _solve(a, b):
    """Résout a.x = b (petit système dense, pivot partiel). None si singulier."""
    n = len(b)
    m = [list(a[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            return None
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


# ---------------------------------------------------------------------------------------------
# Modèle de caméra

@dataclass
class Intrinseques:
    """Modèle sténopé + distorsion OpenCV (k1, k2, p1, p2, k3), pour une résolution donnée."""
    fx: float
    fy: float
    cx: float
    cy: float
    largeur: int
    hauteur: int
    dist: tuple = (0.0, 0.0, 0.0, 0.0, 0.0)

    @classmethod
    def nominales(cls, largeur, hauteur, champ_horizontal_deg):
        """Sans calibration : focale déduite du champ horizontal, centre au milieu, sans distorsion."""
        f = (largeur / 2) / math.tan(math.radians(champ_horizontal_deg) / 2)
        return cls(f, f, largeur / 2, hauteur / 2, largeur, hauteur)

    @classmethod
    def depuis_config(cls, d):
        """{"resolution": [w, h], "fx", "fy", "cx", "cy", "dist": [k1, k2, p1, p2, k3]}."""
        w, h = d["resolution"]
        dist = tuple(d.get("dist") or ()) + (0.0,) * 5
        return cls(float(d["fx"]), float(d["fy"]), float(d["cx"]), float(d["cy"]), int(w), int(h),
                   tuple(float(k) for k in dist[:5]))

    def pour_resolution(self, largeur, hauteur):
        """Mêmes intrinsèques à une autre résolution du même mode capteur (simple mise à l'échelle)."""
        if (largeur, hauteur) == (self.largeur, self.hauteur):
            return self
        sx, sy = largeur / self.largeur, hauteur / self.hauteur
        return Intrinseques(self.fx * sx, self.fy * sy, (self.cx + 0.5) * sx - 0.5,
                            (self.cy + 0.5) * sy - 0.5, largeur, hauteur, self.dist)

    def _distordre(self, x, y):
        k1, k2, p1, p2, k3 = self.dist
        r2 = x * x + y * y
        radial = 1 + r2 * (k1 + r2 * (k2 + r2 * k3))
        return (x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x),
                y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y)

    def projeter_normalise(self, x, y):
        """Coordonnées normalisées (X/Z, Y/Z) -> pixel (avec distorsion)."""
        xd, yd = self._distordre(x, y)
        return self.fx * xd + self.cx, self.fy * yd + self.cy

    def normaliser(self, u, v):
        """Pixel -> coordonnées normalisées sans distorsion (inversion itérative, comme OpenCV)."""
        xd, yd = (u - self.cx) / self.fx, (v - self.cy) / self.fy
        if not any(self.dist):
            return xd, yd
        k1, k2, p1, p2, k3 = self.dist
        x, y = xd, yd
        for _ in range(20):
            r2 = x * x + y * y
            radial = 1 + r2 * (k1 + r2 * (k2 + r2 * k3))
            dx = 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
            dy = p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
            x, y = (xd - dx) / radial, (yd - dy) / radial
        return x, y


class Camera:
    """Intrinsèques + montage sur le robot : passage pixel <-> repère robot."""

    def __init__(self, intr, x=0.0, y=0.0, z=0.0, lacet=0.0, tangage=0.0, roulis=0.0, calibree=True):
        self.intr = intr
        self.calibree = calibree                     # False : intrinsèques nominales (champ de vision)
        self.position = [float(x), float(y), float(z)]
        # Axes caméra exprimés dans le repère robot, caméra « droite » : z_c = X, x_c = -Y, y_c = -Z
        base = [[0, 0, 1], [-1, 0, 0], [0, -1, 0]]
        r = _matmul(_rot_z(math.radians(lacet)),
                    _matmul(_rot_y(math.radians(tangage)), _rot_x(math.radians(roulis))))
        self.r_robot_cam = _matmul(r, base)          # colonnes = axes caméra dans le repère robot
        self.r_cam_robot = _transpose(self.r_robot_cam)

    @classmethod
    def depuis_config(cls, cfg_camera, largeur, hauteur):
        """Section `camera` de config.json, pour des images de largeur x hauteur pixels."""
        d = cfg_camera.get("intrinseques")
        if d:
            intr = Intrinseques.depuis_config(d).pour_resolution(largeur, hauteur)
        else:
            intr = Intrinseques.nominales(largeur, hauteur, float(cfg_camera.get("champ_horizontal_deg", 62.2)))
        m = cfg_camera.get("montage") or {}
        return cls(intr, m.get("x", 0.0), m.get("y", 0.0), m.get("z", 0.0),
                   m.get("lacet", 0.0), m.get("tangage", 0.0), m.get("roulis", 0.0), calibree=bool(d))

    def vers_camera(self, p):
        """Point du repère robot -> repère caméra."""
        return _matvec(self.r_cam_robot, [p[0] - self.position[0], p[1] - self.position[1],
                                          p[2] - self.position[2]])

    def projeter(self, p):
        """Point du repère robot -> pixel, ou None s'il est derrière la caméra."""
        xc, yc, zc = self.vers_camera(p)
        if zc <= 1e-6:
            return None
        return self.intr.projeter_normalise(xc / zc, yc / zc)

    def rayon(self, u, v):
        """Pixel -> direction (repère robot) du rayon, composante caméra z = 1."""
        x, y = self.intr.normaliser(u, v)
        return _matvec(self.r_robot_cam, [x, y, 1.0])

    def pixel_au_sol(self, u, v, z=0.0):
        """Point du repère robot vu au pixel (u, v) à la hauteur z, ou None (rayon vers le haut)."""
        d = self.rayon(u, v)
        if abs(d[2]) < 1e-9:
            return None
        t = (z - self.position[2]) / d[2]
        if t <= 0:
            return None
        return [self.position[i] + t * d[i] for i in range(3)]


# ---------------------------------------------------------------------------------------------
# Pose d'un tag

@dataclass
class PoseTag:
    """Tag vu par la caméra, dans le repère robot (mm, degrés)."""
    id: int
    x: float
    y: float
    z: float
    cap: float              # vertical : normale à la face ; horizontal : bord haut du tag
    orientation: str        # "vertical" | "horizontal"
    taille_mm: float
    err_px: float           # écart moyen résiduel des coins (qualité de la mesure)
    quart: int = 0          # rotation du tag dans son plan (x 90°, sens trigo), mode vertical
    coins_px: list = field(default_factory=list)
    t: float = 0.0          # instant de l'image (time.time())

    @property
    def distance(self):
        """Distance horizontale du point de référence du robot au centre du tag."""
        return math.hypot(self.x, self.y)

    @property
    def ecart_angle(self):
        """Vertical : rotation (degrés) qu'il reste au robot pour faire face au tag (0 = bien en face)."""
        return normalize_deg(self.cap + 180.0)

    def point_devant(self, distance_mm):
        """Vertical : (x, y, cap) du point à distance_mm devant la face, robot tourné vers le tag."""
        c = math.radians(self.cap)
        return (self.x + distance_mm * math.cos(c), self.y + distance_mm * math.sin(c),
                normalize_deg(self.cap + 180.0))

    def vers_table(self, x_robot, y_robot, theta_robot):
        """(x, y, cap) du tag dans le repère table, connaissant la pose du robot."""
        t = math.radians(theta_robot)
        c, s = math.cos(t), math.sin(t)
        return (x_robot + self.x * c - self.y * s, y_robot + self.x * s + self.y * c,
                normalize_deg(self.cap + theta_robot))


def _axes_tag(orientation, cap, quart):
    """(droite, haut) du tag (vecteurs unitaires, repère robot) pour une orientation et un cap."""
    c, s = math.cos(cap), math.sin(cap)
    if orientation == "vertical":
        normale, haut = [c, s, 0.0], [0.0, 0.0, 1.0]
    else:
        normale, haut = [0.0, 0.0, 1.0], [c, s, 0.0]
    droite = _cross(haut, normale)
    for _ in range(quart % 4):                     # rotation de +90° dans le plan du tag
        droite, haut = haut, [-v for v in droite]
    return droite, haut


def _coins_modele(params, z_fixe, orientation, quart, taille):
    x, y = params[0], params[1]
    cap = params[2]
    z = z_fixe if z_fixe is not None else params[3]
    droite, haut = _axes_tag(orientation, cap, quart)
    centre = (x, y, z)
    return [[centre[i] + taille * (a * droite[i] + b * haut[i]) for i in range(3)] for a, b in _COINS_TAG]


def _residus(cam, obs_norm, params, z_fixe, orientation, quart, taille):
    """Écarts (en pixels, ~f x coordonnées normalisées) entre coins observés et modèle."""
    res = []
    f = cam.intr.fx
    for p, (xo, yo) in zip(_coins_modele(params, z_fixe, orientation, quart, taille), obs_norm):
        xc, yc, zc = cam.vers_camera(p)
        if zc <= 1e-3:
            return None
        res.append(f * (xc / zc - xo))
        res.append(f * (yc / zc - yo))
    return res


def _lm(cam, obs_norm, p0, z_fixe, orientation, quart, taille, iterations=40):
    """Levenberg-Marquardt, jacobien par différences finies. Renvoie (params, coût) ou (None, inf)."""
    p = list(p0)
    r = _residus(cam, obs_norm, p, z_fixe, orientation, quart, taille)
    if r is None:
        return None, math.inf
    cout = sum(v * v for v in r)
    lam = 1e-3
    pas = [0.01, 0.01, 1e-5, 0.01][:len(p)]
    for _ in range(iterations):
        jac = []
        for k in range(len(p)):
            q = list(p)
            q[k] += pas[k]
            rk = _residus(cam, obs_norm, q, z_fixe, orientation, quart, taille)
            if rk is None:
                return p, cout
            jac.append([(a - b) / pas[k] for a, b in zip(rk, r)])
        jtj = [[sum(jac[i][m] * jac[j][m] for m in range(len(r))) for j in range(len(p))] for i in range(len(p))]
        jtr = [sum(jac[i][m] * r[m] for m in range(len(r))) for i in range(len(p))]
        progres = False
        while lam < 1e8:
            a = [[jtj[i][j] + (lam * jtj[i][i] if i == j else 0.0) for j in range(len(p))] for i in range(len(p))]
            delta = _solve(a, [-v for v in jtr])
            if delta is None:
                lam *= 10
                continue
            q = [p[i] + delta[i] for i in range(len(p))]
            rq = _residus(cam, obs_norm, q, z_fixe, orientation, quart, taille)
            cq = sum(v * v for v in rq) if rq is not None else math.inf
            if cq < cout:
                p, r, lam, progres = q, rq, max(lam / 10, 1e-7), True
                fin = cout - cq < 1e-10 * (1 + cout)
                cout = cq
                break
            lam *= 10
        if not progres or fin:
            break
    return p, cout


def estimer_pose(cam, coins_px, taille_mm, orientation="vertical", z=None, quarts=None, id_tag=-1, t=0.0):
    """Pose d'un tag (PoseTag) à partir de ses 4 coins en pixels (ordre ArUco), ou None.

    z : hauteur du centre du tag (mm) si connue, liste de hauteurs possibles, ou None (inconnue).
    quarts : rotations dans le plan à essayer (mode vertical), par défaut les 4.
    """
    if orientation not in ("vertical", "horizontal"):
        raise ValueError(f"orientation inconnue : {orientation}")
    obs_norm = [cam.intr.normaliser(u, v) for u, v in coins_px]
    xs, ys = [o[0] for o in obs_norm], [o[1] for o in obs_norm]
    centre_n = (sum(xs) / 4, sum(ys) / 4)
    cotes = [math.hypot(obs_norm[i][0] - obs_norm[(i + 1) % 4][0], obs_norm[i][1] - obs_norm[(i + 1) % 4][1])
             for i in range(4)]
    cote_n = max(cotes)
    if cote_n <= 1e-9:
        return None
    rayon = _matvec(cam.r_robot_cam, [centre_n[0], centre_n[1], 1.0])
    profondeur = taille_mm / cote_n                  # distance le long de l'axe optique, ordre de grandeur

    z_essais = z if isinstance(z, (list, tuple)) else [z]
    if quarts is None:
        quarts = range(4) if orientation == "vertical" else (0,)

    # Départs : (coût initial, params, z, quart) ; LM seulement sur les plus prometteurs
    departs = []
    for z_fixe in z_essais:
        t_ray = profondeur
        if z_fixe is not None and abs(rayon[2]) > 1e-6:
            t_plan = (z_fixe - cam.position[2]) / rayon[2]
            if t_plan > 0 and 0.3 * profondeur < t_plan < 3 * profondeur:
                t_ray = t_plan
        centre = [cam.position[i] + t_ray * rayon[i] for i in range(3)]
        vers_cam = math.atan2(cam.position[1] - centre[1], cam.position[0] - centre[0])
        if orientation == "vertical":
            caps = [vers_cam + math.radians(d) for d in (0, -40, 40)]
        else:
            caps = [math.radians(d) for d in (0, 90, 180, -90)]
        for quart in quarts:
            for cap0 in caps:
                p0 = [centre[0], centre[1], cap0] + ([] if z_fixe is not None else [centre[2]])
                r = _residus(cam, obs_norm, p0, z_fixe, orientation, quart, taille_mm)
                if r is not None:
                    departs.append((sum(v * v for v in r), p0, z_fixe, quart))
    departs.sort(key=lambda d: d[0])

    meilleur = (math.inf, None, None, 0)
    for _, p0, z_fixe, quart in departs[:max(2, len(z_essais))]:
        p, cout = _lm(cam, obs_norm, p0, z_fixe, orientation, quart, taille_mm)
        if p is None or cout >= meilleur[0]:
            continue
        if orientation == "vertical":
            # la face imprimée doit être tournée vers la caméra
            normale = [math.cos(p[2]), math.sin(p[2])]
            if normale[0] * (cam.position[0] - p[0]) + normale[1] * (cam.position[1] - p[1]) <= 0:
                continue
        meilleur = (cout, p, z_fixe, quart)
    cout, p, z_fixe, quart = meilleur
    if p is None:
        return None
    return PoseTag(id=id_tag, x=p[0], y=p[1], z=z_fixe if z_fixe is not None else p[3],
                   cap=normalize_deg(math.degrees(p[2])), orientation=orientation, taille_mm=taille_mm,
                   err_px=math.sqrt(cout / 4), quart=quart, coins_px=[tuple(c) for c in coins_px], t=t)


def projeter_tag(cam, x, y, z, cap_deg, taille_mm, orientation="vertical", quart=0):
    """Coins (pixels, ordre ArUco) d'un tag placé à la pose donnée (repère robot). Sert aux tests,
    et à dessiner la pose estimée par-dessus l'image."""
    coins = _coins_modele([x, y, math.radians(cap_deg), z], None, orientation, quart, taille_mm)
    return [cam.projeter(p) for p in coins]
