"""Suivi / prédiction des robots adverses (Rasp/core/suivi_adversaire.py)."""
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import suivi_adversaire as sa  # noqa: E402


class TestPiste(unittest.TestCase):
    def suivre(self, vx, vy, n=30, dt=0.05, bruit=10.0, seed=1):
        rnd = random.Random(seed)
        p = sa.PisteAdversaire(5, 1000.0, -500.0, 0.0)
        for k in range(1, n + 1):
            t = k * dt
            p.observer(1000.0 + vx * t + rnd.gauss(0, bruit), -500.0 + vy * t + rnd.gauss(0, bruit), t)
        return p, n * dt

    def test_vitesse_estimee(self):
        p, _ = self.suivre(0.0, 600.0)
        vx, vy = p.vitesse
        self.assertAlmostEqual(vx, 0.0, delta=80)
        self.assertAlmostEqual(vy, 600.0, delta=80)

    def test_prediction(self):
        p, t = self.suivre(0.0, 600.0)
        x, y, s = p.position(t + 0.5)
        attendu = -500.0 + 600.0 * t + 600.0 * sa.AMORTISSEMENT_S * (1 - math.exp(-0.5 / sa.AMORTISSEMENT_S))
        self.assertAlmostEqual(x, 1000.0, delta=40)
        self.assertAlmostEqual(y, attendu, delta=60)
        # l'incertitude grandit avec l'horizon, et la prédiction ralentit (vitesse amortie)
        _, y1, s1 = p.position(t + 1.0)
        _, y3, s3 = p.position(t + 3.0)
        self.assertLess(s, s1)
        self.assertLessEqual(s1, s3)
        self.assertLess(y3 - y1, 2 * 600.0)

    def test_immobile(self):
        p, t = self.suivre(0.0, 0.0)
        x, y, s = p.position(t + 2.0)
        self.assertAlmostEqual(x, 1000.0, delta=30)
        self.assertAlmostEqual(y, -500.0, delta=30)
        self.assertLessEqual(s, sa.SIGMA_MAX_MM)
        self.assertLess(p.position(t + 0.5)[2], 80)

    def test_vitesse_plafonnee(self):
        p = sa.PisteAdversaire(5, 0.0, 0.0, 0.0)
        p.observer(500.0, 0.0, 0.05)     # saut aberrant : 10 m/s
        self.assertLessEqual(math.hypot(*p.vitesse), sa.VITESSE_MAX_MM_S + 1e-6)

    def test_trajectoire(self):
        p, t = self.suivre(300.0, 0.0)
        tr = p.trajectoire(t, horizon_s=1.0, pas_s=0.25)
        self.assertEqual([e[0] for e in tr], [0.0, 0.25, 0.5, 0.75, 1.0])
        self.assertTrue(all(b[1] > a[1] for a, b in zip(tr, tr[1:])))


class TestSuivi(unittest.TestCase):
    def test_pistes(self):
        s = sa.SuiviAdversaires()
        s.observer(5, 100, 100, 0.0)
        s.observer(5, 110, 100, 0.1)
        s.observer(7, 900, 900, 0.1)
        self.assertEqual(len(s.actives(0.2)), 2)
        self.assertEqual(s.pistes[5].n_obs, 2)
        self.assertEqual(len(s.actives(10.0)), 0)       # perdus
        s.observer(5, 0, 0, 20.0)                        # nouvelle piste
        self.assertEqual(s.pistes[5].n_obs, 1)


if __name__ == "__main__":
    unittest.main()
