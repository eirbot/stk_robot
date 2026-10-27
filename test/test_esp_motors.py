"""Tests de Rasp/interface_deplacement/esp_motors.py (liaison série avec l'ESP moteurs) :
battement de cœur, watchdog « W », GoTo numérotés (D id / A id), trames E, ESP absent, fusion.

Aucun matériel : les modules `serial` et `ihm.shared` sont simulés.
Lancement : `python3 -m pytest test/test_esp_motors.py` ou `python3 test/test_esp_motors.py`.
"""
import re
import importlib.util
import os
import queue
import sys
import threading
import time
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESP_MOTORS_PATH = os.path.join(ROOT, "Rasp", "interface_deplacement", "esp_motors.py")


class FakeSerial:
    """Faux port série : mémorise les écritures, readline() lit une file de lignes."""

    def __init__(self, *args, **kwargs):
        self.is_open = True
        self.writes = []  # (instant monotonic, ligne)
        self.rx = queue.Queue()
        self._lock = threading.Lock()
        self.timeout = kwargs.get("timeout", 0.1)

    def setDTR(self, val):
        pass

    def setRTS(self, val):
        pass

    def reset_input_buffer(self):
        pass

    def write(self, data):
        with self._lock:
            self.writes.append((time.monotonic(), data.decode("utf-8").rstrip("\n")))
        return len(data)

    def readline(self):
        try:
            return (self.rx.get(timeout=self.timeout) + "\n").encode("utf-8")
        except queue.Empty:
            return b""

    def close(self):
        self.is_open = False

    def sent(self):
        with self._lock:
            return list(self.writes)


def load_module():
    """Importe esp_motors.py avec des faux modules `serial` et `ihm.shared`
    (remis en place ensuite : les autres tests importent les vrais)."""
    saved = {k: sys.modules.get(k) for k in ("serial", "ihm", "ihm.shared")}
    fake_serial = types.ModuleType("serial")
    fake_serial.Serial = FakeSerial
    fake_serial.SerialException = type("SerialException", (Exception,), {})
    sys.modules["serial"] = fake_serial

    ihm = types.ModuleType("ihm")
    shared = types.ModuleType("ihm.shared")
    shared.state = {"match_running": True}
    shared.robot_pos = {"x": 0.0, "y": 0.0, "theta": 0.0}
    sys.path.insert(0, os.path.join(ROOT, "Rasp"))
    from core.localisation import Localisation
    shared.loc = Localisation()

    def set_known_pose(x, y, theta, odo_pose=None):
        shared.loc.reset((x, y, theta), odo_pose, t=time.time())
        shared.robot_pos.update({"x": x, "y": y, "theta": theta})

    shared.set_known_pose = set_known_pose
    shared.loc_log = types.SimpleNamespace(write=lambda *a: None)
    shared.logs = []
    shared.send_log = lambda msg, log_type="info": shared.logs.append((msg, log_type))
    ihm.shared = shared
    sys.modules["ihm"] = ihm
    sys.modules["ihm.shared"] = shared

    spec = importlib.util.spec_from_file_location("esp_motors_test", ESP_MOTORS_PATH)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return mod, shared


def wait_for(cond, timeout=1.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def sent_lines(esp):
    return [l for _, l in esp.ser.sent()]


def wait_goto(esp, timeout=1.0):
    """Attend l'envoi d'un G ; renvoie (id, x, y, theta) du dernier envoyé."""
    def last_goto():
        gotos = [l for l in sent_lines(esp) if l.startswith("G ")]
        return gotos[-1] if gotos else None

    assert wait_for(lambda: last_goto() is not None, timeout), f"pas de G envoyé : {sent_lines(esp)}"
    m = re.fullmatch(r"G (\d+) (\S+) (\S+) (\S+)", last_goto())
    assert m, f"G mal formé : {last_goto()}"
    return int(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))


def start_goto(esp, x, y, theta, **kw):
    result = {}
    th = threading.Thread(target=lambda: result.update(ok=esp.goto(x, y, theta, **kw)), daemon=True)
    th.start()
    return th, result


def test_heartbeat_periodique():
    mod, _ = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        time.sleep(1.05)
        beats = [t for t, l in esp.ser.sent() if l == "K"]
        # ~10 battements par seconde attendus
        assert 8 <= len(beats) <= 12, f"{len(beats)} battements en 1 s"
        gaps = [b - a for a, b in zip(beats, beats[1:])]
        # Jamais plus de 200 ms entre deux battements (watchdog ESP à 300 ms)
        assert max(gaps) < 0.2, f"écart max {max(gaps):.3f} s"
    finally:
        esp.stop()


def test_commande_compte_comme_signe_de_vie():
    mod, _ = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        time.sleep(0.15)
        # Commandes envoyées plus vite que la période : plus besoin de "K"
        t_start = time.monotonic()
        while time.monotonic() - t_start < 0.5:
            esp.set_speed(100, 0)
            time.sleep(0.03)
        sent = [(t, l) for t, l in esp.ser.sent() if t_start + 0.05 < t < t_start + 0.5]
        assert any(l.startswith("V ") for _, l in sent)
        assert not any(l == "K" for _, l in sent), "K envoyé alors que des commandes partaient"
        # Puis la liaison redevient muette : le battement de cœur reprend
        time.sleep(0.3)
        assert any(l == "K" and t > t_start + 0.5 for t, l in esp.ser.sent())
    finally:
        esp.stop()


def test_trame_watchdog_et_trames_existantes():
    mod, shared = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        assert esp.watchdog_count == 0 and not esp.watchdog_tripped

        # Trames existantes inchangées
        esp.ser.rx.put("T 120.50 340.00 90.00")
        assert wait_for(lambda: shared.robot_pos["x"] == 120.5)
        assert shared.robot_pos["y"] == 340.0 and shared.robot_pos["theta"] == 90.0

        # Watchdog ESP déclenché
        esp.ser.rx.put("W")
        assert wait_for(lambda: esp.watchdog_count == 1)
        assert esp.watchdog_tripped and esp.last_watchdog_time is not None

        # Le battement de cœur et l'état LiDAR n'effacent pas l'état watchdog...
        esp.set_lidar_state(0)
        time.sleep(0.15)
        assert esp.watchdog_tripped
        # ... seule une nouvelle consigne de mouvement le fait
        esp.set_speed(0, 0)
        assert not esp.watchdog_tripped

        esp.ser.rx.put("W")
        assert wait_for(lambda: esp.watchdog_count == 2)

        # GoTo long : il attend "D" pendant que le battement de cœur continue
        result = {}
        th = threading.Thread(target=lambda: result.setdefault("ok", esp.goto(500, 500, 0)))
        th.start()
        time.sleep(0.6)
        assert th.is_alive()
        beats_during = [l for t, l in esp.ser.sent() if l == "K"]
        assert len(beats_during) >= 5
        goto_id, x, y, theta = wait_goto(esp)
        assert (x, y, theta) == (500.0, 500.0, 0.0)
        esp.ser.rx.put(f"D {goto_id}")
        th.join(2)
        assert result.get("ok") is True and not esp.watchdog_tripped
    finally:
        esp.stop()


def test_fusion_goto_et_odometrie():
    """GoTo converti dans le repère odo de l'ESP ; trames T -> pose fusionnée (repère table)."""
    mod, shared = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        # « S » envoyé en décimal ; le repère odo de la fusion = la valeur envoyée
        esp.set_pos(1000.44, 0.0, 10.4)
        assert "S 1000.4 0.0 10.40" in sent_lines(esp)
        esp.ser.rx.put("T 1000.40 0.00 10.40")
        assert wait_for(lambda: abs(shared.robot_pos["theta"] - 10.4) < 1e-6)
        assert abs(shared.robot_pos["x"] - 1000.44) < 1e-6

        # La caméra voit le robot 50 mm plus loin en X (correction forcée, robot immobile)
        shared.loc.on_camera(time.time(), 1050.44, 0.0, 10.4, gain=1.0)
        th, result = start_goto(esp, 1050.44, 0.0, 10.4)
        # Cible table = pose actuelle : l'ESP reçoit sa propre pose odo
        goto_id, x, y, theta = wait_goto(esp)
        assert abs(x - 1000.4) < 0.06 and abs(y) < 0.06 and abs(theta - 10.4) < 0.006
        esp.ser.rx.put(f"D {goto_id}")
        th.join(2)
        assert result.get("ok") is True
    finally:
        esp.stop()


def test_goto_annule():
    mod, _ = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        th, result = start_goto(esp, 100, 0, 0)
        goto_id, *_ = wait_goto(esp)
        esp.ser.rx.put(f"A {goto_id}")
        th.join(2)
        assert result.get("ok") is False
    finally:
        esp.stop()


def test_goto_facteur_vitesse():
    """vitesse < 1 : 5e champ du G ; pleine vitesse : G à 4 champs (comme avant)."""
    mod, _ = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        th, result = start_goto(esp, 100, 0, 0, vitesse=0.3)
        assert wait_for(lambda: any(l.startswith("G ") for l in sent_lines(esp)))
        g = [l for l in sent_lines(esp) if l.startswith("G ")][-1]
        assert g.endswith(" 0.30"), g
        esp.ser.rx.put(f"D {g.split()[1]}")
        th.join(2)
        th, result = start_goto(esp, 200, 0, 0)
        goto_id, *_ = wait_goto(esp)
        esp.ser.rx.put(f"D {goto_id}")
        th.join(2)
        assert result.get("ok") is True
    finally:
        esp.stop()


def test_reponse_d_un_ancien_goto_ignoree():
    """Le « A » en retard d'un GoTo précédent ne termine pas le GoTo en cours."""
    mod, _ = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        th1, r1 = start_goto(esp, 100, 0, 0)
        id1, *_ = wait_goto(esp)
        esp.ser.rx.put(f"A {id1}")
        th1.join(2)
        th2, r2 = start_goto(esp, 200, 0, 0)
        assert wait_for(lambda: sum(l.startswith("G ") for l in sent_lines(esp)) == 2)
        id2 = int([l for l in sent_lines(esp) if l.startswith("G ")][-1].split()[1])
        assert id2 != id1
        esp.ser.rx.put(f"A {id1}")   # réponse en double / en retard de l'ancien
        esp.ser.rx.put("D 999999")   # numéro inconnu
        time.sleep(0.3)
        assert th2.is_alive(), "un D / A d'un autre GoTo a terminé le GoTo en cours"
        esp.ser.rx.put(f"D {id2}")
        th2.join(2)
        assert r2.get("ok") is True
    finally:
        esp.stop()


def test_deux_goto_simultanes():
    """GoTo manuel pendant un autre : chacun reçoit SA réponse (l'ESP annule le premier)."""
    mod, _ = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        th1, r1 = start_goto(esp, 100, 0, 0)
        assert wait_for(lambda: sum(l.startswith("G ") for l in sent_lines(esp)) == 1)
        th2, r2 = start_goto(esp, 200, 0, 0, manual=True)
        assert wait_for(lambda: sum(l.startswith("G ") for l in sent_lines(esp)) == 2)
        id1, id2 = [int(l.split()[1]) for l in sent_lines(esp) if l.startswith("G ")]
        esp.ser.rx.put(f"A {id1}")
        esp.ser.rx.put(f"D {id2}")
        th1.join(2)
        th2.join(2)
        assert r1.get("ok") is False and r2.get("ok") is True
    finally:
        esp.stop()


def test_arret_du_match_pendant_goto():
    mod, shared = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        th, result = start_goto(esp, 100, 0, 0)
        wait_goto(esp)
        shared.state["match_running"] = False
        th.join(2)
        assert result.get("ok") is False
        assert "H" in sent_lines(esp)
    finally:
        esp.stop()


def test_goto_sans_reponse_expire():
    mod, _ = load_module()
    mod.GOTO_TIMEOUT_S = 0.5
    esp = mod.ESPMotors()
    esp.start()
    try:
        th, result = start_goto(esp, 100, 0, 0)
        th.join(2)
        assert result.get("ok") is False
        assert "H" in sent_lines(esp)
    finally:
        esp.stop()


def test_esp_absent():
    """Port série non ouvert : erreur claire au lieu d'attendre la fin du match."""
    mod, _ = load_module()
    esp = mod.ESPMotors()  # start() pas appelé : aucun port
    assert not esp.connected
    try:
        esp.goto(100, 0, 0)
    except mod.ESPError as e:
        assert "non connecté" in str(e)
    else:
        raise AssertionError("ESPError attendue")


def test_trame_erreur_journalisee():
    mod, shared = load_module()
    esp = mod.ESPMotors()
    esp.start()
    try:
        esp.ser.rx.put("E commande inconnue")
        assert wait_for(lambda: esp.errors == ["commande inconnue"])
        assert ("ESP moteurs : commande inconnue", "err") in shared.logs
    finally:
        esp.stop()


class TestESPMotors(__import__("unittest").TestCase):
    """Rend ces tests visibles par `unittest discover` (tools/run_tests.sh)."""


for _name, _fn in list(globals().items()):
    if _name.startswith("test_") and callable(_fn):
        setattr(TestESPMotors, _name, (lambda f: lambda self: f())(_fn))


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v) and not isinstance(v, type)]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"{len(tests)} tests passés")
