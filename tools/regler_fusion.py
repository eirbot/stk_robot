#!/usr/bin/env python3
"""Réglage automatique de la fusion odométrie + caméra à partir d'un enregistrement du robot.

Enregistrement : le robot écrit Rasp/logs/localisation/loc_*.csv (Rasp/utils/loc_recorder.py) dès
que l'odométrie ou la caméra parlent. Pour un bon réglage : caméra zénithale allumée, robot
qui roule ET tourne sur toute la table (match ou pilotage manuel), avec des arrêts de
quelques secondes. 2-3 minutes suffisent.

    scp eirbot:Documents/robot_stk/logs/localisation/loc_<date>.csv .
    tools/regler_fusion.py loc_<date>.csv                    # rapport + réglages proposés
    tools/regler_fusion.py loc_<date>.csv --appliquer Rasp/config.json

Ce qui est estimé (aucune vérité terrain : la caméra sert de référence, à son bruit près)
  - latence_s : retard des images. Les déplacements (distance, rotation) entre deux images
    ne dépendent pas du repère : on cherche le décalage qui les fait coïncider avec ceux
    de l'odométrie.
  - cam_sigma_mm / cam_sigma_deg : dispersion des images robot immobile.
  - erreur d'échelle des roues (distance et rotation) : à corriger dans le firmware.
  - odo_sigma_* et latence_sigma_s : ce qui reste d'écart, par mètre, par tour et selon la vitesse.
Puis l'enregistrement est rejoué dans core/localisation.py avec les réglages actuels et
proposés : innovation normalisée moyenne (idéal ~3) et mesures rejetées.
"""

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "Rasp"))

from core.reglage_fusion import *  # noqa: E402,F401,F403  (analyse : Rasp/core/reglage_fusion.py)
from core.reglage_fusion import analyser, load_log  # noqa: E402


def _fmt(v, unit="", nd=1):
    return "?" if v is None else f"{v:.{nd}f}{unit}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log", help="logs/localisation/loc_*.csv récupéré du robot")
    ap.add_argument("--config", default=os.path.join(ROOT, "Rasp", "config.json"),
                    help="config.json dont on lit les réglages actuels")
    ap.add_argument("--appliquer", metavar="CONFIG", help="écrire les réglages proposés dans ce config.json")
    args = ap.parse_args()

    events = load_log(args.log)
    try:
        with open(args.config, encoding="utf-8") as f:
            actuelle = json.load(f).get("vision_odom", {})
    except (OSError, ValueError):
        actuelle = {}
    prop, r = analyser(events, actuelle)

    print(f"Enregistrement : {r['trames_odo']} trames odométrie, {r['images']} images caméra")
    print(f"Latence caméra       : {_fmt(r['latence_s'], ' s', 3)}"
          + ("" if r["latence_s"] is not None else "  (pas assez de mouvement)"))
    b = r["bruit_camera"]
    print(f"Bruit caméra immobile: {_fmt(b and b[0], ' mm')} / {_fmt(b and b[1], '°', 2)}"
          + ("" if b else "  (pas assez d'arrêts d'au moins 1 s)"))
    d = r["derive"]
    if d:
        err_d = (1 / d["echelle_distance"] - 1) * 100
        err_r = (1 / d["echelle_rotation"] - 1) * 100
        print(f"Erreur odométrie     : distances {err_d:+.1f} %, rotations {err_r:+.1f} %"
              f"  ({d['couples']} couples ; + = l'odométrie surestime)")
        # distance odo ∝ diamètre ; rotation odo ∝ diamètre / entraxe
        if abs(err_d) > 1:
            print(f"  -> distances : multiplier le diamètre des roues du firmware par {d['echelle_distance']:.4f}")
        if abs(err_r) > 1:
            print(f"  -> rotations : multiplier l'entraxe du firmware par "
                  f"{d['echelle_distance'] / d['echelle_rotation']:.4f} (avec le diamètre corrigé)")
        if abs(err_d) > 1 or abs(err_r) > 1:
            print("     puis refaire un enregistrement pour vérifier")
    for nom in ("rejeu_actuel", "rejeu_propose"):
        rj = r[nom]
        print(f"Rejeu {'actuel ' if nom == 'rejeu_actuel' else 'proposé'} : {rj['acceptees']} acceptées, "
              f"{rj['rejetees']} rejetées ({rj['taux_rejet']:.0%}), innovation normalisée moyenne "
              f"{_fmt(rj['nis_moyen'], '', 2)} (idéal ~3)")
    print("\nRéglages proposés (vision_odom) :")
    print(json.dumps(prop, indent=4, ensure_ascii=False))

    if args.appliquer and prop:
        with open(args.appliquer, encoding="utf-8") as f:
            raw = f.read()
        cfg = json.loads(raw)
        cfg["vision_odom"] = dict(sorted({**cfg.get("vision_odom", {}), **prop}.items()))
        with open(args.appliquer, "w", encoding="utf-8") as f:
            f.write(json.dumps(cfg, indent=4, ensure_ascii=False) + ("\n" if raw.endswith("\n") else ""))
        print(f"\nÉcrit dans {args.appliquer}")


if __name__ == "__main__":
    main()
