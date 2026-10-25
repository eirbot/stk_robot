"""Temps de match (Rasp/core/temps_match.py)."""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import temps_match as tm  # noqa: E402


class TestTemps(unittest.TestCase):
    def test_rotations_goto(self):
        d, r = tm.rotations_goto((0, 0, 0), (0, 1000, 0))
        self.assertAlmostEqual(d, 1000)
        self.assertAlmostEqual(r, 180)                    # 90° pour viser, 90° pour revenir à 0
        self.assertEqual(tm.rotations_goto((5, 5, 10), (5, 5, -80)), (0.0, 90.0))

    def test_duree_chemin(self):
        m = {"v_mm_s": 500, "w_deg_s": 90, "t0_s": 0}
        t = tm.duree_chemin((0, 0, 0), [(1000, 0), (1000, 1000)], 90, m)
        # 1000 mm (2 s) + 90° (1 s) puis 1000 mm (2 s), cap final déjà bon
        self.assertAlmostEqual(t, 5.0)

    def test_ajuster(self):
        vrai = {"v_mm_s": 420.0, "w_deg_s": 150.0, "t0_s": 0.6}
        rnd = random.Random(2)
        ech = []
        for _ in range(40):
            d, r = rnd.uniform(0, 1500), rnd.uniform(0, 270)
            ech.append((d, r, tm.duree_goto(d, r, vrai) + rnd.gauss(0, 0.05)))
        m = tm.ajuster(ech)
        self.assertAlmostEqual(m["v_mm_s"], 420, delta=20)
        self.assertAlmostEqual(m["w_deg_s"], 150, delta=10)
        self.assertAlmostEqual(m["t0_s"], 0.6, delta=0.1)

    def test_ajuster_peu_de_donnees(self):
        self.assertEqual(tm.ajuster([(100, 0, 1.0)]), tm.DEFAUTS)
        # données incohérentes (durée qui baisse avec la distance) : défauts
        self.assertEqual(tm.ajuster([(d, 0, 10 - d / 200) for d in range(100, 1100, 100)]), tm.DEFAUTS)

    def test_decision(self):
        self.assertEqual(tm.temps_restant(1000.0, 1030.0), 70.0)
        self.assertEqual(tm.temps_restant(None, 5.0), 100.0)
        self.assertTrue(tm.doit_rentrer(8.0, 6.0, 3.0))
        self.assertFalse(tm.doit_rentrer(10.0, 6.0, 3.0))
        self.assertTrue(tm.assez_de_temps(30.0, 10.0, 8.0, 3.0))
        self.assertFalse(tm.assez_de_temps(20.0, 10.0, 8.0, 3.0))


if __name__ == "__main__":
    unittest.main()
