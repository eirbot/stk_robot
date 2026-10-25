#!/usr/bin/env python3
"""Vidéo d'une simulation de navigation, avec le vrai code du robot et de la base.

    uv run tools/video_simu.py                       # -> simu_navigation.mp4 (dossier courant)
    uv run tools/video_simu.py -o /tmp/simu.mp4 --duree 60 --accelere 2

Ce qui tourne est le code réel : planificateur de la base (Rasp/core/navigation.py : Kalman de
l'adversaire, A* dans le temps, pierres, hystérésis), suivi de trajectoire du robot (core/suivi.py,
consignes V à 20 Hz), puis rotation finale. Seul le monde est simulé : robot différentiel (rampe
d'accélération, un pas de retard comme l'ESP), adversaire qui fait des allers-retours au milieu de la
table, caméra zénithale (bruit 10 mm), piles de pierres, LiDAR dans la balise (72 secteurs) : il ne voit
que la balise adverse, les pierres ne sont vues que par la caméra.
Vue de dessus dans le repère de la carte 3D : Y vers la droite, X vers le bas.
"""

import argparse
import math
import os
import random
import subprocess
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "Rasp"))
from core import frames, planif, suivi as suivi_mod  # noqa: E402
from core.navigation import Navigateur  # noqa: E402

DT = 0.05
W, H = 1920, 1080
ECH = 0.5                       # px par mm : table 3000 x 2000 mm -> 1500 x 1000 px
OX, OY = 20, 60                 # coin de la table dans l'image
PANNEAU_X = OX + 1500 + 30

# --- Scénario -------------------------------------------------------------------------------
DEPART = (250.0, -1250.0, 0.0)
OBJECTIFS = [                   # (nom, x, y, theta, durée de l'action s)
    ("Carrière A", 1650.0, -1150.0, 0.0, 1.5),
    ("Carrière B", 1700.0, 1150.0, 90.0, 1.5),
    ("Rempart", 350.0, 1100.0, 180.0, 2.0),
    ("Retour", 300.0, -1150.0, -90.0, 1.0),
]
# Le robot fait le tour de la table ; l'adversaire fait des allers-retours au milieu (Y = 0) et croise sa
# route en haut et en bas ; les piles imposent des détours sans fermer de couloir (vérifié avec le
# planificateur, robot gonflé de 60 mm).
PIERRES = [(750.0, -700.0, 0.0, 3), (750.0, 700.0, 90.0, 2), (1250.0, 650.0, 0.0, 2),
           (1650.0, -500.0, 90.0, 1), (350.0, 450.0, 90.0, 1)]
ADVERSAIRE = {"chemin": [(350.0, 0.0), (1650.0, 0.0)], "vitesse": 450.0, "pause": 1.2, "rayon": 200.0}
ROBOT = {"avant": frames.ROBOT_FRONT_MM, "arriere": frames.ROBOT_BACK_MM, "demi_largeur": frames.ROBOT_HALF_WIDTH_MM}


# --- Monde simulé ---------------------------------------------------------------------------
class Adversaire:
    def __init__(self, cfg):
        self.chemin, self.v, self.pause, self.r = cfg["chemin"], cfg["vitesse"], cfg["pause"], cfg["rayon"]
        self.k, self.x, self.y = 1, *self.chemin[0]
        self.attente = cfg["pause"]

    def pas(self, dt):
        if self.attente > 0:
            self.attente -= dt
            return
        tx, ty = self.chemin[self.k]
        d = math.hypot(tx - self.x, ty - self.y)
        if d <= self.v * dt:
            self.x, self.y = tx, ty
            self.k = (self.k + 1) % len(self.chemin)
            self.attente = self.pause
        else:
            self.x += (tx - self.x) / d * self.v * dt
            self.y += (ty - self.y) / d * self.v * dt


def rect_pierre(x, y, th, lg=320.0, la=110.0):
    c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
    return [(x + u * c - v * s, y + u * s + v * c) for u, v in
            ((lg / 2, la / 2), (lg / 2, -la / 2), (-lg / 2, -la / 2), (-lg / 2, la / 2))]


def dans_pierre(px, py, p):
    x, y, th = p[0], p[1], p[2]
    c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
    u, v = (px - x) * c + (py - y) * s, -(px - x) * s + (py - y) * c
    return abs(u) <= 160 and abs(v) <= 55


RAYON_BALISE = 40.0


def lidar(pose, adv, portee=3000.0, pas=10.0):
    """Points (repère table) du LiDAR simulé, à hauteur de balise : seule la balise adverse (au centre de
    l'adversaire) est vue ; les pierres sont plus basses."""
    x, y, th = pose
    pts = []
    for i in range(72):
        a = math.radians(th + i * 5 + 2.5)
        ca, sa = math.cos(a), math.sin(a)
        d = 150.0
        while d < portee:
            px, py = x + d * ca, y + d * sa
            if not frames.in_table(px, py, 40):
                break
            if math.hypot(px - adv.x, py - adv.y) < RAYON_BALISE:
                pts.append((px, py))
                break
            d += pas
    return pts


# --- Rendu ----------------------------------------------------------------------------------
def px(x, y):
    return int(round(OX + (y + 1500.0) * ECH)), int(round(OY + x * ECH))


def police(taille, gras=False):
    for f in ("/usr/share/fonts/liberation/LiberationSans-%s.ttf" % ("Bold" if gras else "Regular"),
              "/usr/share/fonts/TTF/DejaVuSans%s.ttf" % ("-Bold" if gras else "")):
        if os.path.exists(f):
            return ImageFont.truetype(f, taille)
    return ImageFont.load_default()


def image_carte(carte):
    """Carte de coûts (nx x ny cellules) -> image BGRA à la taille de la table."""
    c = np.array(carte.cout, dtype=np.float64).reshape(carte.nx, carte.ny)
    img = np.zeros((carte.nx, carte.ny, 4), np.uint8)
    interdit = np.isinf(c)
    sur = np.clip((np.where(interdit, 1.0, c) - 1.0) / 6.0, 0.0, 1.0)
    img[..., 0], img[..., 1], img[..., 2] = 0, 140, 255           # orange
    img[..., 3] = (sur * 150).astype(np.uint8)
    img[interdit] = (40, 40, 230, 95)                             # rouge
    return cv2.resize(img, (int(carte.ny * carte.res * ECH), int(carte.nx * carte.res * ECH)),
                      interpolation=cv2.INTER_NEAREST)


def superposer(fond, calque, x0, y0):
    h, w = calque.shape[:2]
    h, w = min(h, fond.shape[0] - y0), min(w, fond.shape[1] - x0)
    a = calque[:h, :w, 3:4].astype(np.float32) / 255.0
    zone = fond[y0:y0 + h, x0:x0 + w].astype(np.float32)
    fond[y0:y0 + h, x0:x0 + w] = (zone * (1 - a) + calque[:h, :w, :3].astype(np.float32) * a).astype(np.uint8)


def dessiner(etat, polices):
    img = np.full((H, W, 3), (32, 30, 28), np.uint8)
    # table
    cv2.rectangle(img, px(0, -1500), px(2000, 1500), (72, 64, 58), -1)
    for v in range(-1500, 1501, 250):
        cv2.line(img, px(0, v), px(2000, v), (92, 84, 78), 1)
    for v in range(0, 2001, 250):
        cv2.line(img, px(v, -1500), px(v, 1500), (92, 84, 78), 1)
    cv2.rectangle(img, px(0, -1500), px(2000, -1490), (255, 140, 47), -1)     # côté bleu
    cv2.rectangle(img, px(0, 1490), px(2000, 1500), (63, 210, 255), -1)       # côté jaune
    if etat["carte_img"] is not None:
        superposer(img, etat["carte_img"], OX, OY)
    # pierres
    for p in PIERRES:
        pts = np.array([px(*q) for q in rect_pierre(*p[:3])], np.int32)
        cv2.fillPoly(img, [pts], (101, 161, 200), cv2.LINE_AA)
        cv2.polylines(img, [pts], True, (40, 80, 120), 2, cv2.LINE_AA)
    # trajectoire prédite de l'adversaire
    for t, x, y, sig in etat["prediction"]:
        a = max(0.15, 1.0 - t / 3.0)
        cv2.circle(img, px(x, y), max(2, int(sig * ECH)), (int(80 * a), int(80 * a), int(255 * a)), 1, cv2.LINE_AA)
        cv2.circle(img, px(x, y), 4, (60, 60, 255), -1, cv2.LINE_AA)
    adv = etat["adv"]
    cv2.circle(img, px(adv.x, adv.y), int(adv.r * ECH), (59, 59, 255), -1, cv2.LINE_AA)
    cv2.circle(img, px(adv.x, adv.y), int(adv.r * ECH), (20, 20, 160), 3, cv2.LINE_AA)
    # LiDAR
    for q in etat["lidar"]:
        cv2.circle(img, px(*q), 4, (82, 82, 255), -1, cv2.LINE_AA)
    # objectifs
    for k, (_, x, y, th, _) in enumerate(OBJECTIFS):
        c = (255, 255, 255) if k == etat["obj"] else (150, 150, 150)
        cv2.circle(img, px(x, y), 16, c, 2, cv2.LINE_AA)
    # trace et chemin planifié
    if len(etat["trace"]) > 1:
        cv2.polylines(img, [np.array([px(x, y) for x, y in etat["trace"]], np.int32)], False, (220, 220, 220), 2, cv2.LINE_AA)
    if etat["chemin"]:
        pts = np.array([px(x, y) for x, y in etat["chemin"]], np.int32)
        cv2.polylines(img, [pts], False, (255, 229, 0), 3, cv2.LINE_AA)
        for q in pts[1:]:
            cv2.circle(img, tuple(int(v) for v in q), 6, (255, 229, 0), -1, cv2.LINE_AA)
    # robot
    x, y, th = etat["pose"]
    coins = frames.robot_corners(x, y, th)
    cv2.fillPoly(img, [np.array([px(*q) for q in coins], np.int32)], (63, 210, 255), cv2.LINE_AA)
    cv2.polylines(img, [np.array([px(*q) for q in coins], np.int32)], True, (0, 0, 0), 2, cv2.LINE_AA)
    fx, fy = frames.offset_along(x, y, th, ROBOT["avant"] + 40)
    cv2.line(img, px(x, y), px(fx, fy), (40, 40, 220), 4, cv2.LINE_AA)

    # textes (Pillow : accents)
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(pil)
    d.text((OX, 14), "Eirbot — simulation de navigation (planificateur de la base + suivi de trajectoire)",
           font=polices["titre"], fill=(255, 255, 255))
    for k, (nom, x, y, _, _) in enumerate(OBJECTIFS):
        qx, qy = px(x, y)
        d.text((qx - 6, qy - 11), str(k + 1), font=polices["petit_gras"], fill=(255, 255, 255))
    for p in PIERRES:
        qx, qy = px(p[0], p[1])
        d.ellipse((qx - 13, qy - 13, qx + 13, qy + 13), fill=(0, 0, 0))
        d.text((qx - 6, qy - 11), str(p[3]), font=polices["petit_gras"], fill=(255, 255, 255))
    lignes = [
        ("Temps", f"{etat['t']:5.1f} s"),
        ("Objectif", f"{etat['obj'] + 1}/{len(OBJECTIFS)} — {OBJECTIFS[min(etat['obj'], len(OBJECTIFS) - 1)][0]}"),
        ("État", etat["etat"]),
        ("Vitesse", f"{etat['v']:4.0f} mm/s   {etat['w']:+4.0f} °/s"),
        ("Plan", f"{etat['calc_ms']:4.1f} ms, {max(0, len(etat['chemin']) - 1)} segment(s)"),
        ("Durée prévue", f"{etat['duree_plan']:4.1f} s"),
        ("Changements", str(etat["changements"])),
        ("Marge adversaire", "—" if etat["marge"] is None else f"{etat['marge']:4.0f} mm"),
    ]
    yy = OY
    for k, v in lignes:
        d.text((PANNEAU_X, yy), k, font=polices["petit"], fill=(170, 170, 170))
        d.text((PANNEAU_X, yy + 22), v, font=polices["normal"], fill=(255, 255, 255))
        yy += 64
    legende = [((255, 210, 63), "notre robot (vraies dimensions)"), ((0, 229, 255), "chemin planifié"),
               ((255, 59, 59), "adversaire + trajectoire prédite"), ((255, 82, 82), "points LiDAR"),
               ((200, 161, 101), "pile de pierres (nombre)"), ((255, 140, 0), "carte de coûts : surcoût"),
               ((230, 40, 40), "carte de coûts : interdit (robot gonflé)")]
    yy += 20
    for c, txt in legende:
        d.rectangle((PANNEAU_X, yy + 4, PANNEAU_X + 18, yy + 22), fill=c)
        d.text((PANNEAU_X + 28, yy), txt, font=polices["petit"], fill=(230, 230, 230))
        yy += 32
    return cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)


# --- Simulation -------------------------------------------------------------------------------
def simuler(sortie, duree_max, accelere, cfg_planif):
    rnd = random.Random(4)
    nav = Navigateur(cfg_planif)
    adv = Adversaire(ADVERSAIRE)
    x, y, th = DEPART
    v_reel = w_reel = 0.0
    cmd_retard = (0.0, 0.0)
    obj, etat_txt = 0, "départ"
    action_reste, suiveur, chemin, nav_id = 0.5, None, [], 0
    changements, calc_ms, duree_plan, marge = 0, 0.0, 0.0, None
    trace, lidar_pts, carte_img, prediction = [], [], None, []
    polices = {"titre": police(26, True), "normal": police(24), "petit": police(18), "petit_gras": police(18, True)}
    ffmpeg = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24",
                               "-s", f"{W}x{H}", "-r", str(int(round(1 / DT * accelere))), "-i", "-",
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", sortie], stdin=subprocess.PIPE)
    n, t = 0, 0.0
    t0 = time.perf_counter()
    while t < duree_max and obj < len(OBJECTIFS):
        adv.pas(DT)
        # caméra zénithale (adversaire bruité ; pierres toutes les 0,2 s) et LiDAR (10 Hz)
        vision = {"adversaires": [{"id": 7, "x": adv.x + rnd.gauss(0, 10), "y": adv.y + rnd.gauss(0, 10)}]}
        if n % 4 == 0:
            vision["pierres"] = [{"x": p[0], "y": p[1], "theta": p[2], "nb": p[3]} for p in PIERRES]
        nav.observer_vision(vision, t)
        if n % 2 == 0:
            lidar_pts = lidar((x, y, th), adv)
            nav.observer_lidar(lidar_pts, t)
        nav.observer_pose(x, y, th, t)
        nom, gx, gy, gth, action_s = OBJECTIFS[obj]

        v_cmd = w_cmd = 0.0
        if action_reste > 0:                              # action en cours (ou départ)
            action_reste -= DT
            etat_txt = "action" if t > 0.6 else "départ"
            if action_reste <= 0 and etat_txt == "départ":
                pass
        elif etat_txt == "rotation finale":
            err = (gth - th + 180) % 360 - 180
            w_cmd = max(-180.0, min(180.0, 4.0 * err))
            if abs(err) < 1.0:
                etat_txt, action_reste = "action", action_s
                obj += 1
                suiveur, chemin = None, []
                nav.terminer(nav_id)
                v_cmd = w_cmd = 0.0
        else:
            if nav.nav is None:
                nav_id += 1
                nav.demander(nav_id, (gx, gy, gth), cfg_planif)
                suiveur = None
            if n % 2 == 0:                                # la base replanifie à 10 Hz
                c0 = time.perf_counter()
                plan, change = nav.planifier(t, (x, y, th))
                calc_ms = (time.perf_counter() - c0) * 1000
                changements += 1 if change and suiveur is not None else 0
                if plan is not None:
                    chemin, duree_plan = list(plan.points), plan.duree
                    marge = None if math.isinf(plan.marge_adversaire_mm) else plan.marge_adversaire_mm
                    if suiveur is None:
                        suiveur = suivi_mod.Suivi(chemin, cfg_planif)
                    else:
                        suiveur.changer_chemin(chemin)
                carte_img = image_carte(nav.carte) if nav.carte is not None else None
                prediction = nav.predictions(t, 3.0, 0.25)[0]["trajectoire"] if nav.suivi.actives(t) else []
            if suiveur is not None:
                obstacle = suivi_mod.obstacle_devant(lidar_pts, (x, y, th))
                r = planif.DEFAUTS["rayon_adversaire_mm"] + planif.DEFAUTS["rayon_robot_mm"]
                m_adv = min(math.hypot(px_ - x, py_ - y) - r for (px_, py_, _) in
                            [p.position(t + dt) for p in nav.suivi.actives(t) for dt in (0.0, 0.5)]) \
                    if nav.suivi.actives(t) else math.inf
                cmd = suiveur.commande((x, y, th), DT, obstacle, m_adv)
                etat_txt = {"rotation": "rotation sur place", "suivi": "suivi de trajectoire",
                            "arrive": "rotation finale"}[cmd.etat]
                v_cmd, w_cmd = (cmd.v, cmd.w) if cmd.etat != "arrive" else (0.0, 0.0)
            else:
                etat_txt = "pas de chemin : attente"

        # robot : la commande arrive au pas suivant (comme l'ESP), rampe d'accélération
        cv_, cw_ = cmd_retard
        cmd_retard = (v_cmd, w_cmd)
        v_reel += max(-1400 * DT, min(1400 * DT, cv_ - v_reel))
        w_reel = cw_
        th += w_reel * DT
        x += v_reel * math.cos(math.radians(th)) * DT
        y += v_reel * math.sin(math.radians(th)) * DT
        if n % 2 == 0:
            trace.append((x, y))
        frame = dessiner({"t": t, "obj": min(obj, len(OBJECTIFS) - 1), "etat": etat_txt, "v": v_reel, "w": w_reel,
                          "calc_ms": calc_ms, "chemin": chemin if suiveur else [], "duree_plan": duree_plan,
                          "changements": changements, "marge": marge, "pose": (x, y, th), "adv": adv,
                          "lidar": lidar_pts, "carte_img": carte_img, "prediction": prediction,
                          "trace": trace[-400:]}, polices)
        ffmpeg.stdin.write(frame.tobytes())
        n += 1
        t += DT
    ffmpeg.stdin.close()
    ffmpeg.wait()
    print(f"{sortie} : {n} images ({t:.1f} s simulées, {len(OBJECTIFS) if obj >= len(OBJECTIFS) else obj} "
          f"objectifs atteints), rendu en {time.perf_counter() - t0:.0f} s")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--sortie", default="simu_navigation.mp4")
    ap.add_argument("--duree", type=float, default=60.0, help="durée simulée maximale (s)")
    ap.add_argument("--accelere", type=float, default=1.0, help="vitesse de lecture (1 = temps réel)")
    args = ap.parse_args()
    import json
    with open(os.path.join(ROOT, "Rasp", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f).get("planif", {})
    simuler(args.sortie, args.duree, args.accelere, cfg)


if __name__ == "__main__":
    main()
