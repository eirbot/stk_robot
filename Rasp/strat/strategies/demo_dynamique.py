"""Démonstration de stratégie dynamique (strat/actions.py : jouer) : les objectifs sont écrits à la
main, le robot choisit l'ordre en match (points, temps restant, adversaire, échecs) et se déplace
avec le planificateur (aller). Positions et actions 2027 à remplacer par les vraies."""
from strat.actions import RobotActions

METADATA = {"name": "demo_dynamique"}

OBJECTIFS = [
    {"nom": "carriere_1", "x": 700, "y": -600, "theta": 90, "points": 4, "duree_action_s": 3, "action": "prendreKapla"},
    {"nom": "carriere_2", "x": 1300, "y": -200, "theta": 0, "points": 4, "duree_action_s": 3, "action": "prendreKapla"},
    {"nom": "rempart", "x": 400, "y": -1100, "theta": 180, "points": 12, "duree_action_s": 4, "action": "poseKapla",
     "prerequis": ["carriere_1"]},
    {"nom": "carriere_3", "x": 1500, "y": 700, "theta": 90, "points": 4, "duree_action_s": 3, "action": "prendreKapla"},
]


def run(robot: RobotActions):
    robot.set_pos(250, -1200, 0)
    robot.retour_fin(250, -1200, 180, marge_s=3)
    robot.jouer(OBJECTIFS)
