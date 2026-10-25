"""Choix du prochain objectif (Rasp/core/decision.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core import decision as dec  # noqa: E402
from core.decision import Etat, Objectif  # noqa: E402

MODELE = {"v_mm_s": 400.0, "w_deg_s": 180.0, "t0_s": 0.0}


class TestDecision(unittest.TestCase):
    def test_prefere_rapport_points_temps(self):
        proche = Objectif("proche", 500, 0, 0, points=5, duree_action_s=1)
        loin = Objectif("loin", 1800, 1400, 0, points=6, duree_action_s=1)
        o, _ = dec.choisir([proche, loin], Etat(), (400, 0, 0), 90, modele=MODELE, profondeur=1)
        self.assertEqual(o.nom, "proche")

    def test_prerequis(self):
        prendre = Objectif("prendre", 1500, 0, 0, points=0.5)
        poser = Objectif("poser", 400, 0, 0, points=20, prerequis=("prendre",))
        o, _ = dec.choisir([prendre, poser], Etat(), (400, 0, 0), 90, modele=MODELE)
        self.assertEqual(o.nom, "prendre")        # seul faisable ; la suite (poser) le rend rentable
        o, _ = dec.choisir([prendre, poser], Etat(reussis={"prendre"}), (1500, 0, 0), 90, modele=MODELE)
        self.assertEqual(o.nom, "poser")

    def test_temps_et_retour(self):
        obj = Objectif("loin", 1800, 1400, 0, points=10, duree_action_s=2)
        o, _ = dec.choisir([obj], Etat(), (200, -1400, 0), 100, retour=(200, -1400, 0), modele=MODELE)
        self.assertIsNotNone(o)
        o, _ = dec.choisir([obj], Etat(), (200, -1400, 0), 15, retour=(200, -1400, 0), modele=MODELE)
        self.assertIsNone(o)                       # y aller ET rentrer ne tient pas en 15 s

    def test_adversaire(self):
        a = Objectif("a", 1000, 500, 0, points=8)
        b = Objectif("b", 1000, -500, 0, points=8)
        o, _ = dec.choisir([a, b], Etat(), (1000, 0, 90), 90, adversaires=[(1000, 550)], modele=MODELE)
        self.assertEqual(o.nom, "b")

    def test_echecs(self):
        a = Objectif("a", 1000, 500, 0, points=8, max_essais=2)
        b = Objectif("b", 1000, -500, 0, points=6)
        etat = Etat(essais={"a": 1})               # a déjà raté une fois : proba x0,5
        o, _ = dec.choisir([a, b], etat, (1000, 0, 90), 90, modele=MODELE, profondeur=1)
        self.assertEqual(o.nom, "b")
        etat.essais["a"] = 2
        self.assertNotIn(a, dec.disponibles([a, b], etat))

    def test_profondeur_regroupe(self):
        # Deux objectifs proches l'un de l'autre valent mieux qu'un seul isolé un peu plus rentable
        iso = Objectif("isole", 1000, -1200, 0, points=7)
        g1 = Objectif("g1", 1000, 1000, 0, points=6)
        g2 = Objectif("g2", 1100, 1100, 0, points=6)
        o1, _ = dec.choisir([iso, g1, g2], Etat(), (1000, 0, 0), 90, modele=MODELE, profondeur=1)
        o2, _ = dec.choisir([iso, g1, g2], Etat(), (1000, 0, 0), 90, modele=MODELE, profondeur=2)
        self.assertEqual(o1.nom, "isole")
        self.assertIn(o2.nom, ("g1", "g2"))

    def test_rien(self):
        self.assertEqual(dec.choisir([], Etat(), (0, 0, 0), 90), (None, 0.0))


if __name__ == "__main__":
    unittest.main()
