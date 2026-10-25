"""Suivi de trajectoire (Rasp/core/suivi.py), sur un robot différentiel simulé."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import suivi  # noqa: E402

DT = 0.05


def simuler(chemin, pose, t_max=20.0, cfg=None, obstacle=lambda p: math.inf, latence=1):
    """Robot qui applique la commande avec un pas de retard (comme l'ESP) ; renvoie trace et commandes."""
    s = suivi.Suivi(chemin, cfg)
    x, y, th = pose
    trace, cmds = [(x, y, th)], []
    en_attente = [(0.0, 0.0)] * latence
    t = 0.0
    while t < t_max:
        c = s.commande((x, y, th), DT, obstacle((x, y, th)))
        cmds.append(c)
        en_attente.append((c.v, c.w))
        v, w = en_attente.pop(0)
        th += w * DT
        x += v * math.cos(math.radians(th)) * DT
        y += v * math.sin(math.radians(th)) * DT
        trace.append((x, y, th))
        t += DT
        if c.etat == "arrive":
            break
    return trace, cmds, t


def ecart_au_chemin(p, chemin):
    best = math.inf
    for a, b in zip(chemin, chemin[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        f = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
        best = min(best, math.hypot(p[0] - a[0] - f * dx, p[1] - a[1] - f * dy))
    return best


class TestSuivi(unittest.TestCase):
    def test_ligne_droite(self):
        chemin = [(500, -1000), (500, 1000)]
        trace, cmds, t = simuler(chemin, (500, -1000, 90))
        self.assertEqual(cmds[-1].etat, "arrive")
        self.assertLess(math.hypot(trace[-1][0] - 500, trace[-1][1] - 1000), 40)
        self.assertLess(t, 2000 / 700 + 2.0)                 # croisière + accélération / freinage
        self.assertLessEqual(max(c.v for c in cmds), 700.0 + 1e-6)

    def test_virage_en_l(self):
        chemin = [(500, -1000), (500, 0), (1500, 0)]
        trace, cmds, t = simuler(chemin, (500, -1000, 90))
        self.assertEqual(cmds[-1].etat, "arrive")
        self.assertLess(max(ecart_au_chemin(p, chemin) for p in trace), 120)   # coin arrondi
        self.assertLess(t, 8.0)

    def test_rotation_sur_place_au_depart(self):
        trace, cmds, _ = simuler([(500, 0), (1500, 0)], (500, 0, 180))
        self.assertEqual(cmds[0].etat, "rotation")
        self.assertTrue(all(abs(c.v) < 1e-6 for c in cmds[:5]))
        self.assertEqual(cmds[-1].etat, "arrive")

    def test_freine_avant_obstacle(self):
        chemin = [(500, -1000), (500, 1000)]

        def obstacle(p):          # mur à y = 0
            return max(0.0, 0.0 - p[1]) if p[1] < 0 else 0.0
        trace, cmds, _ = simuler(chemin, (500, -1000, 90), t_max=6.0, obstacle=obstacle)
        self.assertLess(max(p[1] for p in trace), -suivi.DEFAUTS["distance_arret_mm"] + 60)
        self.assertNotEqual(cmds[-1].etat, "arrive")

    def test_bloque_devant_tourne_vers_le_chemin(self):
        # obstacle juste devant, chemin qui part à 30° : le robot ne reste pas figé, il tourne
        s = suivi.Suivi([(0, 0), (1000, 577)])
        c = s.commande((0, 0, 0), DT, obstacle_devant_mm=200.0)
        self.assertEqual(c.etat, "rotation")
        self.assertEqual(c.v, 0.0)
        self.assertGreater(c.w, 0.0)

    def test_obstacle_devant(self):
        # balises : couloir de 2 x 400 mm (notre demi-largeur + corps adverse)
        self.assertAlmostEqual(suivi.obstacle_devant([(800, 0), (300, 0)], (500, 0, 0)), 300)
        self.assertAlmostEqual(suivi.obstacle_devant([(800, 350)], (500, 0, 0)), 300)     # dans le couloir
        self.assertEqual(suivi.obstacle_devant([(800, 450)], (500, 0, 0)), math.inf)      # à côté
        self.assertEqual(suivi.obstacle_devant([(800, 0)], (500, 0, 180)), math.inf)      # derrière

    def test_changer_chemin(self):
        s = suivi.Suivi([(0, 0), (1000, 0)])
        s.commande((0, 0, 0), DT)
        s.changer_chemin([(0, 0), (0, 1000)])
        self.assertEqual(s.seg, 0)
        self.assertEqual(s.commande((0, 0, 0), DT).etat, "rotation")


if __name__ == "__main__":
    unittest.main()
