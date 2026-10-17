"""Tests des repères (Rasp/core/frames.py). Lancer : python3 -m unittest discover -s test"""
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
