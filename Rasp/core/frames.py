"""Repères de coordonnées : définition UNIQUE et conversions (pur Python, testé).

REPÈRE TABLE (= repère robot, celui de toute la stratégie, de l'ESP et de l'IHM)
  - X : largeur de la table, 0 -> 2000 mm, depuis le bord « haut » de la carte.
  - Y : longueur de la table, -1500 -> +1500 mm, centrée.
  - theta : degrés, 0 = vers +X, 90 = vers +Y (sens trigonométrique), normalisé dans ]-180, 180].
  - Équipe BLEUE : coordonnées telles quelles. Équipe JAUNE : symétrie par rapport à
    l'axe X (y -> -y, theta -> -theta). Les stratégies sont écrites côté BLEUE.

REPÈRE CAMÉRA ZÉNITHALE (sortie de vision_deporte/computePosition, en mètres)
  - Même orientation que le repère table (computePosition applique déjà la rotation Rzn) :
    conversion = mètres -> millimètres, theta inchangé.

REPÈRE AFFICHAGE 3D (map.js / Three.js) : cf. Base/Web/static/js/frames.js, qui
implémente les mêmes formules (testées dans test/frames.test.mjs).
"""

import math

TABLE_X_MIN, TABLE_X_MAX = 0.0, 2000.0
TABLE_Y_MIN, TABLE_Y_MAX = -1500.0, 1500.0


def normalize_deg(theta):
    """Angle en degrés ramené dans ]-180, 180]."""
    t = math.fmod(theta, 360.0)
    if t <= -180.0:
        t += 360.0
    elif t > 180.0:
        t -= 360.0
    return t


def angle_diff_deg(a, b):
    """a - b ramené dans ]-180, 180] (degrés)."""
    return normalize_deg(a - b)


def mirror_for_team(x, y, theta=None, team="BLEUE"):
    """Coordonnées écrites côté BLEUE -> coordonnées réelles pour `team`.
    La symétrie est son propre inverse : la même fonction sert dans les deux sens."""
    if team != "JAUNE":
        return x, y, theta
    return x, -y, (normalize_deg(-theta) if theta is not None else None)


def in_table(x, y, margin=0.0):
    return (TABLE_X_MIN + margin <= x <= TABLE_X_MAX - margin
            and TABLE_Y_MIN + margin <= y <= TABLE_Y_MAX - margin)


def camera_to_table(x_m, y_m, theta_deg):
    """Pose de la caméra zénithale (m, degrés) -> repère table (mm, degrés)."""
    return x_m * 1000.0, y_m * 1000.0, normalize_deg(theta_deg)


def apply_rigid(x, y, theta, dx=0.0, dy=0.0, rotation_deg=0.0):
    """Changement de repère rigide (rotation autour de l'origine puis translation) :
    sert au réglage fin caméra -> odométrie (config vision_odom.repere)."""
    r = math.radians(rotation_deg)
    xr = dx + x * math.cos(r) - y * math.sin(r)
    yr = dy + x * math.sin(r) + y * math.cos(r)
    return xr, yr, normalize_deg(theta + rotation_deg)


def apply_camera_repere(x, y, theta, repere=None):
    """Correction de la pose caméra (config vision_odom.repere) : mise à l'échelle autour de
    (centre_x, centre_y) puis changement de repère rigide (rotation_deg autour de l'origine, dx, dy).
    L'échelle compense une caméra qui voit les distances trop grandes ou trop petites ; le calcul
    se fait avec tools/calibrer_camera.py à partir de quelques positions mesurées au mètre."""
    r = repere or {}
    s = float(r.get("echelle", 1.0))
    cx, cy = float(r.get("centre_x", 1000.0)), float(r.get("centre_y", 0.0))
    x, y = cx + s * (x - cx), cy + s * (y - cy)
    return apply_rigid(x, y, theta, float(r.get("dx", 0.0)), float(r.get("dy", 0.0)),
                       float(r.get("rotation_deg", 0.0)))


# Encombrement du robot autour de son point de référence (milieu de l'axe des roues, celui de
# l'odométrie), mesuré sur le modèle MuJoCo (tools/encombrement_robot.py) ; même valeurs dans frames.js.
# L'axe des roues n'est PAS au centre du robot : 245,5 mm devant, 102 mm derrière.
ROBOT_FRONT_MM = 245.5
ROBOT_BACK_MM = 102.0
ROBOT_HALF_WIDTH_MM = 188.2
ROBOT_HEIGHT_MM = 450.0


def robot_corners(x, y, theta):
    """Coins de l'encombrement (repère table) : avant gauche, avant droit, arrière droit, arrière gauche."""
    t = math.radians(theta)
    c, s = math.cos(t), math.sin(t)
    return [(x + fx * c - fy * s, y + fx * s + fy * c)
            for fx, fy in ((ROBOT_FRONT_MM, ROBOT_HALF_WIDTH_MM), (ROBOT_FRONT_MM, -ROBOT_HALF_WIDTH_MM),
                           (-ROBOT_BACK_MM, -ROBOT_HALF_WIDTH_MM), (-ROBOT_BACK_MM, ROBOT_HALF_WIDTH_MM))]


def offset_along(x, y, theta, distance):
    """Point à `distance` mm devant (distance > 0) ou derrière (< 0) la pose (x, y, theta)."""
    t = math.radians(theta)
    return x + distance * math.cos(t), y + distance * math.sin(t)
