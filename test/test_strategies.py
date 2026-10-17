"""Chaque stratégie de Rasp/strat/strategies est exécutée dans un robot simulé, pour les deux
équipes (tools/check_strategy.py, un processus par exécution) :
- elle va au bout sans erreur ;
- toutes les poses envoyées à l'ESP sont sur la table ;
- la trajectoire JAUNE est exactement la symétrique de la BLEUE.
"""
import glob
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "Rasp"))
from core import frames  # noqa: E402

STRATEGIES = sorted(os.path.basename(p)[:-3]
                    for p in glob.glob(os.path.join(ROOT, "Rasp", "strat", "strategies", "*.py"))
                    if not p.endswith("__init__.py") and not os.path.basename(p).startswith("test_"))


def run(name, team):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_strategy.py"), name,
                        "--team", team, "--json"], capture_output=True, text=True, timeout=120)
    lines = [line for line in p.stdout.splitlines() if line.startswith("{")]
    if not lines:
        raise AssertionError(f"{name} ({team}) : pas de résultat\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    return json.loads(lines[-1])


class TestStrategies(unittest.TestCase):
    def test_strategies(self):
        self.assertTrue(STRATEGIES, "aucune stratégie trouvée")
        for name in STRATEGIES:
            with self.subTest(strategie=name):
                bleue, jaune = run(name, "BLEUE"), run(name, "JAUNE")
                for res in (bleue, jaune):
                    self.assertIsNone(res["error"], f"{name} ({res['team']}) : {res['error']}")
                    self.assertEqual(res["out_of_table"], [], f"{name} ({res['team']}) sort de la table")
                self.assertEqual(len(bleue["poses"]), len(jaune["poses"]))
                for b, j in zip(bleue["poses"], jaune["poses"]):
                    mx, my, mt = frames.mirror_for_team(b[1], b[2], b[3], "JAUNE")
                    self.assertEqual(b[0], j[0])
                    self.assertAlmostEqual(mx, j[1], places=2)
                    self.assertAlmostEqual(my, j[2], places=2)
                    self.assertAlmostEqual(frames.angle_diff_deg(mt, j[3]), 0, places=2)


if __name__ == "__main__":
    unittest.main()
