"""Planification de trajectoire (Rasp/core/planif.py)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import planif  # noqa: E402
from core.planif import INF  # noqa: E402
from core import suivi_adversaire as sa  # noqa: E402


def dist_segment(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


class TestCarte(unittest.TestCase):
    def test_bords_interdits(self):
        c = planif.Carte()
        self.assertFalse(c.libre(100, 0))         # à moins du rayon du robot du bord X = 0
        self.assertFalse(c.libre(1000, 1400))
        self.assertTrue(c.libre(1000, 0))
        self.assertFalse(c.libre(-10, 0))         # hors table

    def test_disque_et_surcout(self):
        c = planif.Carte()
        c.ajouter_disque(1000, 0, 100)
        self.assertEqual(c.cout_xy(1000, 0), INF)
        self.assertEqual(c.cout_xy(1000, 280), INF)       # 100 + 215 > 280 (au centre de cellule près)
        self.assertGreater(c.cout_xy(1000, 400), 1.0)     # zone de surcoût
        self.assertEqual(c.cout_xy(1000, 900), 1.0)

    def test_rect(self):
        c = planif.Carte({"obstacles": [{"rect": [800, -200, 1200, 200]}]})
        self.assertEqual(c.cout_xy(1000, 0), INF)
        self.assertEqual(c.cout_xy(1000, 400), INF)       # 200 + 215
        self.assertTrue(c.libre(1000, 500))

    def test_resume(self):
        g = planif.Carte({"res_mm": 25}).resume(100)   # blocs de 4 cellules = 100 mm
        self.assertEqual(len(g), 20)
        self.assertEqual(g[0][5], 9)
        self.assertEqual(g[10][15], 0)


class TestPlanifier(unittest.TestCase):
    def test_ligne_droite_si_libre(self):
        p = planif.planifier(planif.Carte(), (500, -1000), (1500, 1000))
        self.assertEqual(p.points, [(500, -1000), (1500, 1000)])
        self.assertAlmostEqual(p.longueur, math.hypot(1000, 2000))

    def test_contourne_un_obstacle(self):
        c = planif.Carte({"obstacles": [{"cercle": [1000, 0, 150]}]})
        p = planif.planifier(c, (1000, -1000), (1000, 1000))
        self.assertGreater(len(p.points), 2)
        self.assertTrue(planif.chemin_libre(c, p.points))
        for a, b in zip(p.points, p.points[1:]):
            self.assertGreater(dist_segment((1000, 0), a, b), 150 + 215 - 30)
        self.assertLess(p.longueur, 2000 * 1.35)

    def test_mur_infranchissable(self):
        c = planif.Carte({"obstacles": [{"rect": [0, -10, 2000, 10]}]})
        self.assertIsNone(planif.planifier(c, (1000, -1000), (1000, 1000)))

    def test_passage_etroit(self):
        # Mur avec une porte de 500 mm : le robot (2 x 215) passe, en frôlant
        c = planif.Carte({"obstacles": [{"rect": [0, -10, 750, 10]}, {"rect": [1250, -10, 2000, 10]}]})
        p = planif.planifier(c, (1000, -1000), (1000, 1000))
        self.assertIsNotNone(p)
        self.assertTrue(planif.chemin_libre(c, p.points))

    def test_arrivee_interdite_deplacee(self):
        c = planif.Carte()
        c.ajouter_disque(1000, 1000, 20)
        p = planif.planifier(c, (1000, -1000), (1000, 1000))
        self.assertIsNone(p)                              # 235 mm à l'intérieur > tolérance
        c2 = planif.Carte({"tolerance_arrivee_mm": 300})
        c2.ajouter_disque(1000, 1000, 20)
        p2 = planif.planifier(c2, (1000, -1000), (1000, 1000))
        self.assertTrue(p2.arrivee_deplacee)
        self.assertTrue(c2.libre(*p2.points[-1]))

    def test_depart_colle(self):
        c = planif.Carte()
        c.ajouter_disque(1000, 0, 50)
        p = planif.planifier(c, (1000, 200), (1000, 1000))   # départ dans la zone interdite
        self.assertIsNotNone(p)
        self.assertEqual(p.points[0], (1000, 200))

    def test_evite_adversaire_et_prediction(self):
        c = planif.Carte()
        c.ajouter_adversaire(1000, 0, 0.0, 500.0)           # avance vers Y+ à 0,5 m/s
        self.assertEqual(c.cout_xy(1000, 400), INF)          # position prédite à +0,8 s
        p = planif.planifier(c, (1000, -1000), (1000, 1200))
        self.assertTrue(planif.chemin_libre(c, p.points))

    def test_chaleur(self):
        ch = planif.Chaleur(demi_vie_s=2.0)
        for k in range(5):
            ch.observer(1000, 0, k * 0.1)
        self.assertGreater(ch.valeur(1000, 0, 0.5), 0.9)
        self.assertLess(ch.valeur(1000, 0, 15.0), 0.05)
        self.assertLess(ch.valeur(1000, 600, 0.5), 0.01)
        c = planif.Carte()
        c.ajouter_chaleur(ch, 0.5)
        self.assertGreater(c.cout_xy(1000, 0), 2.5)
        self.assertEqual(c.cout_xy(1000, 800), 1.0)

    def test_caps(self):
        p = planif.Plan([(0, 0), (0, 100), (100, 100)], 200, 0)
        self.assertEqual(p.caps(45.0), [0.0, 45.0])

    def test_construire(self):
        c = planif.construire({}, adversaires=[(1000, 0, 0, 0)], points_lidar=[(500, 500)])
        self.assertFalse(c.libre(1000, 0))
        self.assertFalse(c.libre(500, 500))


def piste(x, y, vx, vy, n=10, dt=0.05):
    p = sa.PisteAdversaire(5, x, y, 0.0)
    for k in range(1, n + 1):
        p.observer(x + vx * k * dt, y + vy * k * dt, k * dt)
    return p, n * dt


class TestPierres(unittest.TestCase):
    def test_rect_oriente(self):
        c = planif.Carte()
        c.ajouter_rect_oriente(1000, 0, 320, 110, 90)        # axe long le long de Y
        self.assertEqual(c.cout_xy(1000, 150), INF)           # dans la boîte (demi-longueur 160)
        self.assertEqual(c.cout_xy(1000, 160 + 180), INF)     # + rayon du robot (215)
        self.assertTrue(c.libre(1000, 160 + 260))
        self.assertTrue(c.libre(1000 + 55 + 260, 0))

    def test_pierres_ignorees_pres_cible_et_sur_robot(self):
        cfg = {"ignorer_pres_cible_mm": 300}
        c = planif.construire(cfg, pierres=[(1000, 500, 0), (1000, -500, 0)], cible=(1000, 700))
        self.assertTrue(c.libre(1000, 500))                   # la pierre qu'on va prendre
        self.assertFalse(c.libre(1000, -500))
        c2 = planif.construire({}, points_lidar=[(1000, 100), (500, 500)], robot=(1000, 0))
        self.assertTrue(c2.libre(1000, 100))                  # point LiDAR sur le robot lui-même
        self.assertFalse(c2.libre(500, 500))


class TestTemps(unittest.TestCase):
    def test_sans_adversaire_ligne_droite(self):
        p = planif.planifier_temps(planif.Carte(), (500, -1000, 0), (500, 1000), None, 90)
        self.assertEqual(p.points, [(500, -1000), (500, 1000)])
        v, w = planif.DEFAUTS["v_nominale_mm_s"], planif.DEFAUTS["w_nominale_deg_s"]
        self.assertAlmostEqual(p.duree, 90 / w + 2000 / v)    # rotation vers Y+ puis ligne

    def test_dynamique_evaluer(self):
        p, t = piste(1000, 0, 0, 0)
        dyn = planif.Dynamique([p], t)
        self.assertTrue(dyn.evaluer(1000, 300, 0.5)[0])
        interdit, sur = dyn.evaluer(1000, 800, 0.5)
        self.assertFalse(interdit)
        self.assertGreater(sur, 0)
        self.assertTrue(dyn.evaluer(1000, 300, 10.0)[0])          # au-delà de l'horizon : toujours là
        self.assertEqual(dyn.evaluer(1000, 800, 10.0), (False, 0.0))  # mais plus de surcoût

    def test_passe_derriere_un_adversaire_qui_traverse(self):
        # adversaire qui traverse vers X+ ; le robot monte vers Y+ et doit passer derrière (X plus petit)
        p, t = piste(400, 0, 600, 0)
        c = planif.Carte()
        plan = planif.planifier_temps(c, (1000, -1100, 90), (1000, 1100), planif.Dynamique([p], t, c.cfg), 90)
        self.assertIsNotNone(plan)
        croisement = [x for (x, y) in plan.points if abs(y) < 600]
        self.assertTrue(croisement and min(croisement) < 950, plan.points)
        # jamais dans la zone de l'adversaire (sur l'horizon de prédiction)
        self.assertGreater(planif.Dynamique([p], t, c.cfg).marge_min(plan.points, plan.temps), 0)

    def test_adversaire_arrete_contourne(self):
        p, t = piste(1000, 0, 0, 0)
        c = planif.Carte()
        plan = planif.planifier_temps(c, (1000, -1100, 90), (1000, 1100), planif.Dynamique([p], t, c.cfg), 90)
        self.assertGreater(len(plan.points), 2)
        self.assertGreater(planif.Dynamique([p], t, c.cfg).marge_min(plan.points, plan.temps), 0)

    def test_hysteresis(self):
        c = planif.Carte()
        ancien = planif.planifier_temps(c, (500, -1000, 90), (500, 1000), None, 90)
        nouveau = planif.PlanTemps([(500, -800), (520, 1000)], [0, 2.6], ancien.duree * 0.95, 1800)
        plan, change = planif.choisir_plan(ancien, nouveau, c, None, (500, -800, 90), 90)
        self.assertFalse(change)                                   # gain < 15 % : on garde l'ancien
        self.assertEqual(plan.points[0], (500, -800))
        plus_court = planif.PlanTemps([(500, -800), (500, 1000)], [0, 1.0], 1.0, 1800)
        self.assertTrue(planif.choisir_plan(ancien, plus_court, c, None, (500, -800, 90), 90)[1])
        # ancien chemin bloqué par un nouvel obstacle : on change
        c.ajouter_disque(500, 300, 100)
        self.assertTrue(planif.choisir_plan(ancien, nouveau, c, None, (500, -800, 90), 90)[1])
        # robot écarté du chemin : on change
        self.assertTrue(planif.choisir_plan(ancien, nouveau, planif.Carte(), None, (900, -800, 90), 90)[1])


if __name__ == "__main__":
    unittest.main()
