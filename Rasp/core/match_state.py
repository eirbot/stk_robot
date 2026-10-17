"""Machine d'état du match : SEUL endroit qui fait évoluer l'état du match.

Avant, trois écrivains se marchaient dessus (base Go, thread boutons, client ZMQ),
d'où des bugs (strat « 1 » lancée, équipe ignorée, RESET obligatoire...). Désormais :
- les boutons, le client ZMQ (ordres de la base) et la boucle de stratégie
  appellent les méthodes de MatchState ;
- MatchState écrit le résultat dans le dict partagé `state` (shared.state), que le
  reste du code lit comme avant, et que le client ZMQ publie vers la base ;
- les effets matériels (LED, moteurs, actionneurs, son) passent par l'objet `effects`
  fourni de l'extérieur (main_robot.py), ce qui rend ce module testable sans robot
  (cf. test/test_match_state.py).

Phases (fsm_state) : INIT -> WAIT_START -> RUNNING -> FINISHED | STOPPED
Tirette (tirette)  : WAIT (présente au démarrage : à retirer) -> WAIT_INSERT -> ARMED -> TRIGGERED
"""

import threading
import time

MATCH_DURATION_S = 100.0

# Phases
INIT = "INIT"
WAIT_START = "WAIT_START"
RUNNING = "RUNNING"
FINISHED = "FINISHED"
STOPPED = "STOPPED"

# Tirette
TIR_REMOVE_FIRST = "WAIT"        # présente au démarrage / après arrêt d'urgence : à retirer avant d'armer
TIR_READY = "WAIT_INSERT"        # absente : l'insérer arme le robot
TIR_ARMED = "ARMED"              # insérée : la retirer lance le match
TIR_TRIGGERED = "TRIGGERED"      # retirée, match lancé

TEAM_COLORS = {"BLEUE": "COLOR:0,0,255", "JAUNE": "COLOR:255,160,0"}

# Clés de l'état publiées vers la base (snapshot)
PUBLISHED_KEYS = (
    "fsm_state", "match_running", "match_finished", "timer_str", "tirette", "tirette_msg",
    "team", "strat_mode", "static_strat", "strat_id", "test_mode", "bat_low",
)


class NoEffects:
    """Effets par défaut : rien (tests, simulation)."""
    def led(self, cmd): pass
    def on_match_start(self): pass
    def on_match_end(self, reason): pass
    def on_stop(self): pass
    def on_reset(self): pass


class MatchError(Exception):
    """Commande refusée (ex. changer d'équipe pendant un match)."""


class MatchState:
    def __init__(self, state, config, effects=None, clock=time.time):
        self.state = state          # dict partagé (shared.state)
        self.config = config        # ConfigStore
        self.effects = effects or NoEffects()
        self.clock = clock
        self._lock = threading.RLock()
        self.version = 0            # incrémenté à chaque changement (publication vers la base)
        with self._lock:
            self.state.setdefault("bat_low", False)
            self.state.update({
                "fsm_state": INIT,
                "match_running": False,
                "match_finished": False,
                "start_time": None,
                "timer_str": f"{MATCH_DURATION_S:.1f}",
                "tirette": TIR_READY,
                "tirette_msg": "WAITING",
            })
            self._sync_from_config()

    # ------------------------------------------------------------------
    # Lecture
    @property
    def phase(self):
        return self.state["fsm_state"]

    @property
    def running(self):
        return self.state["match_running"]

    def snapshot(self):
        with self._lock:
            return {k: self.state.get(k) for k in PUBLISHED_KEYS}

    # ------------------------------------------------------------------
    # Interne
    def _changed(self):
        self.version += 1

    def _sync_from_config(self):
        """Champs d'état dérivés de la config (équipe, strat, mode test)."""
        cfg = self.config
        self.state["team"] = cfg.get("team")
        self.state["strat_mode"] = cfg.get("strat_mode")
        self.state["static_strat"] = cfg.get("static_strat")
        self.state["test_mode"] = bool(cfg.get("test_mode"))
        if cfg.get("strat_mode") == "STATIC" and cfg.get("static_strat"):
            self.state["strat_id"] = cfg.get("static_strat")
        else:
            self.state["strat_id"] = cfg.get("strat_id", 1)

    def _alert_active(self):
        """Une alerte visible sur les LEDs (batterie, tirette, armé, match) masque la couleur d'équipe."""
        s = self.state
        return (s.get("bat_low") or s.get("tirette_msg") == "REMOVE_TO_RESET"
                or s.get("tirette") == TIR_ARMED or s.get("match_running"))

    def show_team_color(self, force=False):
        if force or not self._alert_active():
            self.effects.led(TEAM_COLORS.get(self.state.get("team"), TEAM_COLORS["BLEUE"]))

    def _require_not_running(self, what):
        if self.state["match_running"]:
            raise MatchError(f"{what} impossible pendant un match")

    def _reset_match_fields(self):
        self.state.update({
            "match_running": False,
            "match_finished": False,
            "start_time": None,
            "timer_str": f"{MATCH_DURATION_S:.1f}",
        })

    def _start(self):
        self.state.update({
            "match_running": True,
            "match_finished": False,
            "start_time": self.clock(),
            "timer_str": f"{MATCH_DURATION_S:.1f}",
            "fsm_state": RUNNING,
        })
        self._changed()
        self.effects.on_match_start()

    def _end(self, reason):
        self.state.update({
            "match_running": False,
            "match_finished": True,
            "fsm_state": FINISHED,
        })
        if reason == "timer":
            self.state["timer_str"] = "0.0"
        self._changed()
        self.effects.on_match_end(reason)

    # ------------------------------------------------------------------
    # Démarrage du robot
    def ready(self, tirette_inserted):
        """Fin d'initialisation (thread stratégie prêt) : état initial de la tirette lu sur le GPIO."""
        with self._lock:
            self.state["fsm_state"] = WAIT_START
            if tirette_inserted:
                self.state.update({"tirette": TIR_REMOVE_FIRST, "tirette_msg": "REMOVE_TO_RESET"})
                self.effects.led("ANIM:BLINK:255,100,0,350")
            else:
                self.state.update({"tirette": TIR_READY, "tirette_msg": "WAITING"})
                self.show_team_color(force=True)
            self._changed()

    # ------------------------------------------------------------------
    # Tirette et arrêt d'urgence (thread boutons)
    def tirette_changed(self, inserted, bau_pressed=False):
        with self._lock:
            tir = self.state["tirette"]
            if inserted:
                # TRIGGERED hors match = la tirette retirée au départ du match précédent
                rearm = tir == TIR_READY or (tir == TIR_TRIGGERED and not self.running)
                if rearm and not bau_pressed:
                    # Après un match fini ou arrêté : remettre la tirette réarme directement
                    if self.phase in (FINISHED, STOPPED):
                        self._reset_match_fields()
                        self.state["fsm_state"] = WAIT_START
                        self.effects.on_reset()
                    if self.phase == WAIT_START:
                        self.state.update({"tirette": TIR_ARMED, "tirette_msg": "ARMED"})
                        self.effects.led("ANIM:BREATH:0,255,0")
                elif tir == TIR_REMOVE_FIRST:
                    self.state["tirette_msg"] = "REMOVE_TO_RESET"
                    self.effects.led("ANIM:BLINK:255,100,0,350")
            else:
                if tir == TIR_ARMED:
                    if self.phase == WAIT_START and not bau_pressed:
                        self.state["tirette"] = TIR_TRIGGERED
                        self._start()
                        return
                    self.state["tirette"] = TIR_READY
                elif tir in (TIR_REMOVE_FIRST, TIR_TRIGGERED):
                    self.state.update({"tirette": TIR_READY, "tirette_msg": "WAITING"})
                    if not self.running:
                        self.show_team_color()
            self._changed()

    def emergency_stop(self):
        """Arrêt d'urgence physique (BAU)."""
        with self._lock:
            self.state["match_running"] = False
            self.state["fsm_state"] = STOPPED
            self.state["tirette"] = TIR_REMOVE_FIRST
            self.effects.led("COLOR:255,0,0")
            self._changed()
            self.effects.on_stop()

    # ------------------------------------------------------------------
    # Ordres de l'interface (via la base)
    def start(self):
        """GO MATCH depuis l'interface (sans tirette)."""
        with self._lock:
            if self.running:
                return
            if self.phase in (FINISHED, STOPPED):
                self.effects.on_reset()
            self.state["tirette"] = TIR_TRIGGERED
            self._start()

    def stop(self):
        with self._lock:
            self.state["match_running"] = False
            self.state["fsm_state"] = STOPPED
            self.state["tirette"] = TIR_READY
            self._changed()
            self.effects.on_stop()

    def reset(self):
        with self._lock:
            self._reset_match_fields()
            self.state.update({"fsm_state": WAIT_START, "tirette": TIR_READY, "tirette_msg": "WAITING"})
            self._changed()
            self.effects.on_reset()
            self.show_team_color()

    # ------------------------------------------------------------------
    # Chrono (appelé ~10 Hz)
    def tick(self):
        with self._lock:
            if not self.running or not self.state["start_time"]:
                return
            remaining = MATCH_DURATION_S - (self.clock() - self.state["start_time"])
            if remaining <= 0 and not self.state["test_mode"]:
                self._end("timer")
                return
            timer_str = f"{remaining:.1f}"
            if timer_str != self.state["timer_str"]:
                self.state["timer_str"] = timer_str
                self._changed()

    def strategy_finished(self):
        """La stratégie a rendu la main. En mode test, ça termine le match ;
        sinon le match continue jusqu'aux 100 s (règlement)."""
        with self._lock:
            if self.running and self.state["test_mode"]:
                self._end("strategy")

    # ------------------------------------------------------------------
    # Réglages persistés (équipe, stratégie, mode test) : passent par la config
    def apply_config(self, changes):
        """Applique des modifications de config (dict pointé). Les clés du match sont refusées
        pendant un match. Renvoie les clés modifiées. Lève MatchError / ConfigError."""
        with self._lock:
            match_keys = {"team", "strat_mode", "static_strat", "test_mode", "strat_id"}
            if match_keys & set(changes):
                self._require_not_running("Changement d'équipe / de stratégie / du mode test")
            old_team = self.state.get("team")
            changed = self.config.update(changes)
            if changed:
                self._sync_from_config()
                self._changed()
                if "team" in changed and self.state["team"] != old_team:
                    self.show_team_color()
            return changed

    def toggle_team(self):
        team = "JAUNE" if self.state.get("team") == "BLEUE" else "BLEUE"
        return self.apply_config({"team": team})

    def set_battery_low(self, low):
        with self._lock:
            if bool(low) != bool(self.state.get("bat_low")):
                self.state["bat_low"] = bool(low)
                self._changed()
                if not low:
                    self.show_team_color()
