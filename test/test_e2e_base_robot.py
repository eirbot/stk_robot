"""Test de bout en bout : vraie base (serveur Go compilé) + vrai code robot (tools/robot_sim.py,
faux matériel), qui dialoguent en ZMQ sur 127.0.0.1, pilotés par l'API HTTP de l'interface.

Ignoré si `go` est absent ou si les ports de test (18080/15555/15556) sont pris.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASE = os.path.join(ROOT, "Base")
# Ports dédiés : le test tourne même si une base est déjà lancée sur 8080/5555/5556
PORTS = {"STK_HTTP_PORT": "18080", "STK_ZMQ_ROBOT_PORT": "15555", "STK_ZMQ_BASE_PORT": "15556",
         "STK_ZMQ_PLANIF_PORT": "15557"}
API = "http://127.0.0.1:" + PORTS["STK_HTTP_PORT"]
STRAT_NAME = "test_e2e"
STRAT_FILE = os.path.join(ROOT, "Rasp", "strat", "strategies", STRAT_NAME + ".py")
CACHE_FILE = os.path.join(BASE, "robot_config_cache.json")


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def api(path, payload=None):
    req = urllib.request.Request(API + path, method="POST" if payload is not None else "GET",
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def wait_state(pred, timeout=8.0):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            _, last = api("/api/state")
            if pred(last):
                return last
        except OSError:
            pass
        time.sleep(0.1)
    raise AssertionError(f"état attendu non atteint, dernier état : "
                         f"{ {k: last.get(k) for k in ('fsm_state', 'team', 'robot_online', 'strat_id')} if last else None}")


@unittest.skipIf(shutil.which("go") is None, "go absent")
@unittest.skipUnless(all(port_free(int(p)) for p in PORTS.values()), "ports de test occupés")
class TestBaseRobot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="e2e_")
        cls.cache_existed = os.path.exists(CACHE_FILE)
        cls.base = cls.robot = None
        # Si setUpClass échoue plus bas, tearDownClass n'est pas appelé : sans ce nettoyage,
        # la base et le robot simulé restaient lancés et bloquaient les ports des tests suivants
        cls.addClassCleanup(cls._stop_processes)
        binary = os.path.join(cls.tmp, "base_stk")
        subprocess.run(["go", "build", "-o", binary, "."], cwd=os.path.join(BASE, "Web"), check=True)
        with open(STRAT_FILE, "w", encoding="utf-8") as f:
            f.write('METADATA = {"name": "test_e2e"}\n'
                    'def run(robot):\n'
                    '    robot.set_pos(150, 1150, 0)\n'
                    '    robot.goto(700, 1250, 90)\n')
        env = dict(os.environ, STK_NO_VISION="1", STK_NO_PLANIF="1", **PORTS)
        cls.base = subprocess.Popen([binary], cwd=BASE, env=env,
                                    stdout=open(os.path.join(cls.tmp, "base.log"), "w"), stderr=subprocess.STDOUT)
        cls.robot = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "robot_sim.py"),
                                      "--server", "127.0.0.1", "--speed", "100000"],
                                     env=dict(os.environ, **PORTS),
                                     stdout=open(os.path.join(cls.tmp, "robot.log"), "w"), stderr=subprocess.STDOUT)
        wait_state(lambda s: s.get("robot_online"), timeout=15)

    @classmethod
    def _stop_processes(cls):
        for p in (cls.robot, cls.base):
            if p is not None and p.poll() is None:
                p.terminate()
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    p.kill()

    @classmethod
    def tearDownClass(cls):
        cls._stop_processes()
        if os.path.exists(STRAT_FILE):
            os.remove(STRAT_FILE)
        if not cls.cache_existed and os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
        print(f"\n[E2E] logs : {cls.tmp}")

    def test_1_reglages_appliques_par_le_robot(self):
        self.assertEqual(api("/api/action/reset", {})[0], 200)
        self.assertEqual(api("/api/config_edit", {"key": "static_strat", "val": STRAT_NAME})[0], 200)
        self.assertEqual(api("/api/config_edit", {"key": "team", "val": "JAUNE"})[0], 200)
        s = wait_state(lambda s: s.get("team") == "JAUNE" and s.get("strat_id") == STRAT_NAME)
        self.assertEqual(s["config"]["team"], "JAUNE")  # config du robot recopiée par la base

    def test_1b_ping_base_robot(self):
        code, s = api("/api/robot_ping?n=10")
        self.assertEqual(code, 200)
        self.assertEqual(s["sent"], 10)
        self.assertGreaterEqual(s["received"], 8)
        self.assertLess(s["max_ms"], 500)

    def test_2_match_et_symetrie(self):
        self.assertEqual(api("/api/action/start", {})[0], 200)
        wait_state(lambda s: s.get("fsm_state") == "RUNNING")
        # Tests réseau refusés pendant le match (ils saturent le Wi-Fi)
        self.assertEqual(api("/api/robot_ping?n=1")[0], 409)
        self.assertEqual(api("/api/speedtest/upload", {})[0], 409)
        # La stratégie (écrite côté BLEUE) s'exécute en JAUNE : y -> -y, remonté par la télémétrie
        wait_state(lambda s: abs(s["telemetry"]["x"] - 700) < 1 and abs(s["telemetry"]["y"] + 1250) < 1)
        # Équipe refusée pendant le match (par le robot)
        api("/api/action/team", {})
        time.sleep(0.5)
        self.assertEqual(api("/api/state")[1]["team"], "JAUNE")
        self.assertEqual(api("/api/action/stop", {})[0], 200)
        wait_state(lambda s: s.get("fsm_state") == "STOPPED" and not s.get("match_running"))

    def test_3_robot_hors_ligne(self):
        self.robot.terminate()
        self.robot.wait(5)
        wait_state(lambda s: not s.get("robot_online"), timeout=8)
        code, body = api("/api/action/start", {})
        self.assertEqual(code, 503)
        self.assertIn("hors ligne", body.get("msg", ""))


if __name__ == "__main__":
    unittest.main()
