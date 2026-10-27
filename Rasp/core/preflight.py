"""Check-list avant match (pur Python, testé) : ce qui empêcherait le match de bien se passer.

`evaluer(e)` prend un dict d'entrées (rempli par ihm/tasks.py à 1 Hz, clés ci-dessous, toutes
facultatives) et renvoie la liste des vérifications, chacune {id, label, niveau, detail} avec
niveau "ok" | "warn" | "err". Pas prêt = au moins un "err".

Entrées :
    esp_moteurs (bool, port ouvert), esp_moteurs_age_s (depuis la dernière trame, None = jamais),
    esp_actionneurs (bool), lidar_mode, lidar_age_s (dernier tour), camera_zen_age_s (dernière pose
    caméra zénithale), tension_v, strategie (nom ou None), strategie_existe (bool), depart (pose
    (x, y, theta) du premier set_pos de la stratégie, symétrie d'équipe déjà appliquée), pose_camera
    (dernière pose caméra zénithale), equipe, tirette, test_mode, camera_embarquee (activée dans la
    config), camera_embarquee_ok, temp_cpu, match_running.
"""

import math
import re

from core.frames import angle_diff_deg

OK, WARN, ERR = "ok", "warn", "err"

TENSION_ERR_V = 17.0  # alerte batterie faible (aussi ihm/tasks.py)
TENSION_WARN_V = 17.5  # avertissement, et rétablissement de l'alerte
DEPART_TOL_MM = 50.0
DEPART_TOL_DEG = 10.0


def _item(id_, label, niveau, detail=""):
    return {"id": id_, "label": label, "niveau": niveau, "detail": detail}


def _age(e, cle, max_s):
    a = e.get(cle)
    return a is not None and a <= max_s


def evaluer(e):
    out = []

    if not e.get("esp_moteurs"):
        out.append(_item("esp_moteurs", "ESP moteurs", ERR, "port fermé (câble ?)"))
    elif not _age(e, "esp_moteurs_age_s", 1.0):
        out.append(_item("esp_moteurs", "ESP moteurs", ERR, "aucune trame odométrie"))
    else:
        out.append(_item("esp_moteurs", "ESP moteurs", OK))

    out.append(_item("esp_actionneurs", "ESP actionneurs", OK) if e.get("esp_actionneurs")
               else _item("esp_actionneurs", "ESP actionneurs", ERR, "port fermé"))

    mode = e.get("lidar_mode", "MATCH")
    if mode == "OFF":
        out.append(_item("lidar", "LiDAR", ERR, "évitement désactivé (mode OFF)"))
    elif not _age(e, "lidar_age_s", 1.0):
        out.append(_item("lidar", "LiDAR", ERR, "aucun tour reçu"))
    elif mode == "HOMOLOGATION":
        out.append(_item("lidar", "LiDAR", WARN, "mode homologation"))
    else:
        out.append(_item("lidar", "LiDAR", OK))

    if _age(e, "camera_zen_age_s", 2.0):
        out.append(_item("camera_zen", "Caméra zénithale", OK))
    else:
        out.append(_item("camera_zen", "Caméra zénithale", WARN, "robot non vu : odométrie seule"))

    v = e.get("tension_v")
    if v is None or v < 3.0:
        out.append(_item("batterie", "Batterie", WARN, "pas de mesure"))
    elif v < TENSION_ERR_V:
        out.append(_item("batterie", "Batterie", ERR, f"{v:.1f} V : à changer"))
    elif v < TENSION_WARN_V:
        out.append(_item("batterie", "Batterie", WARN, f"{v:.1f} V"))
    else:
        out.append(_item("batterie", "Batterie", OK, f"{v:.1f} V"))

    strat = e.get("strategie")
    if not strat:
        out.append(_item("strategie", "Stratégie", ERR, "aucune choisie"))
    elif not e.get("strategie_existe", True):
        out.append(_item("strategie", "Stratégie", ERR, f"{strat} introuvable sur le robot"))
    else:
        out.append(_item("strategie", "Stratégie", OK, str(strat)))

    depart, cam = e.get("depart"), e.get("pose_camera")
    if depart and cam and _age(e, "camera_zen_age_s", 2.0):
        d = math.hypot(cam[0] - depart[0], cam[1] - depart[1])
        da = abs(angle_diff_deg(cam[2], depart[2])) if depart[2] is not None else 0.0
        if d > DEPART_TOL_MM or da > DEPART_TOL_DEG:
            out.append(_item("depart", "Position de départ", WARN,
                             f"à {d:.0f} mm / {da:.0f}° de ({depart[0]:.0f}, {depart[1]:.0f})"))
        else:
            out.append(_item("depart", "Position de départ", OK))

    out.append(_item("equipe", "Équipe", OK, str(e.get("equipe") or "?")))

    tir = e.get("tirette")
    if e.get("match_running"):
        out.append(_item("tirette", "Tirette", OK, "match en cours"))
    elif tir == "ARMED":
        out.append(_item("tirette", "Tirette", OK, "armée"))
    elif tir == "WAIT":
        out.append(_item("tirette", "Tirette", ERR, "à retirer puis remettre"))
    else:
        out.append(_item("tirette", "Tirette", WARN, "à insérer"))

    if e.get("test_mode"):
        out.append(_item("test_mode", "Mode test", WARN, "pas d'arrêt à 100 s"))

    if e.get("camera_embarquee") and not e.get("camera_embarquee_ok"):
        out.append(_item("camera_emb", "Caméra embarquée", WARN, "activée mais arrêtée"))

    t = e.get("temp_cpu")
    if t is not None and t > 75.0:
        out.append(_item("temp_cpu", "Température Rasp", WARN, f"{t:.0f} °C"))
    return out


def pret(items):
    return not any(i["niveau"] == ERR for i in items)


def depart_strategie(source):
    """(x, y, theta) du premier robot.set_pos(...) d'une stratégie Python (côté BLEUE), ou None."""
    m = re.search(r"\.set_pos\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)", source or "")
    return tuple(float(v) for v in m.groups()) if m else None
