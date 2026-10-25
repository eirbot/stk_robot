"""Navigateur (Rasp/core/navigation.py) et planificateur de la base (Base/Planif/planif_worker.py)."""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "Rasp"))
from core.navigation import Navigateur  # noqa: E402

spec = importlib.util.spec_from_file_location("planif_worker", os.path.join(ROOT, "Base", "Planif", "planif_worker.py"))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def adversaire_qui_traverse(nav, t0=0.0, n=10):
    for k in range(n):
        nav.observer_vision({"adversaires": [{"id": 5, "x": 400 + 600 * k * 0.05, "y": 0}]}, t0 + k * 0.05)


class TestNavigateur(unittest.TestCase):
    def test_sans_navigation(self):
        nav = Navigateur()
        self.assertEqual(nav.planifier(0.0), (None, False))
        self.assertIsNone(nav.message_plan(0.0, None, False))

    def test_plan_et_message(self):
        nav = Navigateur()
        nav.observer_pose(1000, -1100, 90, 0.0)
        nav.demander(1, (1000, 1100, 90))
        plan, change = nav.planifier(0.1)
        self.assertTrue(change)
        msg = nav.message_plan(0.1, plan, change, 3.2)
        self.assertEqual(msg["id"], 1)
        self.assertTrue(msg["ok"])
        self.assertEqual(msg["points"][0], [1000, -1100])
        self.assertEqual(msg["points"][-1], [1000, 1100])

    def test_pose_trop_vieille(self):
        nav = Navigateur()
        nav.observer_pose(1000, -1100, 90, 0.0)
        nav.demander(1, (1000, 1100, 90))
        self.assertEqual(nav.planifier(5.0), (None, False))
        self.assertIsNotNone(nav.planifier(5.0, pose=(1000, -1100, 90))[0])

    def test_adversaire_et_pierres(self):
        nav = Navigateur()
        adversaire_qui_traverse(nav)
        nav.observer_vision({"pierres": [{"x": 1000, "y": 600, "theta": 0}]}, 0.5)
        nav.observer_pose(1000, -1100, 90, 0.5)
        nav.demander(1, (1000, 1100, 90))
        plan, _ = nav.planifier(0.5)
        self.assertGreater(len(plan.points), 2)
        self.assertFalse(nav.carte.libre(1000, 600))                 # la pierre est un obstacle
        carte = nav.message_carte(0.5)
        self.assertEqual(len(carte["predictions"]), 1)
        self.assertEqual(carte["pierres"], [[1000, 600, 0.0]])

    def test_pierre_cible_ignoree(self):
        nav = Navigateur({"ignorer_pres_cible_mm": 300})
        nav.observer_vision({"pierres": [{"x": 1000, "y": 900, "theta": 0}]}, 0.0)
        nav.observer_pose(1000, -1100, 90, 0.0)
        nav.demander(1, (1000, 750, 90))
        plan, _ = nav.planifier(0.0)
        self.assertEqual(len(plan.points), 2)                      # tout droit vers la pierre à prendre

    def test_hysteresis_entre_deux_calculs(self):
        nav = Navigateur()
        nav.observer_vision({"adversaires": [{"id": 5, "x": 1000, "y": 0}]}, 0.0)
        nav.observer_pose(1000, -1100, 90, 0.0)
        nav.demander(1, (1000, 1100, 90))
        p1, c1 = nav.planifier(0.0)
        nav.observer_vision({"adversaires": [{"id": 5, "x": 1003, "y": 0}]}, 0.1)
        p2, c2 = nav.planifier(0.1)
        self.assertTrue(c1)
        self.assertFalse(c2)                                       # presque rien n'a bougé : même chemin
        self.assertEqual(p1.points[1:], p2.points[1:])

    def test_terminer(self):
        nav = Navigateur()
        nav.demander(3, (1000, 0, 0))
        nav.terminer(2)
        self.assertIsNotNone(nav.nav)
        nav.terminer(3)
        self.assertIsNone(nav.nav)


class TestWorker(unittest.TestCase):
    def test_messages(self):
        nav = Navigateur()
        worker.traiter(nav, {"type": "telemetry", "data": {"x": 1000, "y": -1100, "theta": 90}}, 0.0)
        worker.traiter(nav, {"type": "lidar_frame", "data": {"points": [[1000, 0]]}}, 0.0)
        out = worker.traiter(nav, {"type": "nav_demande", "data": {"id": 7, "cible": [1000, 1100, 90]}}, 0.0)
        self.assertEqual(out, [("plan", None)])
        msgs, dp, dc = worker.tic(nav, 0.05, 0.0, -1.0, forcer=True)
        types = [k for k, _ in msgs]
        self.assertEqual(types, ["plan", "carte_planif"])
        plan = msgs[0][1]
        self.assertEqual(plan["id"], 7)
        self.assertTrue(plan["ok"])
        self.assertGreater(len(plan["points"]), 2)                 # contourne le point LiDAR
        msgs, _, _ = worker.tic(nav, 0.08, dp, dc)                  # trop tôt pour un nouveau plan
        self.assertEqual(msgs, [])
        worker.traiter(nav, {"type": "nav_fin", "data": {"id": 7}}, 0.1)
        self.assertEqual([k for k, _ in worker.tic(nav, 1.0, dp, dc)[0]], ["carte_planif"])


if __name__ == "__main__":
    unittest.main()
