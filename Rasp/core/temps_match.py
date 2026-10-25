"""Temps de match (pur Python, testé) : durée estimée des déplacements, « a-t-on encore le temps ? ».

Modèle d'un GoTo de l'ESP (rotation vers la cible, ligne droite, rotation finale) :
    durée = t0_s + distance / v_mm_s + rotations / w_deg_s
v, w et t0 sont appris sur les GoTo réels du robot (strat/actions.py les note dans
logs/durees_goto.jsonl) par moindres carrés ; valeurs par défaut tant qu'il n'y en a pas assez.

Retour de fin de match (règlement 2027 : robot arrêté dans la salle du trône à 100 s) : la stratégie
déclare sa pose de retour ; avant chaque déplacement, si le temps restant ne couvre plus le
trajet de retour + une marge, la stratégie est interrompue et le robot rentre.
"""

import math

from core.frames import angle_diff_deg

DUREE_MATCH_S = 100.0
DEFAUTS = {"v_mm_s": 300.0, "w_deg_s": 120.0, "t0_s": 0.4}
ECHANTILLONS_MIN = 8


def duree_goto(distance_mm, rotation_deg, modele=None):
    m = {**DEFAUTS, **(modele or {})}
    return m["t0_s"] + abs(distance_mm) / m["v_mm_s"] + abs(rotation_deg) / m["w_deg_s"]


def rotations_goto(depart, cible):
    """(distance, rotation totale) d'un GoTo ESP de depart (x, y, theta) à cible (x, y, theta)."""
    dx, dy = cible[0] - depart[0], cible[1] - depart[1]
    d = math.hypot(dx, dy)
    if d < 1.0:
        return 0.0, abs(angle_diff_deg(cible[2], depart[2]))
    cap = math.degrees(math.atan2(dy, dx))
    return d, abs(angle_diff_deg(cap, depart[2])) + abs(angle_diff_deg(cible[2], cap))


def duree_chemin(depart, points, theta_final, modele=None):
    """Durée d'une suite de GoTo : depart (x, y, theta), points [(x, y)] de passage, cap final."""
    pose, total = tuple(depart), 0.0
    for k, (x, y) in enumerate(points):
        if k + 1 < len(points):
            nx, ny = points[k + 1]
            cap = math.degrees(math.atan2(ny - y, nx - x))
        else:
            cap = theta_final
        d, r = rotations_goto(pose, (x, y, cap))
        total += duree_goto(d, r, modele)
        pose = (x, y, cap)
    return total


def _resoudre3(a, b):
    """Système 3x3 (Cramer), None si singulier."""
    def det(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    d = det(a)
    if abs(d) < 1e-12:
        return None
    out = []
    for c in range(3):
        m = [list(r) for r in a]
        for r in range(3):
            m[r][c] = b[r]
        out.append(det(m) / d)
    return out


def ajuster(echantillons):
    """Modèle {v_mm_s, w_deg_s, t0_s} à partir de [(distance, rotation, durée)] ; défauts sinon."""
    ech = [e for e in echantillons if e[2] > 0 and (e[0] > 0 or e[1] > 0)]
    if len(ech) < ECHANTILLONS_MIN:
        return dict(DEFAUTS)
    ata = [[0.0] * 3 for _ in range(3)]
    atb = [0.0] * 3
    for d, r, t in ech:
        ligne = (1.0, d, r)
        for i in range(3):
            atb[i] += ligne[i] * t
            for j in range(3):
                ata[i][j] += ligne[i] * ligne[j]
    sol = _resoudre3(ata, atb)
    if sol is None or sol[1] <= 1e-6 or sol[2] <= 1e-6:
        return dict(DEFAUTS)
    t0, inv_v, inv_w = sol
    return {"v_mm_s": round(1.0 / inv_v, 1), "w_deg_s": round(1.0 / inv_w, 1), "t0_s": round(max(0.0, t0), 3)}


def temps_restant(start_time, now, duree_match=DUREE_MATCH_S):
    return duree_match - (now - start_time) if start_time else duree_match


def doit_rentrer(restant, duree_retour, marge_s):
    """True s'il faut partir maintenant pour être rentré avant la fin."""
    return restant <= duree_retour + marge_s


def assez_de_temps(restant, duree_action, duree_retour=0.0, marge_s=0.0):
    """On peut encore faire une action de duree_action secondes, puis rentrer."""
    return restant - duree_action >= duree_retour + marge_s
