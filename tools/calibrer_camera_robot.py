#!/usr/bin/env python3
"""Calibration de la caméra EMBARQUÉE (config camera.intrinseques) avec un damier imprimé.

Focale, centre optique et distorsion de l'objectif : sans eux, les distances aux tags ArUco
sont approximatives (focale déduite du champ de vision, pas de distorsion). À faire une fois par
module caméra et par mode capteur (résolution ou champ changé = recalibrer).

1. Capture : robot allumé avec la caméra active, damier (ex. 9x6 coins intérieurs, cases de
   25 mm, collé bien à plat). Entrée = une photo pleine résolution prise sur le robot (/snapshot).
   Faire 15 à 25 photos : damier près / loin, dans les coins de l'image, incliné jusqu'à ~45°.
       uv run tools/calibrer_camera_robot.py capturer --robot eirbot --dossier calib_cam/
2. Calcul : affiche le bloc à mettre dans camera.intrinseques (ou l'écrit avec --appliquer).
       uv run tools/calibrer_camera_robot.py calculer --dossier calib_cam/ --damier 9x6 --case 25
       uv run tools/calibrer_camera_robot.py calculer ... --appliquer Rasp/config.json
   Erreur de reprojection attendue : < 0,5 px. Au-delà, retirer les photos floues (listées).

Le montage (camera.montage : position, tangage...) se mesure à part, au réglet sur le robot.
"""

import argparse
import glob
import json
import os
import sys
import time
import urllib.request

import cv2
import numpy as np


def capturer(args):
    os.makedirs(args.dossier, exist_ok=True)
    url = f"http://{args.robot}:{args.port}/snapshot"
    print(f"Photos depuis {url} -> {args.dossier} (Entrée = photo, q + Entrée = fin)")
    n = len(glob.glob(os.path.join(args.dossier, "*.jpg")))
    while input(f"[{n} photos] ").strip().lower() != "q":
        try:
            data = urllib.request.urlopen(url, timeout=5).read()
        except Exception as e:
            print(f"  échec : {e}")
            continue
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
        ok, _ = cv2.findChessboardCornersSB(img, args.damier, cv2.CALIB_CB_NORMALIZE_IMAGE)
        chemin = os.path.join(args.dossier, f"{int(time.time() * 1000)}.jpg")
        with open(chemin, "wb") as f:
            f.write(data)
        n += 1
        print(f"  {chemin} ({img.shape[1]}x{img.shape[0]}) damier {'trouvé' if ok else 'NON TROUVÉ'}")


def calculer(args):
    cols, lignes = args.damier
    objet = np.zeros((cols * lignes, 3), np.float32)
    objet[:, :2] = np.mgrid[0:cols, 0:lignes].T.reshape(-1, 2) * args.case
    pts_objet, pts_image, noms, taille = [], [], [], None
    for chemin in sorted(glob.glob(os.path.join(args.dossier, "*.jpg")) + glob.glob(os.path.join(args.dossier, "*.png"))):
        img = cv2.imread(chemin, cv2.IMREAD_GRAYSCALE)
        if taille is None:
            taille = img.shape[::-1]
        elif img.shape[::-1] != taille:
            print(f"  ignorée (taille {img.shape[::-1]} != {taille}) : {chemin}")
            continue
        ok, coins = cv2.findChessboardCornersSB(img, (cols, lignes), cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_ACCURACY)
        if not ok:
            print(f"  damier non trouvé : {chemin}")
            continue
        pts_objet.append(objet)
        pts_image.append(coins.reshape(-1, 1, 2).astype(np.float32))
        noms.append(chemin)
    if len(pts_image) < 8:
        sys.exit(f"Seulement {len(pts_image)} photos utilisables : il en faut au moins 8 (15-25 conseillé).")

    rms, k, dist, rvecs, tvecs = cv2.calibrateCamera(pts_objet, pts_image, taille, None, None)
    print(f"\n{len(pts_image)} photos, erreur de reprojection {rms:.3f} px")
    for nom, o, i, r, t in zip(noms, pts_objet, pts_image, rvecs, tvecs):
        proj, _ = cv2.projectPoints(o, r, t, k, dist)
        e = float(np.sqrt(np.mean(np.sum((proj.reshape(-1, 2) - i.reshape(-1, 2)) ** 2, axis=1))))
        if e > max(2 * rms, 0.5):
            print(f"  photo douteuse ({e:.2f} px) : {nom}")
    intr = {"resolution": list(taille), "fx": round(float(k[0, 0]), 2), "fy": round(float(k[1, 1]), 2),
            "cx": round(float(k[0, 2]), 2), "cy": round(float(k[1, 2]), 2),
            "dist": [round(float(v), 6) for v in dist.ravel()[:5]], "rms_px": round(float(rms), 3)}
    print("\ncamera.intrinseques =")
    print(json.dumps(intr))
    if args.appliquer:
        with open(args.appliquer) as f:
            cfg = json.load(f)
        cfg.setdefault("camera", {})["intrinseques"] = intr
        tmp = args.appliquer + ".tmp"
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, args.appliquer)
        print(f"Écrit dans {args.appliquer}")


def _damier(s):
    c, l = s.lower().split("x")
    return int(c), int(l)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("capturer")
    a.add_argument("--robot", default="eirbot")
    a.add_argument("--port", type=int, default=8081)
    a.add_argument("--dossier", required=True)
    a.add_argument("--damier", type=_damier, default=(9, 6), help="coins intérieurs, ex. 9x6")
    b = sub.add_parser("calculer")
    b.add_argument("--dossier", required=True)
    b.add_argument("--damier", type=_damier, default=(9, 6), help="coins intérieurs, ex. 9x6")
    b.add_argument("--case", type=float, default=25.0, help="côté d'une case en mm")
    b.add_argument("--appliquer", metavar="CONFIG_JSON")
    args = ap.parse_args()
    capturer(args) if args.cmd == "capturer" else calculer(args)


if __name__ == "__main__":
    main()
