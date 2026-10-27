"""Essai sur table : aller() depuis la pose actuelle (pas de set_pos), cibles dans le tiers du milieu de la
table (|y| <= 250 : le robot ne passe pas sur les jonctions entre tables, où il glisse), puis retour."""
from strat.actions import RobotActions
from ihm import shared

METADATA = {"name": "essai_aller"}

CIBLES = [(1500, 0, 0), (1000, -200, -90), (600, 200, 180)]


def run(robot: RobotActions):
    p = dict(shared.robot_pos)
    print(f"[ESSAI] départ {p}")
    for cible in CIBLES + [(round(p["x"]), round(p["y"]), round(p["theta"]))]:
        ok = robot.aller(*cible, real=True)
        print(f"[ESSAI] aller{cible} -> {ok}, pose {shared.robot_pos}")
