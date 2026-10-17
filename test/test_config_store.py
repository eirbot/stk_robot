"""Tests de la config du robot (Rasp/core/config_store.py)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core.config_store import ConfigError, ConfigStore  # noqa: E402


class TestConfigStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "config.json")

    def tearDown(self):
        self.dir.cleanup()

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_fichier_absent_valeurs_par_defaut(self):
        store = ConfigStore(self.path)
        self.assertEqual(store.get("team"), "BLEUE")
        self.assertIs(store.get("test_mode"), False)
        self.assertIs(store.get("camera.enabled"), True)

    def test_valeur_invalide_corrigee_au_chargement(self):
        self.write({"team": "ROUGE", "lidar_mode": "MATCH", "autre": 42})
        store = ConfigStore(self.path)
        self.assertEqual(store.get("team"), "BLEUE")
        self.assertEqual(store.get("lidar_mode"), "MATCH")
        self.assertEqual(store.get("autre"), 42)  # clé inconnue conservée

    def test_update_valide_et_enregistre(self):
        store = ConfigStore(self.path)
        changed = store.update({"team": "JAUNE", "camera.enabled": False})
        self.assertEqual(changed, {"team": "JAUNE", "camera.enabled": False})
        saved = self.read()
        self.assertEqual(saved["team"], "JAUNE")
        self.assertIs(saved["camera"]["enabled"], False)

    def test_update_dict_imbrique(self):
        store = ConfigStore(self.path)
        store.update({"camera": {"enabled": False}})
        self.assertIs(store.get("camera.enabled"), False)

    def test_update_refuse_tout_ou_rien(self):
        store = ConfigStore(self.path)
        with self.assertRaises(ConfigError):
            store.update({"team": "JAUNE", "lidar_mode": "TURBO"})
        self.assertEqual(store.get("team"), "BLEUE")  # rien appliqué

    def test_sans_changement_pas_d_ecriture(self):
        store = ConfigStore(self.path)
        store.save()
        mtime = os.path.getmtime(self.path)
        self.assertEqual(store.update({"team": "BLEUE"}), {})
        self.assertEqual(os.path.getmtime(self.path), mtime)

    def test_booleen_texte_accepte(self):
        store = ConfigStore(self.path)
        store.update({"test_mode": "true"})
        self.assertIs(store.get("test_mode"), True)

    def test_data_modifie_en_place(self):
        store = ConfigStore(self.path)
        alias = store.data  # comme shared.cfg
        store.update({"team": "JAUNE"})
        self.assertEqual(alias["team"], "JAUNE")

    def test_json_corrompu(self):
        with open(self.path, "w") as f:
            f.write("{pas du json")
        store = ConfigStore(self.path)
        self.assertEqual(store.get("team"), "BLEUE")


if __name__ == "__main__":
    unittest.main()
