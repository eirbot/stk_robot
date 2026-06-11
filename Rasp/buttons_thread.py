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

        # --- INITIAL STATE CHECK (Tirette) ---
        # Si on démarre sans tirette (1), on est prêt à l'insérer (WAIT_INSERT).
        # Si on démarre avec tirette (0), on attend qu'elle soit retirée (WAIT) -> Logic "REMOVE_TO_RESET" handled in loop
        if self.last_states[PIN_TIRETTE] == TIRETTE_REMOVED_VAL:
             print("[BUTTONS] Tirette ABSENTE au démarrage -> Prêt à armer.")
             shared.state['tirette'] = "WAIT_INSERT"
             shared.state['tirette_msg'] = "WAITING"
             shared.send_led_cmd("COLOR:0,0,255")
        else:
             print("[BUTTONS] Tirette PRÉSENTE au démarrage -> Veuillez retirer !")
             shared.state['tirette'] = "WAIT"
             shared.state['tirette_msg'] = "REMOVE_TO_RESET"
             shared.send_led_cmd("ANIM:BLINK:255,100,0,350")

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
                    # BAU Pressed (Closed to 3.3V) -> 1
                    if val == 1: 
                        print("[BUTTONS] 🚨 ARRET D'URGENCE (BAU) !")
                        shared.state['match_running'] = False
                        shared.state['fsm_state'] = "STOPPED"
                        shared.send_led_cmd("COLOR:255,0,0") 
                        # Reset tirette state to force re-arm
                        shared.state['tirette'] = "WAIT" 
                    else:
                         print("[BUTTONS] BAU Relâché.")

                elif name == "TIRETTE":
                    # TIRETTE FSM : WAIT -> ARMED -> TRIGGERED
                    # Updated logic: 0 = Inserted, 1 = Removed
                    
                    is_inserted = (val == TIRETTE_INSERTED_VAL)
                    
                    current_state = shared.state.get('tirette', 'WAIT')
                    
                    if current_state == "WAIT" or current_state == "NON-ARMED":
                        if is_inserted:
                             # Warn user to remove
                             if shared.state.get('tirette_msg') != "REMOVE_TO_RESET":
                                 print("[BUTTONS] ⚠️ Sécurité : Veuillez RETIRER la tirette !")
                                 shared.state['tirette_msg'] = "REMOVE_TO_RESET"
                                 shared.send_led_cmd("ANIM:BLINK:255,100,0,350")
                        else:
                             # Tirette is Removed. Ready to ARM.
                             print("[BUTTONS] ⏳ Tirette ABSENTE -> Prêt à armer (Bleu)")
                             shared.state['tirette'] = "WAIT_INSERT"
                             shared.state['tirette_msg'] = "WAITING"
                             shared.send_led_cmd("COLOR:0,0,255") # On arrête le clignotement par un bleu fixe


                    elif current_state == "WAIT_INSERT":
                        if is_inserted:
                             print("[BUTTONS] ✅ Tirette INSÉRÉE -> ROBOT ARMÉ !")
                             shared.state['tirette'] = "ARMED"
                             shared.state['match_running'] = False
                             # LED Vert Breath (Green=0,255,0)
                             shared.send_led_cmd("ANIM:BREATH:0,255,0") 

                    elif current_state == "ARMED":
                        if not is_inserted: # Removed
                             print("[BUTTONS] 🚀 TIRETTE RETIRÉE -> MATCH START !")
                             shared.state['tirette'] = "TRIGGERED"
                             shared.state['match_running'] = True
                             shared.state['start_time'] = time.time()
                             shared.send_led_cmd("PLAY:match_start")
                             
                    elif current_state == "TRIGGERED":
                         # Match is running. If inserted again -> Stop? Or Just ignore?
                         # Usually we ignore or treat as stop. Let's ignore for now or log.
                         if is_inserted:
                             print("[BUTTONS] Tirette remise (Info).")
                             # Could allow re-arming if match finished?

    # --- ACTIONS ---
    def action_team(self):
        new_team = 'JAUNE' if shared.state['team'] == 'BLEUE' else 'BLEUE'
        print(f"[BUTTONS] Changement Equipe -> {new_team}")
        shared.state['team'] = new_team
        
        # Visual Update
        if new_team == 'JAUNE': shared.send_led_cmd("COLOR:255,160,0")
        else: shared.send_led_cmd("COLOR:0,0,255")

    def action_strat(self):
        # Cycle through strategies
        current_id = shared.state.get('strat_id', '')
        
        # Reload strategies if empty (maybe files were added late)
        if not shared.strategies_list:
             print("[BUTTONS] Liste stratégies vide, tentative de reload...")
             # Assuming shared could initiate reload or we just warn
             # For now, just warn.
        
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
        print(f"[BUTTONS] Changement Stratégie -> {new_id}")
        shared.state['strat_id'] = new_id
        # Optional: Blink LEDs?

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
