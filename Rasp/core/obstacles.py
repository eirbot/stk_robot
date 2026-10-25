"""Évitement : tours LiDAR -> état d'obstacle envoyé à l'ESP moteurs (pur Python, testé).

Paquet UDP envoyé par Rasp/LiDAR/lidar_udp.cpp à chaque tour (little-endian) :
    "LDR2", angle du point le plus proche (float, degrés), sa distance (float, mm ; 0 = aucun),
    puis SECTORS floats : distance minimale vue dans chaque secteur de SECTOR_DEG degrés
    (secteur i = angles [i*SECTOR_DEG, (i+1)*SECTOR_DEG[, 0 = rien vu).

États (protocole ESP moteurs, commande « L ») :
    CLEAR 0 : libre ; STOP 1 : tout s'arrête (rotations comprises) ;
    FRONT 2 : marche avant interdite ; BACK 3 : marche arrière interdite.

Règles en mode MATCH (angles LiDAR : 0 = avant du robot) :
    - un point à moins de `near_mm` dans n'importe quelle direction : STOP ;
    - devant : à moins de `seuil_mm` dans le cône ±CONE_FULL_DEG, ou de `seuil_mm` x SIDE_FACTOR
      jusqu'à ±CONE_WIDE_DEG : FRONT ; derrière, symétriquement : BACK ; les deux : STOP.
    - sur les côtés (au-delà de ±CONE_WIDE_DEG de l'axe) : ignoré, sauf `near_mm`. Un mur
      latéral ne masque plus un robot devant (tous les secteurs sont examinés).
Mode HOMOLOGATION : un point à moins de HOMOLOGATION_MM dans n'importe quelle direction : STOP.

L'état ne revient à CLEAR qu'après `clear_delay_s` sans obstacle (évite que le robot
reparte et s'arrête en boucle quand l'obstacle est à la limite du seuil).

Points hors de la table (gens au bord, mains, sacs) : `filter_outside_table` efface les secteurs
dont le point, placé dans le repère table avec la pose du robot, est au-delà des bords
(moins `marge_mm`, positive = vers l'intérieur). Sans pose fiable, on ne filtre pas.
Montage du LiDAR (config lidar.montage) : position (x, y) dans le repère robot, `angle` = angle
robot du 0 du LiDAR, `sens` = +1 si les angles LiDAR tournent en sens trigo, -1 sinon.
"""

import math
import struct
from dataclasses import dataclass

from core import frames

CLEAR, STOP, FRONT, BACK = 0, 1, 2, 3

SECTOR_DEG = 5
SECTORS = 360 // SECTOR_DEG
_PACKET = struct.Struct(f"<4sff{SECTORS}f")
PACKET_SIZE = _PACKET.size

CONE_FULL_DEG = 22.5
CONE_WIDE_DEG = 45.0
SIDE_FACTOR = 0.7
HOMOLOGATION_MM = 500.0


@dataclass
class Scan:
    closest_angle: float           # degrés, angle LiDAR
    closest_dist: float            # mm, 0 = aucun point
    sectors: tuple                 # mm par secteur, 0 = rien vu


def parse_scan(data):
    """Paquet UDP -> Scan, ou None s'il n'a pas le bon format."""
    if len(data) != PACKET_SIZE:
        return None
    magic, angle, dist, *sectors = _PACKET.unpack(data)
    if magic != b"LDR2":
        return None
    return Scan(angle, dist, tuple(sectors))


def sector_points(scan, pose, montage=None):
    """[(i, x, y)] : milieu de chaque secteur vu, dans le repère table, pose = (x, y, theta) du robot."""
    m = montage or {}
    lx, ly = float(m.get("x", 0.0)), float(m.get("y", 0.0))
    offset, sens = float(m.get("angle", 0.0)), float(m.get("sens", 1.0))
    rx, ry, rt = pose
    c, s = math.cos(math.radians(rt)), math.sin(math.radians(rt))
    out = []
    for i, d in enumerate(scan.sectors):
        if d <= 0.0:
            continue
        a = math.radians(offset + sens * (i * SECTOR_DEG + SECTOR_DEG / 2.0))
        px, py = lx + d * math.cos(a), ly + d * math.sin(a)
        out.append((i, rx + px * c - py * s, ry + px * s + py * c))
    return out


def filter_outside_table(scan, pose, marge_mm=40.0, montage=None):
    """Scan sans les secteurs dont le point est hors de la table (cf. docstring du module)."""
    if pose is None:
        return scan
    sectors = list(scan.sectors)
    for i, x, y in sector_points(scan, pose, montage):
        if not frames.in_table(x, y, marge_mm):
            sectors[i] = 0.0
    if sectors == list(scan.sectors):
        return scan
    # point le plus proche (affichage) : recalculé parmi les secteurs gardés
    vus = [(d, i) for i, d in enumerate(sectors) if d > 0.0]
    if not vus:
        return Scan(0.0, 0.0, tuple(sectors))
    d, i = min(vus)
    return Scan(i * SECTOR_DEG + SECTOR_DEG / 2.0, d, tuple(sectors))


def _center_angle(i, montage=None):
    """Angle robot (0 = avant) du milieu du secteur i, ramené dans ]-180, 180]."""
    m = montage or {}
    a = float(m.get("angle", 0.0)) + float(m.get("sens", 1.0)) * (i * SECTOR_DEG + SECTOR_DEG / 2.0)
    return frames.normalize_deg(a)


def classify(scan, mode, seuil_mm, near_mm=130.0, montage=None):
    """État d'obstacle d'un tour, sans mémoire (cf. ObstacleDetector pour le délai de retour)."""
    if mode == "OFF":
        return CLEAR
    front = back = False
    for i, d in enumerate(scan.sectors):
        if d <= 0.0:
            continue
        if mode == "HOMOLOGATION":
            if d < HOMOLOGATION_MM:
                return STOP
            continue
        if d < near_mm:
            return STOP
        a = abs(_center_angle(i, montage))
        off_axis_front, off_axis_back = a, 180.0 - a
        limit_front = seuil_mm if off_axis_front <= CONE_FULL_DEG else seuil_mm * SIDE_FACTOR
        limit_back = seuil_mm if off_axis_back <= CONE_FULL_DEG else seuil_mm * SIDE_FACTOR
        if off_axis_front <= CONE_WIDE_DEG and d < limit_front:
            front = True
        elif off_axis_back <= CONE_WIDE_DEG and d < limit_back:
            back = True
    if front and back:
        return STOP
    return FRONT if front else BACK if back else CLEAR


class ObstacleDetector:
    """État d'obstacle à envoyer à l'ESP, avec délai avant de revenir à CLEAR."""

    def __init__(self, seuil_mm=350.0, near_mm=130.0, clear_delay_s=1.0, montage=None):
        self.montage = montage
        self.seuil_mm = seuil_mm
        self.near_mm = near_mm
        self.clear_delay_s = clear_delay_s
        self.state = CLEAR
        self._last_obstacle_t = None

    def update(self, scan, mode, now):
        raw = classify(scan, mode, self.seuil_mm, self.near_mm, self.montage)
        if mode == "OFF":
            self.state, self._last_obstacle_t = CLEAR, None
        elif raw != CLEAR:
            self.state, self._last_obstacle_t = raw, now
        elif self._last_obstacle_t is None or now - self._last_obstacle_t >= self.clear_delay_s:
            self.state = CLEAR
        # sinon : on garde le dernier état pendant le délai
        return self.state

    def on_timeout(self, now):
        """Plus de tours LiDAR : sans capteur on ne peut plus éviter, tout s'arrête."""
        self.state, self._last_obstacle_t = STOP, now
        return self.state
