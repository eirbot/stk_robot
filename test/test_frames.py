"""Tests des repères (Rasp/core/frames.py). Lancer : python3 -m unittest discover -s test"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import frames  # noqa: E402


class TestAngles(unittest.TestCase):
    def test_normalize(self):
        for raw, expected in [(0, 0), (180, 180), (-180, 180), (190, -170), (-190, 170),
                              (360, 0), (540, 180), (-725, -5), (270, -90)]:
            self.assertAlmostEqual(frames.normalize_deg(raw), expected, msg=raw)

    def test_angle_diff(self):
        self.assertAlmostEqual(frames.angle_diff_deg(10, 350), 20)
        self.assertAlmostEqual(frames.angle_diff_deg(350, 10), -20)
        self.assertAlmostEqual(frames.angle_diff_deg(-170, 170), 20)


class TestSymetrie(unittest.TestCase):
    def test_bleue_inchangee(self):
        self.assertEqual(frames.mirror_for_team(700, 1250, 30, "BLEUE"), (700, 1250, 30))

    def test_jaune(self):
        x, y, t = frames.mirror_for_team(700, 1250, 30, "JAUNE")
        self.assertEqual((x, y), (700, -1250))
        self.assertAlmostEqual(t, -30)

    def test_jaune_angle_normalise(self):
        # L'ancienne version renvoyait 270 : même direction, mais hors ]-180, 180]
        self.assertAlmostEqual(frames.mirror_for_team(0, 0, 90, "JAUNE")[2], -90)
        self.assertAlmostEqual(frames.mirror_for_team(0, 0, 180, "JAUNE")[2], 180)

    def test_symetrie_involutive(self):
        for pose in [(148, 1149, 0), (1200, 600, -90), (1800, -100, 90), (1, -2, 179)]:
            once = frames.mirror_for_team(*pose, team="JAUNE")
            twice = frames.mirror_for_team(*once, team="JAUNE")
            self.assertAlmostEqual(twice[0], pose[0])
            self.assertAlmostEqual(twice[1], pose[1])
            self.assertAlmostEqual(frames.angle_diff_deg(twice[2], pose[2]), 0)

    def test_theta_absent(self):
        self.assertEqual(frames.mirror_for_team(10, 20, None, "JAUNE"), (10, -20, None))


class TestConversions(unittest.TestCase):
    def test_camera_to_table(self):
        self.assertEqual(frames.camera_to_table(0.5, -0.25, 190), (500.0, -250.0, -170.0))

    def test_apply_rigid_identite(self):
        self.assertEqual(frames.apply_rigid(100, 200, 30), (100, 200, 30))

    def test_apply_rigid_rotation(self):
        x, y, t = frames.apply_rigid(100, 0, 0, dx=10, dy=-5, rotation_deg=90)
        self.assertAlmostEqual(x, 10)
        self.assertAlmostEqual(y, 95)
        self.assertAlmostEqual(t, 90)

    def test_apply_camera_repere_identite(self):
        self.assertEqual(frames.apply_camera_repere(100, 200, 30, {}), (100.0, 200.0, 30))
        self.assertEqual(frames.apply_camera_repere(100, 200, 30, None), (100.0, 200.0, 30))

    def test_apply_camera_repere_echelle(self):
        # Caméra qui voit 10 % trop grand autour du centre de la table (1000, 0)
        x, y, t = frames.apply_camera_repere(1988, -11, 179, {"echelle": 1 / 1.1})
        self.assertAlmostEqual(x, 1898.18, places=1)
        self.assertAlmostEqual(y, -10.0, places=1)
        self.assertAlmostEqual(t, 179)

    def test_calibrer_camera_retrouve_le_reglage(self):
        """tools/calibrer_camera.py doit retrouver une erreur connue (échelle, rotation, décalage)."""
        import cmath
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "calibrer_camera", os.path.join(os.path.dirname(__file__), "..", "tools", "calibrer_camera.py"))
        cal = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cal)
        vrai = {"echelle": 0.92, "centre_x": 1000.0, "centre_y": 0.0, "rotation_deg": 1.5, "dx": 12.0, "dy": -30.0}
        pts = []
        for xm, ym in [(300, -1200), (1700, -1200), (1000, 0), (300, 1200), (1700, 1100)]:
            w = complex(xm, ym)
            # Caméra brute = inverse de la correction
            p = (w - complex(vrai["dx"], vrai["dy"])) / cmath.exp(1j * math.radians(vrai["rotation_deg"]))
            z = complex(1000, 0) + (p - complex(1000, 0)) / vrai["echelle"]
            pts.append((w, z))
        rep = cal.to_repere(*cal.fit(pts))
        for k in ("echelle", "rotation_deg", "dx", "dy"):
            self.assertAlmostEqual(rep[k], vrai[k], places=1, msg=k)
        # Et la formule de l'outil est bien celle du robot
        for w, z in pts:
            x, y, _ = frames.apply_camera_repere(z.real, z.imag, 0, rep)
            self.assertAlmostEqual(x, w.real, delta=0.5)
            self.assertAlmostEqual(y, w.imag, delta=0.5)

    def test_offset_along(self):
        x, y = frames.offset_along(1000, 0, 90, 100)
        self.assertAlmostEqual(x, 1000)
        self.assertAlmostEqual(y, 100)
        x, y = frames.offset_along(1000, 0, 0, -180)
        self.assertAlmostEqual(x, 820)

    def test_in_table(self):
        self.assertTrue(frames.in_table(1000, 0))
        self.assertTrue(frames.in_table(0, -1500))
        self.assertFalse(frames.in_table(2100, 0))
        self.assertFalse(frames.in_table(100, 0, margin=150))


if __name__ == "__main__":
    unittest.main()


class TestEncombrement(unittest.TestCase):
    def test_coins(self):
        c0 = frames.robot_corners(1000, 0, 0)
        self.assertAlmostEqual(c0[0][0], 1000 + frames.ROBOT_FRONT_MM)
        self.assertAlmostEqual(c0[0][1], frames.ROBOT_HALF_WIDTH_MM)
        self.assertAlmostEqual(c0[2][0], 1000 - frames.ROBOT_BACK_MM)
        c90 = frames.robot_corners(1000, 0, 90)
        self.assertAlmostEqual(c90[0][1], frames.ROBOT_FRONT_MM)
        self.assertAlmostEqual(c90[0][0], 1000 - frames.ROBOT_HALF_WIDTH_MM)

    def test_memes_valeurs_que_frames_js(self):
        import re
        js = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "Base", "Web", "static", "js", "frames.js"), encoding="utf-8").read()
        m = re.search(r"FRONT_MM: ([\d.]+), BACK_MM: ([\d.]+), HALF_WIDTH_MM: ([\d.]+), HEIGHT_MM: ([\d.]+)", js)
        self.assertEqual(tuple(map(float, m.groups())), (frames.ROBOT_FRONT_MM, frames.ROBOT_BACK_MM,
                                                         frames.ROBOT_HALF_WIDTH_MM, frames.ROBOT_HEIGHT_MM))

