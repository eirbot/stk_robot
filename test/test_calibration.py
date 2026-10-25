"""Calibration automatique : séquence de mouvements et résumé (Rasp/strat/calibration.py)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import frames  # noqa: E402
from strat import calibration  # noqa: E402


class TestSequence(unittest.TestCase):
    def gotos(self, etapes):
        return [a[1:] for _, a in etapes if a[0] == "goto"]

    def test_reste_sur_la_table(self):
        for pose in ((1000, 0, 0), (150, 1400, 90), (1900, -1450, -45)):
            for x, y, _ in self.gotos(calibration.sequence(pose, 500)):
                self.assertTrue(frames.in_table(x, y, calibration.MARGE_BORD_MM - 1e-6), (pose, x, y))

    def test_contenu(self):
        etapes = calibration.sequence((1000, 0, 0), 500)
        noms = {n for n, _ in etapes}
        self.assertTrue({"Carré 1/2", "Carré 2/2", "Rotations +", "Rotations -", "Lignes droites"} <= noms)
        caps = [g[2] for n, (k, *g) in etapes if k == "goto" and n.startswith("Rotations")]
        self.assertEqual(len(caps), 8)
        pauses = [a for _, a in etapes if a[0] == "pause"]
        self.assertGreaterEqual(len(pauses), 15)
        # carré : côtés de 500 mm
        g = self.gotos(etapes)[1:5]
        for a, b in zip(g, g[1:]):
            self.assertAlmostEqual(math.hypot(b[0] - a[0], b[1] - a[1]), 500, places=6)

    def test_trop_grand(self):
        with self.assertRaises(ValueError):
            calibration.sequence((1000, 0, 0), 1500)

    def test_resume(self):
        rapport = {"images": 900, "trames_odo": 5000, "latence_s": 0.21, "bruit_camera": (6.0, 0.4),
                   "derive": {"echelle_distance": 0.98, "echelle_rotation": 1.01},
                   "rejeu_actuel": {"acceptees": 800, "rejetees": 100, "taux_rejet": 0.11, "nis_moyen": 9.0},
                   "rejeu_propose": {"acceptees": 880, "rejetees": 20, "taux_rejet": 0.02, "nis_moyen": 3.1}}
        r = calibration.resume({"latence_s": 0.21}, rapport)
        self.assertAlmostEqual(r["erreur_distance_pct"], 2.04, places=2)
        self.assertAlmostEqual(r["facteur_entraxe"], round(0.98 / 1.01, 4))
        self.assertEqual(r["rejeu_propose"]["acceptees"], 880)
        self.assertEqual(r["bruit_camera"], [6.0, 0.4])


if __name__ == "__main__":
    unittest.main()
