"""Essai sur table : aller() depuis la pose actuelle (pas de set_pos), trois cibles proches du centre puis retour."""
from strat.actions import RobotActions
from ihm import shared

METADATA = {"name": "essai_aller"}


def run(robot: RobotActions):
    p = dict(shared.robot_pos)
    print(f"[ESSAI] départ {p}")
    for cible in [(950, 450, 0), (700, 950, 90), (round(p["x"]), round(p["y"]), round(p["theta"]))]:
        ok = robot.aller(*cible, real=True)
        print(f"[ESSAI] aller{cible} -> {ok}, pose {shared.robot_pos}")
