"""Test du battement de cœur Rasp -> ESP moteurs et de la trame watchdog "W".

Aucun matériel : les modules `serial` et `ihm.shared` sont simulés.
Lancement : `python3 -m pytest test/test_esp_heartbeat.py` ou `python3 test/test_esp_heartbeat.py`.
"""
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
    """Importe esp_motors.py avec des faux modules `serial` et `ihm.shared`."""
    fake_serial = types.ModuleType("serial")
    fake_serial.Serial = FakeSerial
    fake_serial.SerialException = type("SerialException", (Exception,), {})
    sys.modules["serial"] = fake_serial

    ihm = types.ModuleType("ihm")
    shared = types.ModuleType("ihm.shared")
    shared.state = {"match_running": True}
    shared.robot_pos = {"x": 0.0, "y": 0.0, "theta": 0.0}
    ihm.shared = shared
    sys.modules["ihm"] = ihm
    sys.modules["ihm.shared"] = shared

    spec = importlib.util.spec_from_file_location("esp_motors_test", ESP_MOTORS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, shared


def wait_for(cond, timeout=1.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


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
        assert ("G 500 500 0" in [l for _, l in esp.ser.sent()])
        esp.ser.rx.put("D")
        th.join(2)
        assert result.get("ok") is True and not esp.watchdog_tripped
    finally:
        esp.stop()


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"OK  {t.__name__}")
    print(f"{len(tests)} tests passés")
