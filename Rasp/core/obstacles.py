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
"""

import struct
from dataclasses import dataclass

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


def _center_angle(i):
    """Angle du milieu du secteur i, ramené dans ]-180, 180]."""
    a = i * SECTOR_DEG + SECTOR_DEG / 2.0
    return a - 360.0 if a > 180.0 else a


def classify(scan, mode, seuil_mm, near_mm=130.0):
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
        a = abs(_center_angle(i))
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

    def __init__(self, seuil_mm=350.0, near_mm=130.0, clear_delay_s=1.0):
        self.seuil_mm = seuil_mm
        self.near_mm = near_mm
        self.clear_delay_s = clear_delay_s
        self.state = CLEAR
        self._last_obstacle_t = None

    def update(self, scan, mode, now):
        raw = classify(scan, mode, self.seuil_mm, self.near_mm)
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
