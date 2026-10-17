# buttons_thread.py
import time
import threading
import sys
import os
import random
import ihm.shared as shared
from strat.actions import actionneurs

# Try Importing GPIO (Mock if not available)
try:
    import RPi.GPIO as GPIO
    MOCK_GPIO = False
except ImportError:
    print("[BUTTONS] RPi.GPIO non trouvé. Mode simulation (MOCK).")
    MOCK_GPIO = True
    class MockGPIO:
        BOARD = "BOARD"
        IN = "IN"
        OUT = "OUT"
        PUD_UP = "PUD_UP"
        PUD_DOWN = "PUD_DOWN"
        def setmode(self, mode): pass
        def setup(self, pin, mode, pull_up_down=None): pass
        def input(self, pin): return 1 # Default HIGH (Pull-up)
        def cleanup(self): pass
    GPIO = MockGPIO()

# === CONFIGURATION PINS (BOARD MODE) ===
PIN_TEAM   = 11
PIN_STRAT  = 13
# PIN_REBOOT = 15 # A ne pas utiliser, il est utilisé par launcher.py
PIN_INIT   = 16
PIN_BAU    = 18
PIN_TIRETTE= 22

# Tirette Logic Configuration
# User says "inverted" -> Assuming Active Low (Switch to GND) with Pull-Up.
# Removed (Switch Open) = 1
# Inserted (Switch Closed) = 0
TIRETTE_REMOVED_VAL = 1
TIRETTE_INSERTED_VAL = 0

class ButtonsThread:
    def __init__(self):
        self.running = True
        self.last_states = {
            PIN_TEAM: 1,
            PIN_STRAT: 1,
            # PIN_REBOOT: 1,
            PIN_INIT: 1,
            PIN_BAU: 1,
            PIN_TIRETTE: 1 
        }
        # Debounce counters (simple software debounce)
        self.counters = { k: 0 for k in self.last_states }
        self.DEBOUNCE_THRESH = 3 # ticks (at 20Hz approx)

    def setup(self):
        if not MOCK_GPIO:
            GPIO.setmode(GPIO.BOARD)
            
            # Group 1: Buttons 1-4 (Direct -> Internal Pull-UP -> Active LOW)
            # Switch connects Pin to GND. Default=1, Pressed=0.
            pins_active_low = [PIN_TEAM, PIN_STRAT, PIN_INIT]
            for p in pins_active_low:
                GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                
            # Group 2: BAU (External Pull-Down -> Active HIGH)
            GPIO.setup(PIN_BAU, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            # Group 3: Tirette (Active Low - User Inverted)
            GPIO.setup(PIN_TIRETTE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                
            print(f"[BUTTONS] Configured - Low: {pins_active_low}, BAU High, Tirette Low")

    def loop(self):
        self.setup()
        print("[BUTTONS] Thread démarré (Mode corrected).")
        
        # Initialize last states after setup
        # Note: If Tirette is inserted (Closed), default read is 1.
        self.last_states = {
             PIN_TEAM: 1, PIN_STRAT: 1, PIN_INIT: 1, # Pull-UP default 1
             PIN_BAU: 0, PIN_TIRETTE: 0 # Pull-DOWN default 0
        }
        if not MOCK_GPIO:
             for p in [PIN_BAU, PIN_TIRETTE]: self.last_states[p] = GPIO.input(p)

        # --- ÉTAT INITIAL DE LA TIRETTE ---
        # Présente au démarrage : il faudra la retirer avant de pouvoir armer (core/match_state.py)
        tirette_inserted = self.last_states[PIN_TIRETTE] == TIRETTE_INSERTED_VAL
        print(f"[BUTTONS] Tirette {'PRÉSENTE (à retirer)' if tirette_inserted else 'ABSENTE (prêt à armer)'} au démarrage.")
        shared.match.ready(tirette_inserted)

        while self.running:
            # Check Inputs (Active Low Buttons)
            self.check_button(PIN_TEAM, self.action_team, active_low=True)
            self.check_button(PIN_STRAT, self.action_strat, active_low=True)
            # PIN_REBOOT est géré par launcher.py
            self.check_button(PIN_INIT, self.action_init, active_low=True)
            
            # Special Handling for Switches (Active High)
            self.check_switch_active_high(PIN_BAU, "BAU")
            self.check_switch_active_high(PIN_TIRETTE, "TIRETTE")

            time.sleep(0.05) 

        if not MOCK_GPIO:
            GPIO.cleanup()

    def check_button(self, pin, callback, active_low=True):
        """ Detects Press. 
            If active_low=True:  Falling Edge (1->0).
            If active_low=False: Rising Edge (0->1).
        """
        val = GPIO.input(pin)
        
        if val != self.last_states[pin]:
            # print(f"[DEBUG] Pin {pin} raw change -> {val}") # Debug pour voir si le bouton réagit
            self.counters[pin] += 1
            if self.counters[pin] >= self.DEBOUNCE_THRESH:
                self.last_states[pin] = val
                self.counters[pin] = 0
                
                # Trigger Condition
                trigger = (val == 0) if active_low else (val == 1)
                
                if trigger:
                    print(f"[BUTTONS] Button {pin} Triggered!")
                    callback()
        else:
            self.counters[pin] = 0

    def check_switch_active_high(self, pin, name):
        """ Handles State Changes for Active High switches (0=Open, 1=Closed/3.3V) """
        val = GPIO.input(pin)
        
        if val != self.last_states[pin]:
            self.counters[pin] += 1
            if self.counters[pin] >= self.DEBOUNCE_THRESH:
                self.last_states[pin] = val
                self.counters[pin] = 0
                
                if name == "BAU":
                    # BAU enfoncé (fermé sur 3,3 V) -> 1
                    if val == 1:
                        print("[BUTTONS] ARRÊT D'URGENCE (BAU) !")
                        shared.match.emergency_stop()
                    else:
                        print("[BUTTONS] BAU relâché.")

                elif name == "TIRETTE":
                    inserted = (val == TIRETTE_INSERTED_VAL)
                    before = shared.state.get("tirette")
                    shared.match.tirette_changed(inserted, bau_pressed=self.last_states[PIN_BAU] == 1)
                    print(f"[BUTTONS] Tirette {'insérée' if inserted else 'retirée'} : "
                          f"{before} -> {shared.state.get('tirette')} (match : {shared.match.phase})")

        else:
            self.counters[pin] = 0

    # --- ACTIONS ---
    def action_team(self):
        try:
            shared.match.toggle_team()
            print(f"[BUTTONS] Équipe -> {shared.state['team']}")
        except shared.MatchError as e:
            print(f"[BUTTONS] Changement d'équipe refusé : {e}")

    def action_strat(self):
        # Cycle through strategies
        current_id = shared.state.get('strat_id', '')
        
        if not shared.strategies_list:
             print("[BUTTONS] Liste stratégies vide, impossible de changer.")
        
        available = list(shared.strategies_list.keys())
        if not available:
             print(f"[BUTTONS] Aucune stratégie disponible. (Liste: {shared.strategies_list})")
             return
             
        try:
            curr_idx = available.index(current_id)
            next_idx = (curr_idx + 1) % len(available)
        except ValueError:
            next_idx = 0
            
        new_id = available[next_idx]
        _, err = shared.update_config_from_server({"static_strat": new_id})
        print(f"[BUTTONS] Stratégie -> {new_id}" + (f" refusée : {err}" if err else ""))

    def action_init(self):
        print("[BUTTONS] INIT des Actionneurs !")
        if actionneurs:
            # On lance l'init dans un thread pour ne pas bloquer la boucle des boutons
            threading.Thread(target=actionneurs.pose_match, daemon=True).start()
        else:
            print("[BUTTONS] ⚠️ Actionneurs non connectés, impossible d'init.")
        

def run_buttons_loop():
    bt = ButtonsThread()
    bt.loop()
