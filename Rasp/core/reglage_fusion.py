"""Réglage de la fusion odométrie + caméra à partir d'un enregistrement (pur Python, testé).

Utilisé par tools/regler_fusion.py (sur PC, à partir d'un loc_*.csv) et par la calibration
automatique du robot (strat/calibration.py, sur les événements enregistrés pendant la séquence).
Ce qui est estimé : cf. tools/regler_fusion.py.
"""

import bisect
import math

from core.frames import angle_diff_deg
from core.localisation import DEFAULTS, Localisation

FENETRE_S = 0.6        # écart entre deux images comparées
FENETRE_LONGUE_S = 2.0  # pour la dérive (plus de distance, moins de bruit caméra relatif)
MOUVEMENT_MIN_MM = 20.0
MOUVEMENT_MIN_DEG = 3.0
IMMOBILE_MIN_S = 1.0


# --- Lecture ---
def load_log(path):
    events = []
    with open(path) as f:
        next(f, None)
        for line in f:
            parts = line.strip().split(",")
            if len(parts) != 5:
                continue
            try:
                events.append((parts[0], float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])))
            except ValueError:
                continue
    events.sort(key=lambda e: e[1])
    return events


class Odo:
    """Odométrie découpée en segments continus (coupés à chaque set_pos)."""

    def __init__(self, events):
        self.segs = []
        cur = []
        for kind, t, x, y, th in events:
            if kind == "s":
                if cur:
                    self.segs.append(cur)
                cur = [(t, x, y, th)]
            elif kind == "o":
                cur.append((t, x, y, th))
        if cur:
            self.segs.append(cur)
        # Cap déroulé (continu, sans saut à ±180°) : les rotations se soustraient directement
        for s in self.segs:
            for k in range(1, len(s)):
                prev = s[k - 1][3]
                s[k] = s[k][:3] + (prev + angle_diff_deg(s[k][3], prev),)
        self._times = [[p[0] for p in s] for s in self.segs]

    def seg_index(self, t):
        for i, s in enumerate(self.segs):
            if s[0][0] <= t <= s[-1][0]:
                return i
        return None

    def at(self, t, seg=None):
        """Pose odo interpolée (théta déroulé) ou None hors segment."""
        i = self.seg_index(t) if seg is None else seg
        if i is None:
            return None
        s, ts = self.segs[i], self._times[i]
        if not (ts[0] <= t <= ts[-1]):
            return None
        k = bisect.bisect_right(ts, t)
        if k >= len(s):
            return s[-1][1:]
        a, b = s[k - 1], s[k]
        f = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
        return (a[1] + f * (b[1] - a[1]), a[2] + f * (b[2] - a[2]), a[3] + f * (b[3] - a[3]))

    def speed(self, t, dt=0.1):
        p0, p1 = self.at(t - dt), self.at(t + dt)
        if p0 is None or p1 is None:
            return 0.0
        return math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / (2 * dt)

    def still_windows(self, min_s=IMMOBILE_MIN_S):
        """Périodes où l'odométrie ne bouge pas : [(t0, t1)]."""
        out = []
        for s in self.segs:
            start = s[0]
            for p in s[1:]:
                if abs(p[1] - start[1]) > 0.5 or abs(p[2] - start[2]) > 0.5 or abs(p[3] - start[3]) > 0.2:
                    if p[0] - start[0] >= min_s:
                        out.append((start[0], p[0]))
                    start = p
            if s[-1][0] - start[0] >= min_s:
                out.append((start[0], s[-1][0]))
        return out


def cameras(events):
    return [e[1:] for e in events if e[0] == "c"]


def _pairs(cams, fenetre):
    """Couples d'images séparées d'environ `fenetre` secondes."""
    ts = [c[0] for c in cams]
    for i, c in enumerate(cams):
        j = bisect.bisect_left(ts, c[0] + fenetre)
        if j < len(cams) and cams[j][0] - c[0] <= fenetre * 1.5:
            yield c, cams[j]


def _increments(odo, cams, latence, fenetre):
    """[(d_cam, d_odo, dth_cam, dth_odo, distance_m, tours, v_i, v_j)] pour les couples où le robot bouge."""
    out = []
    for a, b in _pairs(cams, fenetre):
        ta, tb = a[0] - latence, b[0] - latence
        seg = odo.seg_index(ta)
        if seg is None or odo.seg_index(tb) != seg:
            continue
        oa, ob = odo.at(ta, seg), odo.at(tb, seg)
        if oa is None or ob is None:
            continue
        d_cam = math.hypot(b[1] - a[1], b[2] - a[2])
        d_odo = math.hypot(ob[0] - oa[0], ob[1] - oa[1])
        th_odo = ob[2] - oa[2]
        # La caméra ne voit qu'un angle modulo 360° : on prend le tour le plus proche de l'odométrie
        th_cam = th_odo + angle_diff_deg(angle_diff_deg(b[3], a[3]) - th_odo, 0.0)
        if d_odo < MOUVEMENT_MIN_MM and abs(th_odo) < MOUVEMENT_MIN_DEG:
            continue
        out.append((d_cam, d_odo, th_cam, th_odo, d_odo / 1000.0, abs(th_odo) / 360.0,
                    odo.speed(ta), odo.speed(tb)))
    return out


def _scale(num_den):
    num = sum(a * b for a, b in num_den)
    den = sum(b * b for _, b in num_den)
    return num / den if den > 0 else 1.0


def _cost(incs):
    if len(incs) < 10:
        return math.inf, 1.0, 1.0
    s_d = _scale([(i[0], i[1]) for i in incs])
    s_t = _scale([(i[2], i[3]) for i in incs])
    res = sorted((i[0] - s_d * i[1]) ** 2 / 10.0 ** 2 + (i[2] - s_t * i[3]) ** 2 / 1.0 ** 2 for i in incs)
    res = res[:max(1, int(len(res) * 0.9))]   # 10 % de pires écartés (mauvaises détections)
    return sum(res) / len(res), s_d, s_t


# --- Estimations ---
def estimer_latence(odo, cams, l_max=1.0, pas=0.01):
    best = (math.inf, 0.0)
    couts = []
    for k in range(int(l_max / pas) + 1):
        lat = k * pas
        c = _cost(_increments(odo, cams, lat, FENETRE_S))[0]
        couts.append((lat, c))
        best = min(best, (c, lat))
    if not math.isfinite(best[0]):
        return None
    # Affinage parabolique autour du minimum
    i = [l for l, _ in couts].index(best[1])
    if 0 < i < len(couts) - 1 and all(math.isfinite(couts[j][1]) for j in (i - 1, i, i + 1)):
        c0, c1, c2 = couts[i - 1][1], couts[i][1], couts[i + 1][1]
        den = c0 - 2 * c1 + c2
        if den > 0:
            return best[1] + pas * 0.5 * (c0 - c2) / den
    return best[1]


def estimer_bruit_camera(odo, cams, latence):
    sxy, sth, n = 0.0, 0.0, 0
    for t0, t1 in odo.still_windows():
        pts = [c for c in cams if t0 + 0.2 <= c[0] - latence <= t1 - 0.1]
        if len(pts) < 5:
            continue
        mx = sum(p[1] for p in pts) / len(pts)
        my = sum(p[2] for p in pts) / len(pts)
        ref = pts[0][3]
        mth = ref + sum(angle_diff_deg(p[3], ref) for p in pts) / len(pts)
        sxy += sum((p[1] - mx) ** 2 + (p[2] - my) ** 2 for p in pts) / 2
        sth += sum(angle_diff_deg(p[3], mth) ** 2 for p in pts)
        n += len(pts) - 1
    if n < 10:
        return None
    return math.sqrt(sxy / n), math.sqrt(sth / n)


def _nnls2(rows, y):
    """Moindres carrés à 2 inconnues >= 0 : y ~ a*r0 + b*r1."""
    s00 = sum(r[0] * r[0] for r in rows)
    s01 = sum(r[0] * r[1] for r in rows)
    s11 = sum(r[1] * r[1] for r in rows)
    b0 = sum(r[0] * v for r, v in zip(rows, y))
    b1 = sum(r[1] * v for r, v in zip(rows, y))
    det = s00 * s11 - s01 * s01
    cands = []
    if det > 1e-12:
        cands.append(((s11 * b0 - s01 * b1) / det, (s00 * b1 - s01 * b0) / det))
    cands.append((max(0.0, b0 / s00) if s00 > 0 else 0.0, 0.0))
    cands.append((0.0, max(0.0, b1 / s11) if s11 > 0 else 0.0))
    ok = [c for c in cands if c[0] >= 0 and c[1] >= 0]

    def err(c):
        return sum((v - c[0] * r[0] - c[1] * r[1]) ** 2 for r, v in zip(rows, y))
    return min(ok, key=err)


def estimer_derive(odo, cams, latence, sig_cam_mm, sig_cam_deg):
    incs = _increments(odo, cams, latence, FENETRE_LONGUE_S)
    if len(incs) < 10:
        return None
    s_d = _scale([(i[0], i[1]) for i in incs])
    s_t = _scale([(i[2], i[3]) for i in incs])
    # Position : r² - 2 sigma_cam² ~ q * distance + sigma_lat² * (v_a² + v_b²)
    rows = [(i[4], i[6] ** 2 + i[7] ** 2) for i in incs]
    y = [(i[0] - s_d * i[1]) ** 2 - 2 * sig_cam_mm ** 2 for i in incs]
    q_xy, q_lat = _nnls2(rows, y)
    # Cap : r² - 2 sigma_cam_deg² ~ q_m * distance + q_tour * tours
    rows_t = [(i[4], i[5]) for i in incs]
    y_t = [(i[2] - s_t * i[3]) ** 2 - 2 * sig_cam_deg ** 2 for i in incs]
    q_tm, q_tt = _nnls2(rows_t, y_t)
    return {
        "echelle_distance": s_d, "echelle_rotation": s_t, "couples": len(incs),
        "odo_sigma_mm_par_m": math.sqrt(q_xy), "latence_sigma_s": math.sqrt(q_lat),
        "odo_sigma_deg_par_m": math.sqrt(q_tm), "odo_sigma_deg_par_tour": math.sqrt(q_tt),
    }


# --- Rejeu ---
def rejouer(events, cfg):
    loc = Localisation(lambda: cfg)
    nis, started = [], False
    for kind, t, x, y, th in events:
        if kind == "s":
            loc.reset((x, y, th), t=t)
            started = True
        elif kind == "o":
            if not started:
                loc.reset((x, y, th), t=t)   # pas de set_pos enregistré : on part de l'odométrie
                started = True
            loc.on_odom(t, x, y, th)
        elif kind == "c" and started:
            r = loc.on_camera(t, x, y, th)
            if r["ok"]:
                nis.append(r["nis"])
    total = loc.stats["acceptees"] + loc.stats["rejetees"]
    return {"acceptees": loc.stats["acceptees"], "rejetees": loc.stats["rejetees"],
            "taux_rejet": loc.stats["rejetees"] / total if total else 0.0,
            "nis_moyen": sum(nis) / len(nis) if nis else None}


def analyser(events, cfg_actuelle=None):
    """Renvoie (réglages proposés, rapport)."""
    cfg_actuelle = {**DEFAULTS, **(cfg_actuelle or {})}
    odo, cams = Odo(events), cameras(events)
    rapport = {"images": len(cams), "trames_odo": sum(len(s) for s in odo.segs)}
    prop = {}

    lat = estimer_latence(odo, cams)
    rapport["latence_s"] = lat
    if lat is not None:
        prop["latence_s"] = round(max(0.0, lat), 3)
    lat_use = prop.get("latence_s", cfg_actuelle["latence_s"])

    bruit = estimer_bruit_camera(odo, cams, lat_use)
    rapport["bruit_camera"] = bruit
    if bruit:
        prop["cam_sigma_mm"] = round(max(2.0, bruit[0]), 1)
        prop["cam_sigma_deg"] = round(max(0.2, bruit[1]), 2)

    der = estimer_derive(odo, cams, lat_use, prop.get("cam_sigma_mm", cfg_actuelle["cam_sigma_mm"]),
                         prop.get("cam_sigma_deg", cfg_actuelle["cam_sigma_deg"]))
    rapport["derive"] = der
    if der:
        # Une erreur d'échelle non corrigée est systématique : on la couvre par le sigma
        biais_mm = abs(der["echelle_distance"] - 1.0) * 1000.0
        biais_deg = abs(der["echelle_rotation"] - 1.0) * 360.0
        prop["odo_sigma_mm_par_m"] = round(max(2.0, der["odo_sigma_mm_par_m"], biais_mm), 1)
        prop["odo_sigma_deg_par_m"] = round(max(0.1, der["odo_sigma_deg_par_m"]), 2)
        prop["odo_sigma_deg_par_tour"] = round(max(0.2, der["odo_sigma_deg_par_tour"], biais_deg), 2)
        prop["latence_sigma_s"] = round(min(0.2, max(0.01, der["latence_sigma_s"])), 3)

    rapport["rejeu_actuel"] = rejouer(events, cfg_actuelle)
    rapport["rejeu_propose"] = rejouer(events, {**cfg_actuelle, **prop})
    return prop, rapport
