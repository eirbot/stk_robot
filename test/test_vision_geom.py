"""Tests de la géométrie caméra embarquée (Rasp/core/vision_geom.py). Pur Python.
Lancer : python3 -m unittest discover -s test"""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import vision_geom as vg  # noqa: E402
from core.frames import normalize_deg  # noqa: E402

TAILLE = 50.0


def camera(dist=(0.0, 0.0, 0.0, 0.0, 0.0), **montage):
    intr = vg.Intrinseques(1360.0, 1355.0, 815.0, 620.0, 1640, 1232, dist)
    m = {"x": 150.0, "y": 10.0, "z": 120.0, "lacet": 0.0, "tangage": 5.0, "roulis": 0.0, **montage}
    return vg.Camera(intr, **m)


class TestCamera(unittest.TestCase):
    def test_axe_optique(self):
        # Caméra droite (sans tangage) : un point devant elle tombe au centre optique
        cam = camera(tangage=0.0)
        u, v = cam.projeter([1000.0, 10.0, 120.0])
        self.assertAlmostEqual(u, 815.0)
        self.assertAlmostEqual(v, 620.0)

    def test_gauche_et_haut(self):
        cam = camera(tangage=0.0)
        u, _ = cam.projeter([1000.0, 200.0, 120.0])     # à gauche du robot -> à gauche de l'image
        _, v = cam.projeter([1000.0, 10.0, 400.0])      # plus haut -> plus haut dans l'image
        self.assertLess(u, 815.0)
        self.assertLess(v, 620.0)

    def test_derriere(self):
        self.assertIsNone(camera().projeter([0.0, 0.0, 120.0]))

    def test_pixel_au_sol_aller_retour(self):
        cam = camera(tangage=30.0, lacet=10.0, roulis=2.0, dist=(-0.25, 0.08, 0.001, -0.0005, 0.0))
        for p in ([400.0, 50.0, 0.0], [600.0, -150.0, 0.0], [350.0, 120.0, 55.0]):
            u, v = cam.projeter(p)
            q = cam.pixel_au_sol(u, v, z=p[2])
            for a, b in zip(p, q):
                self.assertAlmostEqual(a, b, places=3)

    def test_distorsion_inverse(self):
        intr = vg.Intrinseques(1360.0, 1355.0, 815.0, 620.0, 1640, 1232, (-0.3, 0.1, 0.001, 0.002, -0.01))
        for x, y in ((0.0, 0.0), (0.3, -0.2), (-0.5, 0.35)):
            u, v = intr.projeter_normalise(x, y)
            xn, yn = intr.normaliser(u, v)
            self.assertAlmostEqual(x, xn, places=6)
            self.assertAlmostEqual(y, yn, places=6)

    def test_pour_resolution(self):
        intr = vg.Intrinseques(1360.0, 1360.0, 819.5, 615.5, 1640, 1232)
        demi = intr.pour_resolution(820, 616)
        self.assertAlmostEqual(demi.fx, 680.0)
        self.assertAlmostEqual(demi.cx, 409.5)
        self.assertIs(intr.pour_resolution(1640, 1232), intr)

    def test_depuis_config(self):
        cfg = {"intrinseques": {"resolution": [1640, 1232], "fx": 1300, "fy": 1302, "cx": 800, "cy": 600,
                                "dist": [-0.2, 0.05]},
               "montage": {"x": 100, "z": 250, "tangage": 15}}
        cam = vg.Camera.depuis_config(cfg, 820, 616)
        self.assertAlmostEqual(cam.intr.fx, 650.0)
        self.assertEqual(cam.intr.dist, (-0.2, 0.05, 0.0, 0.0, 0.0))
        self.assertEqual(cam.position, [100.0, 0.0, 250.0])
        self.assertTrue(cam.calibree)
        nominale = vg.Camera.depuis_config({}, 1640, 1232)
        self.assertFalse(nominale.calibree)
        self.assertAlmostEqual(nominale.intr.fx, 820 / math.tan(math.radians(31.1)), places=6)


class TestPoseTag(unittest.TestCase):
    def assertPose(self, pose, x, y, z, cap, tol_mm=0.5, tol_deg=0.1):
        self.assertIsNotNone(pose)
        self.assertAlmostEqual(pose.x, x, delta=tol_mm)
        self.assertAlmostEqual(pose.y, y, delta=tol_mm)
        self.assertAlmostEqual(pose.z, z, delta=tol_mm)
        self.assertAlmostEqual(normalize_deg(pose.cap - cap), 0.0, delta=tol_deg)

    def test_vertical_exact(self):
        cam = camera(dist=(-0.2, 0.05, 0.0, 0.0, 0.0))
        for x, y, z, cap in ((400, 0, 55, 180), (600, 120, 55, 150), (500, -90, 165, -160), (900, 40, 100, 200)):
            coins = vg.projeter_tag(cam, x, y, z, cap, TAILLE)
            for zz in (None, z, [55, 165, 275] if z in (55, 165) else z):
                with self.subTest(x=x, y=y, cap=cap, z=zz):
                    pose = vg.estimer_pose(cam, coins, TAILLE, "vertical", z=zz)
                    self.assertPose(pose, x, y, z, cap)
                    self.assertLess(pose.err_px, 0.01)

    def test_vertical_tag_tourne_dans_son_plan(self):
        cam = camera()
        for quart in range(4):
            coins = vg.projeter_tag(cam, 500, 30, 55, 170, TAILLE, quart=quart)
            pose = vg.estimer_pose(cam, coins, TAILLE, "vertical")
            self.assertPose(pose, 500, 30, 55, 170)
            self.assertEqual(pose.quart, quart)

    def test_horizontal(self):
        cam = camera(z=300.0, tangage=45.0)
        for x, y, cap in ((400, 0, 0), (450, 60, 90), (380, -50, -135)):
            coins = vg.projeter_tag(cam, x, y, 30, cap, TAILLE, orientation="horizontal")
            for zz in (30, None):
                with self.subTest(x=x, y=y, cap=cap, z=zz):
                    self.assertPose(vg.estimer_pose(cam, coins, TAILLE, "horizontal", z=zz), x, y, 30, cap)

    def test_bruit(self):
        """Coins bruités (0,5 px) : à 50 cm, < 5 mm et < 3° sur une image ; le signe de l'angle ne s'inverse pas."""
        cam = camera()
        rnd = random.Random(3)
        for cap in (165, 175, 185, 195):
            coins = vg.projeter_tag(cam, 500, 20, 55, cap, TAILLE)
            for _ in range(15):
                bruit = [(u + rnd.gauss(0, 0.5), v + rnd.gauss(0, 0.5)) for u, v in coins]
                pose = vg.estimer_pose(cam, bruit, TAILLE, "vertical", z=55)
                self.assertPose(pose, 500, 20, 55, cap, tol_mm=5, tol_deg=3)

    def test_coins_incoherents(self):
        cam = camera()
        coins = vg.projeter_tag(cam, 500, 0, 55, 180, TAILLE)
        coins[2] = (coins[2][0] + 25, coins[2][1] - 20)
        pose = vg.estimer_pose(cam, coins, TAILLE, "vertical")
        self.assertGreater(pose.err_px, 3.0)

    def test_orientation_inconnue(self):
        with self.assertRaises(ValueError):
            vg.estimer_pose(camera(), [(0, 0)] * 4, TAILLE, "oblique")


class TestUtilitaires(unittest.TestCase):
    def pose(self, **k):
        d = dict(id=13, x=500.0, y=40.0, z=55.0, cap=170.0, orientation="vertical", taille_mm=TAILLE, err_px=0.1)
        d.update(k)
        return vg.PoseTag(**d)

    def test_ecart_angle(self):
        self.assertAlmostEqual(self.pose(cap=180.0).ecart_angle, 0.0)
        self.assertAlmostEqual(self.pose(cap=170.0).ecart_angle, -10.0)

    def test_point_devant(self):
        x, y, cap = self.pose(x=500.0, y=0.0, cap=180.0).point_devant(200)
        self.assertAlmostEqual(x, 300.0)
        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(cap, 0.0)

    def test_vers_table(self):
        x, y, cap = self.pose(x=500.0, y=0.0, cap=180.0).vers_table(1000.0, 200.0, 90.0)
        self.assertAlmostEqual(x, 1000.0)
        self.assertAlmostEqual(y, 700.0)
        self.assertAlmostEqual(cap, -90.0)

    def test_distance(self):
        self.assertAlmostEqual(self.pose(x=300.0, y=400.0).distance, 500.0)


if __name__ == "__main__":
    unittest.main()
