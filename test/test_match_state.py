"""Tests de la machine d'état du match (Rasp/core/match_state.py), avec une horloge simulée."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Rasp"))
from core.config_store import ConfigStore  # noqa: E402
from core import match_state as ms  # noqa: E402
from core.match_state import MatchError, MatchState  # noqa: E402


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class RecordingEffects:
    def __init__(self):
        self.calls = []

    def led(self, cmd):
        self.calls.append(("led", cmd))

    def on_match_start(self):
        self.calls.append(("start",))

    def on_match_end(self, reason):
        self.calls.append(("end", reason))

    def on_stop(self):
        self.calls.append(("stop",))

    def on_reset(self):
        self.calls.append(("reset",))

    def names(self):
        return [c[0] for c in self.calls]


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.config = ConfigStore(os.path.join(self.dir.name, "config.json"))
        self.config.update({"strat_mode": "STATIC", "static_strat": "3b_pouss_plus"})
        self.clock = FakeClock()
        self.fx = RecordingEffects()
        self.state = {}
        self.m = MatchState(self.state, self.config, self.fx, clock=self.clock)

    def tearDown(self):
        self.dir.cleanup()

    def arm_and_start(self):
        self.m.ready(tirette_inserted=False)
        self.m.tirette_changed(inserted=True)
        self.m.tirette_changed(inserted=False)


class TestDemarrage(Base):
    def test_strat_initiale_depuis_config(self):
        # Bug d'origine : le robot lançait la strat « 1 »
        self.assertEqual(self.state["strat_id"], "3b_pouss_plus")

    def test_tirette_absente_au_demarrage(self):
        self.m.ready(tirette_inserted=False)
        self.assertEqual(self.m.phase, ms.WAIT_START)
        self.assertEqual(self.state["tirette"], ms.TIR_READY)
        self.assertIn(("led", ms.TEAM_COLORS["BLEUE"]), self.fx.calls)

    def test_tirette_presente_au_demarrage_doit_etre_retiree(self):
        self.m.ready(tirette_inserted=True)
        self.assertEqual(self.state["tirette_msg"], "REMOVE_TO_RESET")
        self.m.tirette_changed(inserted=False)        # retrait : prêt
        self.assertEqual(self.state["tirette"], ms.TIR_READY)
        self.m.tirette_changed(inserted=True)         # insertion : armé
        self.assertEqual(self.state["tirette"], ms.TIR_ARMED)


class TestMatch(Base):
    def test_sequence_complete_tirette(self):
        self.arm_and_start()
        self.assertTrue(self.m.running)
        self.assertEqual(self.m.phase, ms.RUNNING)
        self.assertIn(("start",), self.fx.calls)
        self.clock.advance(30)
        self.m.tick()
        self.assertEqual(self.state["timer_str"], "70.0")
        self.clock.advance(70.05)
        self.m.tick()
        self.assertFalse(self.m.running)
        self.assertTrue(self.state["match_finished"])
        self.assertEqual(self.m.phase, ms.FINISHED)
        self.assertEqual(self.state["timer_str"], "0.0")
        self.assertIn(("end", "timer"), self.fx.calls)

    def test_strategie_finie_avant_100s_le_match_continue(self):
        self.arm_and_start()
        self.clock.advance(40)
        self.m.strategy_finished()
        self.assertTrue(self.m.running)

    def test_mode_test_pas_d_arret_a_100s(self):
        self.config.update({"test_mode": True})
        self.m._sync_from_config()
        self.arm_and_start()
        self.clock.advance(130)
        self.m.tick()
        self.assertTrue(self.m.running)
        self.assertEqual(self.state["timer_str"], "-30.0")
        self.m.strategy_finished()
        self.assertFalse(self.m.running)
        self.assertIn(("end", "strategy"), self.fx.calls)

    def test_retirer_tirette_sans_armer_ne_lance_rien(self):
        self.m.ready(tirette_inserted=False)
        self.m.tirette_changed(inserted=False)
        self.assertFalse(self.m.running)

    def test_go_interface(self):
        self.m.ready(tirette_inserted=False)
        self.m.start()
        self.assertTrue(self.m.running)
        self.m.start()  # double clic : ignoré
        self.assertEqual(self.fx.names().count("start"), 1)


class TestArretsEtRelance(Base):
    def test_rearmement_tirette_apres_match(self):
        # Avant : il fallait passer par RESET MATCH sur l'interface
        self.arm_and_start()
        self.clock.advance(101)
        self.m.tick()
        self.assertEqual(self.m.phase, ms.FINISHED)
        self.m.tirette_changed(inserted=True)
        self.assertEqual(self.m.phase, ms.WAIT_START)
        self.assertEqual(self.state["tirette"], ms.TIR_ARMED)
        self.assertEqual(self.state["timer_str"], "100.0")
        self.assertIn(("reset",), self.fx.calls)
        self.m.tirette_changed(inserted=False)
        self.assertTrue(self.m.running)

    def test_stop_puis_reset(self):
        self.arm_and_start()
        self.m.stop()
        self.assertEqual(self.m.phase, ms.STOPPED)
        self.assertFalse(self.m.running)
        self.assertIn(("stop",), self.fx.calls)
        self.m.reset()
        self.assertEqual(self.m.phase, ms.WAIT_START)
        self.assertFalse(self.state["match_finished"])

    def test_arret_urgence(self):
        self.arm_and_start()
        self.m.emergency_stop()
        self.assertEqual(self.m.phase, ms.STOPPED)
        self.assertIn(("led", "COLOR:255,0,0"), self.fx.calls)
        # BAU encore enfoncé : remettre la tirette n'arme pas
        self.m.tirette_changed(inserted=False)
        self.m.tirette_changed(inserted=True, bau_pressed=True)
        self.assertNotEqual(self.state["tirette"], ms.TIR_ARMED)
        # BAU relâché : on peut réarmer
        self.m.tirette_changed(inserted=False)
        self.m.tirette_changed(inserted=True)
        self.assertEqual(self.state["tirette"], ms.TIR_ARMED)

    def test_remettre_tirette_pendant_match_ignore(self):
        self.arm_and_start()
        self.m.tirette_changed(inserted=True)
        self.assertTrue(self.m.running)


class TestReglages(Base):
    def test_equipe_bloquee_pendant_match(self):
        self.arm_and_start()
        with self.assertRaises(MatchError):
            self.m.toggle_team()
        self.assertEqual(self.state["team"], "BLEUE")

    def test_equipe_apres_arret_change_les_leds(self):
        # Bug d'origine : après un STOP, les LEDs ne suivaient plus l'équipe
        self.arm_and_start()
        self.m.stop()
        self.fx.calls.clear()
        self.m.toggle_team()
        self.assertEqual(self.state["team"], "JAUNE")
        self.assertIn(("led", ms.TEAM_COLORS["JAUNE"]), self.fx.calls)
        self.assertEqual(self.config.get("team"), "JAUNE")  # persisté

    def test_equipe_pendant_alerte_batterie_sans_led(self):
        self.m.ready(tirette_inserted=False)
        self.m.set_battery_low(True)
        self.fx.calls.clear()
        self.m.toggle_team()
        self.assertNotIn(("led", ms.TEAM_COLORS["JAUNE"]), self.fx.calls)
        self.m.set_battery_low(False)  # fin d'alerte : couleur de l'équipe
        self.assertIn(("led", ms.TEAM_COLORS["JAUNE"]), self.fx.calls)

    def test_changement_strategie(self):
        self.m.apply_config({"static_strat": "carre"})
        self.assertEqual(self.state["strat_id"], "carre")
        self.assertEqual(self.config.get("static_strat"), "carre")

    def test_reglage_non_match_autorise_pendant_match(self):
        self.arm_and_start()
        self.m.apply_config({"lidar_mode": "OFF"})
        self.assertEqual(self.config.get("lidar_mode"), "OFF")

    def test_version_incrementee(self):
        v = self.m.version
        self.m.ready(tirette_inserted=False)
        self.assertGreater(self.m.version, v)
        v = self.m.version
        self.m.apply_config({"team": "BLEUE"})  # aucun changement réel
        self.assertEqual(self.m.version, v)

    def test_snapshot(self):
        snap = self.m.snapshot()
        for key in ("fsm_state", "team", "strat_id", "timer_str", "test_mode"):
            self.assertIn(key, snap)


if __name__ == "__main__":
    unittest.main()
