#!/usr/bin/env python3
"""Exécute une stratégie dans un robot simulé (sans base, sans matériel) et vérifie sa trajectoire.

Usage :
    python3 tools/check_strategy.py 3b_pouss_plus            # équipe BLEUE
    python3 tools/check_strategy.py 3b_pouss_plus --team JAUNE
    python3 tools/check_strategy.py 3b_pouss_plus --json     # sortie machine (tests)

Vérifie : la stratégie va au bout sans erreur, et toutes les poses envoyées à l'ESP
(set_pos / goto) sont sur la table. Code de sortie 0 si tout est bon.
"""

import argparse
import importlib
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import robot_sim  # noqa: E402


def run_strategy(name, team, timeout=60.0):
    robot_sim.FakeESPMotors.speed_mm_s = 0  # déplacements instantanés
    os.environ["ROBOT_CONFIG"] = robot_sim.prepare_config("127.0.0.1")
    robot_sim.install_fakes()
    sys.path.insert(0, robot_sim.RASP)
    os.chdir(robot_sim.RASP)

    import ihm.shared as shared
    import strat.actions as actions
    from core import frames

    shared.match.ready(tirette_inserted=False)
    shared.match.apply_config({"team": team})
    shared.match.start()

    error = []

    def target():
        try:
            mod = importlib.import_module(f"strat.strategies.{name}")
            mod.run(actions.RobotActions())
        except Exception as e:  # noqa: BLE001 - on rapporte toute erreur de la stratégie
            error.append(f"{type(e).__name__}: {e}")

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        error.append(f"pas terminée après {timeout:.0f} s")

    poses = [c for c in actions.esp.calls if c[0] in ("set_pos", "goto")]
    out_of_table = [c for c in poses if not frames.in_table(c[1], c[2])]
    return {"strategy": name, "team": team, "error": error[0] if error else None,
            "poses": poses, "out_of_table": out_of_table}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("strategy", help="nom du fichier dans Rasp/strat/strategies (sans .py)")
    parser.add_argument("--team", default="BLEUE", choices=("BLEUE", "JAUNE"))
    parser.add_argument("--json", action="store_true", help="résultat en JSON sur la dernière ligne")
    args = parser.parse_args()

    result = run_strategy(args.strategy, args.team)
    if args.json:
        print(json.dumps(result))
    else:
        print(f"\n=== {result['strategy']} ({result['team']}) : {len(result['poses'])} poses ===")
        for p in result["poses"]:
            print(f"  {p[0]:8s} x={p[1]:8.1f}  y={p[2]:8.1f}  θ={p[3]:7.1f}")
        if result["out_of_table"]:
            print(f"HORS TABLE : {result['out_of_table']}")
        if result["error"]:
            print(f"ERREUR : {result['error']}")
    ok = not result["error"] and not result["out_of_table"]
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
