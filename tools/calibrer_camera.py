#!/usr/bin/env python3
"""Calibration du repère caméra (config vision_odom.repere) à partir de positions mesurées au mètre.

La caméra zénithale peut voir les distances trop grandes ou trop petites (échelle), tournées ou
décalées. On pose le robot en quelques points connus (au moins 2, idéalement 4-5 répartis sur
la table), on relève à chaque fois la position mesurée et celle que donne la caméra, avec
`vision_odom.repere` remis à l'identité (sinon on calibre une correction déjà corrigée).

    tools/calibrer_camera.py 1898,0:1988,-11  880,10:870,38  1000,1400:983,1480
    tools/calibrer_camera.py ... --appliquer Rasp/config.json

Chaque point : x_mesuré,y_mesuré:x_caméra,y_caméra (mm, repère robot).
Modèle (le même que Rasp/core/frames.py : apply_camera_repere) :
    vrai = rotation(rotation_deg) . (centre + echelle * (caméra - centre)) + (dx, dy)
Avec 2 points ou plus : échelle, rotation et translation ; avec 1 point : translation seule.
"""

import argparse
import cmath
import json
import math
import os
import sys

CENTRE = complex(1000.0, 0.0)  # centre de la table (repère robot) : point fixe de la mise à l'échelle


def parse_point(text):
    try:
        mes, cam = text.split(":")
        xm, ym = (float(v) for v in mes.split(","))
        xc, yc = (float(v) for v in cam.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"point invalide : {text!r} (attendu : xm,ym:xc,yc)")
    return complex(xm, ym), complex(xc, yc)


def fit(points):
    """Similitude vrai = a * caméra + b (nombres complexes) aux moindres carrés."""
    n = len(points)
    if n == 1:
        (w, z), = points
        return 1.0 + 0j, w - z
    zm = sum(z for _, z in points) / n
    wm = sum(w for w, _ in points) / n
    den = sum(abs(z - zm) ** 2 for _, z in points)
    if den < 1.0:
        raise SystemExit("Points caméra confondus : impossible de calculer une échelle")
    a = sum((w - wm) * (z - zm).conjugate() for w, z in points) / den
    return a, wm - a * zm


def to_repere(a, b):
    """a, b -> paramètres de apply_camera_repere (échelle autour de CENTRE, rotation, translation)."""
    s, phi = abs(a), cmath.phase(a)
    d = b - cmath.exp(1j * phi) * CENTRE * (1 - s)
    return {"echelle": round(s, 5), "centre_x": CENTRE.real, "centre_y": CENTRE.imag,
            "rotation_deg": round(math.degrees(phi), 3), "dx": round(d.real, 1), "dy": round(d.imag, 1)}


def apply(repere, z):
    """Même formule que frames.apply_camera_repere (pour afficher les résidus)."""
    c = complex(repere["centre_x"], repere["centre_y"])
    p = c + repere["echelle"] * (z - c)
    return cmath.exp(1j * math.radians(repere["rotation_deg"])) * p + complex(repere["dx"], repere["dy"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("points", nargs="+", type=parse_point, help="xm,ym:xc,yc (mm)")
    ap.add_argument("--appliquer", metavar="CONFIG", help="écrit vision_odom.repere dans ce config.json")
    args = ap.parse_args()

    repere = to_repere(*fit(args.points))
    print("Point mesuré        caméra brute        caméra corrigée     erreur avant -> après")
    for w, z in args.points:
        c = apply(repere, z)
        print(f"({w.real:6.0f},{w.imag:6.0f})  ({z.real:6.0f},{z.imag:6.0f})  ({c.real:7.1f},{c.imag:7.1f})"
              f"   {abs(z - w):5.0f} mm -> {abs(c - w):5.1f} mm")
    print("\nvision_odom.repere proposé :")
    print(json.dumps(repere, indent=4))
    if len(args.points) < 3:
        print("\nAttention : moins de 3 points, la calibration n'est pas vérifiable (aucun résidu).")

    if args.appliquer:
        with open(args.appliquer, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("vision_odom", {})["repere"] = repere
        tmp = args.appliquer + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, args.appliquer)
        print(f"\nÉcrit dans {args.appliquer}")


if __name__ == "__main__":
    sys.exit(main())
