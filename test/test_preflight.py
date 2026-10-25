"""Tests de la check-list avant match (Rasp/core/preflight.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import preflight  # noqa: E402
from core.preflight import ERR, OK, WARN  # noqa: E402

PRET = {
    "esp_moteurs": True, "esp_moteurs_age_s": 0.05, "esp_actionneurs": True,
    "lidar_mode": "MATCH", "lidar_age_s": 0.1, "camera_zen_age_s": 0.2, "tension_v": 22.1,
    "strategie": "3b_pouss_plus", "strategie_existe": True, "equipe": "BLEUE", "tirette": "ARMED",
    "depart": (148.0, 1149.0, 0.0), "pose_camera": (150.0, 1140.0, 1.5),
    "camera_embarquee": True, "camera_embarquee_ok": True, "temp_cpu": 55.0,
}


def niveaux(e):
    return {i["id"]: i["niveau"] for i in preflight.evaluer(e)}


class TestPreflight(unittest.TestCase):
    def test_tout_pret(self):
        items = preflight.evaluer(PRET)
        self.assertTrue(preflight.pret(items))
        self.assertEqual({i["niveau"] for i in items}, {OK})

    def test_esp_muet(self):
        n = niveaux({**PRET, "esp_moteurs_age_s": None})
        self.assertEqual(n["esp_moteurs"], ERR)
        self.assertFalse(preflight.pret(preflight.evaluer({**PRET, "esp_moteurs": False})))

    def test_lidar(self):
        self.assertEqual(niveaux({**PRET, "lidar_mode": "OFF"})["lidar"], ERR)
        self.assertEqual(niveaux({**PRET, "lidar_age_s": 5.0})["lidar"], ERR)
        self.assertEqual(niveaux({**PRET, "lidar_mode": "HOMOLOGATION"})["lidar"], WARN)

    def test_batterie(self):
        self.assertEqual(niveaux({**PRET, "tension_v": 17.5})["batterie"], ERR)
        self.assertEqual(niveaux({**PRET, "tension_v": 19.0})["batterie"], WARN)
        self.assertEqual(niveaux({**PRET, "tension_v": 0.0})["batterie"], WARN)

    def test_strategie(self):
        self.assertEqual(niveaux({**PRET, "strategie": None})["strategie"], ERR)
        self.assertEqual(niveaux({**PRET, "strategie_existe": False})["strategie"], ERR)

    def test_depart_mal_place(self):
        self.assertEqual(niveaux({**PRET, "pose_camera": (300.0, 1149.0, 0.0)})["depart"], WARN)
        self.assertEqual(niveaux({**PRET, "pose_camera": (148.0, 1149.0, 30.0)})["depart"], WARN)
        # sans caméra récente : pas de verdict sur le départ
        self.assertNotIn("depart", niveaux({**PRET, "camera_zen_age_s": 10.0}))

    def test_tirette(self):
        self.assertEqual(niveaux({**PRET, "tirette": "WAIT"})["tirette"], ERR)
        self.assertEqual(niveaux({**PRET, "tirette": "WAIT_INSERT"})["tirette"], WARN)
        self.assertEqual(niveaux({**PRET, "tirette": "TRIGGERED", "match_running": True})["tirette"], OK)

    def test_avertissements(self):
        n = niveaux({**PRET, "test_mode": True, "camera_embarquee_ok": False, "temp_cpu": 80.0,
                     "camera_zen_age_s": None})
        self.assertEqual((n["test_mode"], n["camera_emb"], n["temp_cpu"], n["camera_zen"]), (WARN,) * 4)
        self.assertTrue(preflight.pret(preflight.evaluer({**PRET, "test_mode": True})))

    def test_depart_strategie(self):
        src = 'def run(robot):\n    robot.set_pos(148, -1149.5, 90)\n    robot.goto(1, 2, 3)\n    robot.set_pos(0, 0, 0)\n'
        self.assertEqual(preflight.depart_strategie(src), (148.0, -1149.5, 90.0))
        self.assertIsNone(preflight.depart_strategie("robot.goto(1, 2, 3)"))


if __name__ == "__main__":
    unittest.main()
