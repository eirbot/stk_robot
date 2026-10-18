"""Fusion odométrie + caméra (Rasp/core/localisation.py), sans robot."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))

from core.frames import angle_diff_deg  # noqa: E402
from core.localisation import Localisation  # noqa: E402


def _close(test, a, b, tol=1e-6):
    test.assertAlmostEqual(a[0], b[0], delta=tol)
    test.assertAlmostEqual(a[1], b[1], delta=tol)
    test.assertAlmostEqual(angle_diff_deg(a[2], b[2]), 0.0, delta=tol)


class Simu:
    """Robot qui roule en carré ; l'odométrie surestime les distances de 3 % et dérive
    de 0,5° par mètre. Caméra : bruit gaussien, images en retard de `latence` s."""

    def __init__(self, loc, latence=0.3, bruit_mm=8.0, bruit_deg=1.0, seed=1):
        self.loc, self.latence = loc, latence
        self.bruit_mm, self.bruit_deg = bruit_mm, bruit_deg
        self.rng = random.Random(seed)
        self.t = 0.0
        self.vrai = [1000.0, 0.0, 0.0]
        self.odo = [1000.0, 0.0, 0.0]
        self.passe = []  # (t, vraie pose)
        self.err_max = (0.0, 0.0)
        loc.reset(tuple(self.vrai), t=0.0)
        loc.on_odom(0.0, *self.odo)

    def avance(self, distance, vitesse=500.0, dt=0.02, camera=True, tourne=0.0):
        n = max(1, int(abs(distance) / vitesse / dt))
        for i in range(n):
            self.t += dt
            d = distance / n
            th = math.radians(self.vrai[2])
            self.vrai[0] += d * math.cos(th)
            self.vrai[1] += d * math.sin(th)
            self.vrai[2] += tourne / n
            tho = math.radians(self.odo[2])
            self.odo[0] += 1.03 * d * math.cos(tho)
            self.odo[1] += 1.03 * d * math.sin(tho)
            self.odo[2] += tourne / n + 0.5 * abs(d) / 1000.0
            self.passe.append((self.t, tuple(self.vrai)))
            e = self.erreur(self.loc.on_odom(self.t, *self.odo))
            self.err_max = (max(self.err_max[0], e[0]), max(self.err_max[1], e[1]))
            if camera and i % 5 == 0:
                self.image()

    def image(self):
        t_img = self.t - self.latence
        vue = next((p for (t, p) in reversed(self.passe) if t <= t_img), None)
        if vue:
            self.loc.on_camera(self.t, vue[0] + self.rng.gauss(0, self.bruit_mm),
                               vue[1] + self.rng.gauss(0, self.bruit_mm),
                               vue[2] + self.rng.gauss(0, self.bruit_deg))

    def erreur(self, pose):
        return math.hypot(pose[0] - self.vrai[0], pose[1] - self.vrai[1]), abs(angle_diff_deg(pose[2], self.vrai[2]))

    def carres(self, n=3, camera=True):
        for _ in range(n):
            for _ in range(4):
                self.avance(800, camera=camera)
                self.avance(0.001, tourne=90.0, camera=camera)


class TestTransformations(unittest.TestCase):
    def test_reset_rattrape_l_arrondi(self):
        loc = Localisation()
        loc.reset((1234.4, -567.6, 33.4), odo_pose=(1234, -568, 33))
        _close(self, loc.on_odom(0.0, 1234, -568, 33), (1234.4, -567.6, 33.4))

    def test_aller_retour_odo_table(self):
        loc = Localisation()
        loc.reset((500.0, 200.0, 90.0), odo_pose=(480.0, 260.0, 80.0))
        p = (1500.0, -800.0, -135.0)
        _close(self, loc.to_table(*loc.to_odom(*p)), p)

    def test_correction_suit_le_robot(self):
        # Après correction, un déplacement odo est reporté tel quel (rotation comprise)
        loc = Localisation()
        loc.reset((1000.0, 0.0, 90.0), odo_pose=(1000.0, 0.0, 0.0))
        _close(self, loc.on_odom(0.0, 1100.0, 0.0, 0.0), (1000.0, 100.0, 90.0))


class TestCamera(unittest.TestCase):
    def test_mesure_aberrante_rejetee(self):
        loc = Localisation()
        loc.reset((1000.0, 0.0, 0.0), t=0.0)
        loc.on_odom(1.0, 1000.0, 0.0, 0.0)
        res = loc.on_camera(1.0, 1000.0, 600.0, 0.0)
        self.assertFalse(res["ok"])
        _close(self, loc.pose(), (1000.0, 0.0, 0.0))

    def test_gain_force_robot_immobile(self):
        loc = Localisation(lambda: {"latence_s": 0.0})
        loc.reset((1000.0, 0.0, 0.0), t=0.0)
        loc.on_odom(1.0, 1000.0, 0.0, 0.0)
        self.assertTrue(loc.on_camera(1.0, 1040.0, -30.0, 5.0, gain=1.0)["ok"])
        _close(self, loc.pose(), (1040.0, -30.0, 5.0))
        # L'ESP continue dans son repère : la correction suit
        _close(self, loc.on_odom(2.0, 1100.0, 0.0, 0.0),
               (1040.0 + 100 * math.cos(math.radians(5)), -30.0 + 100 * math.sin(math.radians(5)), 5.0))

    def test_image_trop_vieille_ignoree(self):
        loc = Localisation()
        loc.reset((1000.0, 0.0, 0.0), t=10.0)
        self.assertFalse(loc.on_camera(5.0, 1000.0, 0.0, 0.0)["ok"])

    def test_desactivable(self):
        self.assertFalse(Localisation(lambda: {"fusion": False}).enabled())


class TestFusion(unittest.TestCase):
    def test_fusion_bat_l_odometrie_seule(self):
        seule = Simu(Localisation())
        seule.carres(camera=False)
        err_odo = seule.err_max

        fus = Simu(Localisation())
        fus.carres(camera=True)
        err_fus = fus.err_max

        self.assertGreater(err_odo[0], 40)         # l'odométrie seule dérive franchement
        self.assertGreater(err_odo[1], 4)
        self.assertLess(err_fus[0], 25)            # la fusion reste près de la vérité
        self.assertLess(err_fus[1], 2)
        self.assertGreater(fus.loc.stats["acceptees"], 100)

    def test_latence_compensee(self):
        # Images en retard de 0,6 s à 500 mm/s : sans compensation, chaque image
        # tire le robot 300 mm en arrière
        avec = Simu(Localisation(lambda: {"latence_s": 0.6}), latence=0.6)
        avec.avance(1500, vitesse=500)
        sans = Simu(Localisation(lambda: {"latence_s": 0.0}), latence=0.6)
        sans.avance(1500, vitesse=500)
        self.assertLess(avec.err_max[0], 30)
        self.assertGreater(sans.err_max[0], 1.5 * avec.err_max[0])


if __name__ == "__main__":
    unittest.main()
