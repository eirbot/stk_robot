"""aller() (planificateur) et retour de fin de match, dans le robot simulé (tools/robot_sim.py).
Un sous-processus : les faux modules du simulateur ne doivent pas polluer les autres tests."""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

SCRIPT = r'''
import json, os, sys, time
sys.path.insert(0, os.path.join(ROOT, "tools"))
import robot_sim
robot_sim.FakeESPMotors.speed_mm_s = 0
os.environ["ROBOT_CONFIG"] = robot_sim.prepare_config("127.0.0.1")
os.environ.setdefault("ROBOT_TELEMETRY_DIR", os.path.dirname(os.environ["ROBOT_CONFIG"]))
robot_sim.install_fakes()
sys.path.insert(0, robot_sim.RASP); os.chdir(robot_sim.RASP)
import hardware, ihm.shared as shared, strat.actions as actions
actions.DUREES_PATH = os.path.join(os.environ["ROBOT_TELEMETRY_DIR"], "durees.jsonl")
hardware.start(shared.cfg)
shared.match.ready(tirette_inserted=False); shared.match.apply_config({"team": TEAM}); shared.match.start()
r = actions.RobotActions()
out = {}
r.set_pos(1000, -1200, 90)
shared.noter_adversaire(5, 1000, 0 if TEAM == "BLEUE" else 0, time.time())
out["aller"] = r.aller(1000, 1200, 90)
out["gotos"] = [c[1:] for c in hardware.esp.calls if c[0] == "goto"]
out["pose"] = [shared.robot_pos[k] for k in ("x", "y", "theta")]
r.retour_fin(300, -1200, 0, marge_s=3)
shared.state["start_time"] = time.time() - 95
try:
    r.goto(1500, 500, 0)
    out["retour_fin"] = False
except actions.RetourFin:
    out["retour_fin"] = True
out["si_temps"] = r.si_temps(3)
r.executer_retour()
out["pose_retour"] = [shared.robot_pos[k] for k in ("x", "y", "theta")]
print(json.dumps(out))
'''


def run(team):
    code = f"ROOT = {ROOT!r}\nTEAM = {team!r}\n" + SCRIPT
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    lignes = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if not lignes:
        raise AssertionError(p.stdout[-2000:] + p.stderr[-2000:])
    return json.loads(lignes[-1])


class TestDeplacementDynamique(unittest.TestCase):
    def test_contourne_adversaire_et_rentre(self):
        for team in ("BLEUE", "JAUNE"):
            with self.subTest(equipe=team):
                r = run(team)
                self.assertTrue(r["aller"])
                sym = 1 if team == "BLEUE" else -1
                self.assertAlmostEqual(r["pose"][0], 1000, delta=1)
                self.assertAlmostEqual(r["pose"][1], 1200 * sym, delta=1)
                # au moins un point de passage pour contourner l'adversaire en (1000, 0)
                self.assertGreaterEqual(len(r["gotos"]), 2)
                self.assertTrue(any(abs(g[0] - 1000) > 300 for g in r["gotos"][:-1]))
                self.assertTrue(r["retour_fin"])
                self.assertFalse(r["si_temps"])
                self.assertAlmostEqual(r["pose_retour"][0], 300, delta=1)
                self.assertAlmostEqual(r["pose_retour"][1], -1200 * sym, delta=1)


if __name__ == "__main__":
    unittest.main()
