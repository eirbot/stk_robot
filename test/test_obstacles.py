"""Tests de Rasp/core/obstacles.py (décision d'évitement à partir des tours LiDAR)."""
import math
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Rasp"))

from core import obstacles  # noqa: E402
from core.obstacles import BACK, CLEAR, FRONT, STOP  # noqa: E402


def scan(points=(), closest=None):
    """Scan avec des points (angle LiDAR en degrés, distance mm)."""
    sectors = [0.0] * obstacles.SECTORS
    for angle, dist in points:
        i = int((angle % 360) // obstacles.SECTOR_DEG)
        sectors[i] = dist if sectors[i] == 0 else min(sectors[i], dist)
    c = closest or (min(points, key=lambda p: p[1]) if points else (0.0, 0.0))
    return obstacles.Scan(c[0], c[1], tuple(sectors))


def packet(points=()):
    s = scan(points)
    return struct.pack(f"<4sff{obstacles.SECTORS}f", b"LDR2", s.closest_angle, s.closest_dist, *s.sectors)


class TestParse(unittest.TestCase):
    def test_paquet_valide(self):
        s = obstacles.parse_scan(packet([(10.0, 300.0), (200.0, 900.0)]))
        self.assertEqual(s.closest_dist, 300.0)
        self.assertEqual(s.sectors[2], 300.0)        # 10° -> secteur [10, 15[
        self.assertEqual(s.sectors[40], 900.0)       # 200° -> secteur [200, 205[

    def test_paquet_invalide(self):
        self.assertIsNone(obstacles.parse_scan(b"abc"))
        self.assertIsNone(obstacles.parse_scan(b"XXXX" + packet()[4:]))
        self.assertIsNone(obstacles.parse_scan(b"\0" * 64))  # ancien format (64 octets)


class TestClassify(unittest.TestCase):
    def c(self, points, mode="MATCH"):
        return obstacles.classify(scan(points), mode, seuil_mm=350.0, near_mm=130.0)

    def test_libre(self):
        self.assertEqual(self.c([]), CLEAR)
        self.assertEqual(self.c([(0.0, 800.0), (180.0, 800.0)]), CLEAR)

    def test_devant(self):
        self.assertEqual(self.c([(0.0, 300.0)]), FRONT)
        self.assertEqual(self.c([(350.0, 300.0)]), FRONT)   # -10°
        self.assertEqual(self.c([(30.0, 230.0)]), FRONT)    # cône large : 0,7 x seuil
        self.assertEqual(self.c([(30.0, 300.0)]), CLEAR)

    def test_derriere(self):
        self.assertEqual(self.c([(180.0, 300.0)]), BACK)
        self.assertEqual(self.c([(150.0, 230.0)]), BACK)

    def test_cotes_ignores(self):
        # Mur latéral à 200 mm : ni devant ni derrière (avant : classé « arrière »)
        self.assertEqual(self.c([(90.0, 200.0), (270.0, 200.0)]), CLEAR)

    def test_mur_lateral_ne_masque_pas_le_robot_devant(self):
        # L'ancien driver n'envoyait que le point le plus proche (le mur) : le robot devant était ignoré
        self.assertEqual(self.c([(90.0, 150.0), (0.0, 300.0)]), FRONT)

    def test_tout_pres(self):
        self.assertEqual(self.c([(90.0, 100.0)]), STOP)

    def test_devant_et_derriere(self):
        self.assertEqual(self.c([(0.0, 300.0), (180.0, 300.0)]), STOP)

    def test_homologation(self):
        self.assertEqual(self.c([(90.0, 450.0)], "HOMOLOGATION"), STOP)
        self.assertEqual(self.c([(90.0, 600.0)], "HOMOLOGATION"), CLEAR)

    def test_off(self):
        self.assertEqual(self.c([(0.0, 100.0)], "OFF"), CLEAR)


class TestDetector(unittest.TestCase):
    def test_delai_avant_de_repartir(self):
        d = obstacles.ObstacleDetector(seuil_mm=350.0, clear_delay_s=1.0)
        self.assertEqual(d.update(scan([(0.0, 300.0)]), "MATCH", 10.0), FRONT)
        # Obstacle parti : l'ESP garde FRONT pendant le délai (avant, il recevait 0 tout de suite)
        self.assertEqual(d.update(scan([]), "MATCH", 10.5), FRONT)
        self.assertEqual(d.update(scan([]), "MATCH", 11.0), CLEAR)

    def test_changement_de_type_immediat(self):
        d = obstacles.ObstacleDetector(seuil_mm=350.0)
        d.update(scan([(0.0, 300.0)]), "MATCH", 0.0)
        self.assertEqual(d.update(scan([(180.0, 300.0)]), "MATCH", 0.1), BACK)

    def test_perte_du_lidar(self):
        d = obstacles.ObstacleDetector()
        self.assertEqual(d.on_timeout(5.0), STOP)
        self.assertEqual(d.update(scan([]), "MATCH", 5.5), STOP)   # garde STOP pendant le délai
        self.assertEqual(d.update(scan([]), "MATCH", 6.1), CLEAR)

    def test_off_remet_a_zero(self):
        d = obstacles.ObstacleDetector()
        d.update(scan([(0.0, 300.0)]), "MATCH", 0.0)
        self.assertEqual(d.update(None, "OFF", 0.1), CLEAR)


class TestHorsTable(unittest.TestCase):
    """Points hors de la table effacés avant la décision (gens au bord de la table)."""

    def test_point_hors_table_ignore(self):
        # Robot à 300 mm du bord X = 0, tourné vers lui : un point à 340 mm devant est dehors
        s = scan([(0.0, 340.0)])
        self.assertEqual(obstacles.classify(s, "MATCH", 350.0), FRONT)
        f = obstacles.filter_outside_table(s, (300.0, 0.0, 180.0))
        self.assertEqual(obstacles.classify(f, "MATCH", 350.0), CLEAR)

    def test_point_sur_table_garde(self):
        s = scan([(0.0, 200.0)])
        f = obstacles.filter_outside_table(s, (1000.0, 0.0, 0.0))
        self.assertEqual(f.sectors, s.sectors)

    def test_marge(self):
        # Point à 20 mm à l'intérieur du bord : gardé sans marge, effacé avec 40 mm
        s = scan([(90.0, 1480.0)])
        pose = (1000.0, 0.0, 0.0)          # 90° LiDAR (sens trigo) = vers Y+
        self.assertNotEqual(obstacles.filter_outside_table(s, pose, 0.0).sectors, (0.0,) * obstacles.SECTORS)
        self.assertEqual(obstacles.filter_outside_table(s, pose, 40.0).sectors, (0.0,) * obstacles.SECTORS)

    def test_montage_sens_horaire(self):
        # LiDAR qui tourne en sens horaire : son angle 90° est à droite du robot (Y-)
        s = scan([(90.0, 1000.0)])
        (_, x, y), = obstacles.sector_points(s, (1000.0, 0.0, 0.0), {"sens": -1})
        self.assertAlmostEqual(x, 1000.0 + 1000.0 * math.cos(math.radians(-92.5)), places=3)
        self.assertLess(y, -990.0)

    def test_montage_decale(self):
        s = scan([(0.0, 100.0)])
        (_, x, y), = obstacles.sector_points(s, (500.0, 200.0, 90.0), {"x": 50.0, "y": 0.0})
        # repère robot : (50 + 100 cos 2,5°, 100 sin 2,5°), puis rotation de 90°
        self.assertAlmostEqual(x, 500.0 - 100.0 * math.sin(math.radians(2.5)), places=3)
        self.assertAlmostEqual(y, 200.0 + 50.0 + 100.0 * math.cos(math.radians(2.5)), places=3)

    def test_decision_avec_montage_tourne(self):
        # LiDAR monté avec son 0 vers la gauche du robot : un point à son angle -90° est devant
        s = scan([(270.0, 300.0)])
        self.assertEqual(obstacles.classify(s, "MATCH", 350.0), CLEAR)          # vu « à droite »
        self.assertEqual(obstacles.classify(s, "MATCH", 350.0, montage={"angle": 90.0}), FRONT)

    def test_sans_pose(self):
        s = scan([(0.0, 100.0)])
        self.assertIs(obstacles.filter_outside_table(s, None), s)


if __name__ == "__main__":
    unittest.main()
