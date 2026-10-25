"""Stratégie dynamique : choix du prochain objectif (pur Python, testé).

Les objectifs restent écrits à la main (où aller, quelle action, combien de points) ; c'est l'ordre
qui est décidé en match, à chaque fois qu'un objectif se termine, d'après :
  - les points espérés (points x probabilité de réussite) ;
  - le temps : trajet estimé (core/temps_match.py) + durée de l'action, et il doit rester de quoi
    rentrer (retour de fin de match) après ;
  - l'adversaire : un objectif près de lui est moins sûr (il y est peut-être déjà) ;
  - les prérequis (ex. « déposer » après « prendre ») et les échecs (un objectif raté est retenté
    plus tard avec une probabilité diminuée).
On évalue les suites de `profondeur` objectifs (recherche exhaustive, quelques dizaines d'objectifs
au plus) et on garde le premier de la meilleure suite : points espérés par seconde, avec un bonus
pour le total, les objectifs suivants étant actualisés (x ACTUALISATION par rang).
"""

import math
from dataclasses import dataclass, field

from core import temps_match


@dataclass
class Objectif:
    nom: str
    x: float                      # pose d'approche (repère table, déjà symétrisée pour l'équipe)
    y: float
    theta: float
    points: float
    duree_action_s: float = 2.0
    proba: float = 1.0            # probabilité de réussite a priori
    prerequis: tuple = ()         # noms d'objectifs à avoir réussis avant
    action: str = ""              # méthode de RobotActions appelée une fois arrivé (vide = rien)
    args: dict = field(default_factory=dict)
    max_essais: int = 2


@dataclass
class Etat:
    reussis: set = field(default_factory=set)
    essais: dict = field(default_factory=dict)      # nom -> nombre d'échecs


DISTANCE_ADVERSAIRE_MM = 500.0    # en dessous, la probabilité baisse (jusqu'à x0,3 au contact)
ACTUALISATION = 0.8               # un objectif plus loin dans la suite compte moins (l'avenir est
                                  # incertain) : à valeur égale, le plus sûr passe en premier


def proba_effective(obj, etat, adversaires=()):
    p = obj.proba * (0.5 ** etat.essais.get(obj.nom, 0))
    for ax, ay in adversaires:
        d = math.hypot(obj.x - ax, obj.y - ay)
        if d < DISTANCE_ADVERSAIRE_MM:
            p *= 0.3 + 0.7 * d / DISTANCE_ADVERSAIRE_MM
    return p


def disponibles(objectifs, etat):
    return [o for o in objectifs
            if o.nom not in etat.reussis and etat.essais.get(o.nom, 0) < o.max_essais
            and all(p in etat.reussis for p in o.prerequis)]


def duree_objectif(pose, obj, modele=None, detour=1.25):
    d, r = temps_match.rotations_goto(pose, (obj.x, obj.y, obj.theta))
    return temps_match.duree_goto(d * detour, r, modele) + obj.duree_action_s


def choisir(objectifs, etat, pose, temps_restant, retour=None, marge_s=3.0, adversaires=(),
            modele=None, profondeur=2):
    """(objectif, valeur) du meilleur prochain objectif, ou (None, 0) si plus rien n'est faisable.

    retour : pose (x, y, theta) de fin de match, ou None (pas de contrainte de retour)."""
    def retour_depuis(p):
        if retour is None:
            return 0.0
        d, r = temps_match.rotations_goto(p, retour)
        return temps_match.duree_goto(d * 1.25, r, modele)

    def meilleur(pose_, etat_, restant, n):
        best = (None, 0.0, 0.0)               # (premier objectif, points espérés, durée)
        for o in disponibles(objectifs, etat_):
            t = duree_objectif(pose_, o, modele)
            fin = (o.x, o.y, o.theta)
            if restant - t < retour_depuis(fin) + marge_s:
                continue
            pts = o.points * proba_effective(o, etat_, adversaires)
            if pts <= 0:
                continue
            tot_pts, tot_t = pts, t
            if n > 1:
                suite = Etat(set(etat_.reussis) | {o.nom}, dict(etat_.essais))
                _, p2, t2 = meilleur(fin, suite, restant - t, n - 1)
                tot_pts, tot_t = pts + ACTUALISATION * p2, t + t2
            if _valeur(tot_pts, tot_t) > _valeur(best[1], best[2]):
                best = (o, tot_pts, tot_t)
        return best

    o, pts, t = meilleur(tuple(pose), etat, temps_restant, max(1, profondeur))
    return (o, _valeur(pts, t)) if o else (None, 0.0)


def _valeur(points, duree):
    if points <= 0 or duree <= 0:
        return 0.0
    return points / duree + 0.05 * points
