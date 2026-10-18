"""tools/regler_fusion.py : retrouve des paramètres connus sur un enregistrement synthétique."""
import importlib.util
import math
import os
import random
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("regler_fusion", os.path.join(ROOT, "tools", "regler_fusion.py"))
rf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rf)

VRAI = {"latence": 0.25, "gigue": 0.02, "cam_mm": 6.0, "cam_deg": 0.8,
        "echelle_d": 1.02, "echelle_r": 0.99}


def enregistrement(seed=3, duree=150.0):
    """Robot qui tourne, roule, s'arrête ; odométrie à 50 Hz, caméra à 15 Hz en retard."""
    rng = random.Random(seed)
    vrai = [1000.0, 0.0, 0.0]
    odo = list(vrai)
    events = [("s", 0.0, *odo)]
    passe = []  # (t, vraie pose)
    t, dt = 0.0, 0.02
    plan = []

    def ajoute_mouvements():
        cap = rng.uniform(-180, 180)
        dist = rng.uniform(300, 900)
        # Rester sur la table : demi-tour vers le centre si on s'éloigne
        if math.hypot(vrai[0] - 1000, vrai[1]) > 600:
            cap = math.degrees(math.atan2(-vrai[1], 1000 - vrai[0]))
        plan.extend([("tourne", cap), ("roule", dist), ("pause", rng.uniform(1.5, 3.0))])

    prochain_img = 0.0
    while t < duree:
        if not plan:
            ajoute_mouvements()
        action, val = plan[0]
        dd = dth = 0.0
        if action == "tourne":
            err = rf.angle_diff_deg(val, vrai[2])
            dth = max(-180 * dt, min(180 * dt, err))
            if abs(err) < 0.5:
                plan.pop(0)
        elif action == "roule":
            dd = min(500 * dt, val)
            plan[0] = ("roule", val - dd)
            if val - dd <= 0:
                plan.pop(0)
        else:
            plan[0] = ("pause", val - dt)
            if val - dt <= 0:
                plan.pop(0)
        t += dt
        th = math.radians(vrai[2])
        vrai[0] += dd * math.cos(th)
        vrai[1] += dd * math.sin(th)
        vrai[2] += dth
        tho = math.radians(odo[2])
        do = dd * VRAI["echelle_d"] * (1 + rng.gauss(0, 0.01))
        odo[0] += do * math.cos(tho)
        odo[1] += do * math.sin(tho)
        odo[2] += dth * VRAI["echelle_r"] + rng.gauss(0, 0.01) * (1 if dd or dth else 0)
        passe.append((t, tuple(vrai)))
        events.append(("o", t, odo[0], odo[1], rf.angle_diff_deg(odo[2], 0)))
        if t >= prochain_img:
            prochain_img = t + 1 / 15
            p = passe[-1][1]
            t_recu = t + VRAI["latence"] + rng.gauss(0, VRAI["gigue"])
            events.append(("c", t_recu, p[0] + rng.gauss(0, VRAI["cam_mm"]), p[1] + rng.gauss(0, VRAI["cam_mm"]),
                           rf.angle_diff_deg(p[2] + rng.gauss(0, VRAI["cam_deg"]), 0)))
    events.sort(key=lambda e: e[1])
    return events


class TestReglerFusion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = enregistrement()
        cls.prop, cls.rapport = rf.analyser(cls.events, {"latence_s": 0.5})

    def test_latence(self):
        self.assertAlmostEqual(self.rapport["latence_s"], VRAI["latence"], delta=0.03)

    def test_bruit_camera(self):
        mm, deg = self.rapport["bruit_camera"]
        self.assertAlmostEqual(mm, VRAI["cam_mm"], delta=1.5)
        self.assertAlmostEqual(deg, VRAI["cam_deg"], delta=0.25)

    def test_echelles(self):
        d = self.rapport["derive"]
        # échelle = caméra / odométrie : l'inverse de l'erreur de l'odométrie
        self.assertAlmostEqual(d["echelle_distance"], 1 / VRAI["echelle_d"], delta=0.005)
        self.assertAlmostEqual(d["echelle_rotation"], 1 / VRAI["echelle_r"], delta=0.01)

    def test_rejeu_ameliore(self):
        actuel, propose = self.rapport["rejeu_actuel"], self.rapport["rejeu_propose"]
        self.assertLessEqual(propose["taux_rejet"], actuel["taux_rejet"])
        self.assertLess(propose["taux_rejet"], 0.05)

    def test_lecture_fichier(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("type,t,x,y,theta\n")
            for e in self.events[:200]:
                f.write(f"{e[0]},{e[1]:.4f},{e[2]:.2f},{e[3]:.2f},{e[4]:.3f}\n")
            f.write("ligne cassée\n")
        try:
            self.assertEqual(len(rf.load_log(f.name)), 200)
        finally:
            os.remove(f.name)


if __name__ == "__main__":
    unittest.main()
