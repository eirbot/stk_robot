# strat/main_strat.py
import time
import importlib
import os
import glob
import threading
import sys
import ihm.shared as shared
from strat.actions import RobotActions, EndOfMatchException, actionneurs

# Dossier des stratégies (relatif au main)
STRAT_DIR = "strat/strategies"

def discover_strategies():
    """
    Scanne les fichiers .py, charge les METADATA et retourne une liste.
    Recalculée à chaque appel pour voir les nouvelles strats.
    """
    strats = {}
    # On cherche tous les fichiers .py dans strat/strategies
    files = glob.glob(os.path.join(STRAT_DIR, "*.py"))
    
    # print(f"[STRAT] Recherche de stratégies dans {STRAT_DIR}...")
    
    for filepath in files:
        filename = os.path.basename(filepath)
        if filename == "__init__.py": continue
        
        # Nom du module pour l'import (ex: strat.strategies.strat_match_1)
        mod_name = filename[:-3] # Enlève .py
        full_mod_path = f"strat.strategies.{mod_name}"
        
        try:
            # On check si déjà chargé pour reload ou import
            if full_mod_path in sys.modules:
                mod = sys.modules[full_mod_path]
                # Note: On ne reload pas TOUT ici, trop lourd. On reload juste au moment du run.
            else:
                mod = importlib.import_module(full_mod_path)

            meta = getattr(mod, "METADATA", {"name": mod_name})
            strats[mod_name] = meta
            
        except Exception as e:
            print(f"   [ERREUR] Impossible de charger {filename}: {e}")

    return strats

def strat_loop():
    print("[STRAT] Thread démarré.")
    robot = RobotActions()
    
    # On initialise l'état dans le partagé pour l'affichage Web
    shared.state["fsm_state"] = "WAIT_START"
    
    last_scan = 0.0
    while True:
        # On synchronise l'état local avec l'IHM à chaque tour de boucle
        current_state = shared.state["fsm_state"]

        # --- ETAT 1 : ATTENTE ---
        if current_state == "WAIT_START":
            # Mise à jour périodique de la liste pour l'IHM
            # (Ex: toutes les secondes ou juste quand on est en wait)
            # Pour faire simple : on refresh à chaque tour de boucle lent? Non trop bourrin.
            # On le fait juste avant de démarrer ? Non car l'IHM en a besoin.
            # Disons qu'on refresh refresh souvent en mode WAIT
            # Scan des stratégies limité à 1 Hz, mais tirette/start réactifs (boucle à 100 Hz)
            now = time.time()
            if now - last_scan >= 1.0:
                shared.strategies_list = discover_strategies()
                last_scan = now

            if shared.state["match_running"]:
                print(f"[STRAT] GO ! Lancement : {shared.state['strat_id']}")
                robot.is_returning = False
                # Le match précédent a pu bloquer les actionneurs (fin à 100 s / STOP)
                if actionneurs:
                    actionneurs.debloquer()
                shared.state["fsm_state"] = "RUNNING" # Update Etat
            else:
                time.sleep(0.01)

        # --- ETAT 2 : MATCH ---
        elif current_state == "RUNNING":
            try:
                # On récupère l'ID (qui est maintenant le nom du fichier, ex: "strat_match_1")
                strat_name = shared.state["strat_id"]
                
                # Import dynamique ET Reload
                # On ré-explore pour être sûr que la strat existe (cas création récente)
                available = shared.strategies_list
                if strat_name not in available:
                    available = discover_strategies()
                
                if strat_name in available:
                    full_mod_path = f"strat.strategies.{strat_name}"
                    
                    if full_mod_path in sys.modules:
                        print(f"[STRAT] Reloading {strat_name}...")
                        mod = importlib.reload(sys.modules[full_mod_path])
                    else:
                        print(f"[STRAT] Importing {strat_name}...")
                        mod = importlib.import_module(full_mod_path)
                    
                    # Run
                    mod.run(robot)

                    if shared.state.get("test_mode", False):
                        # Pas de 100 s en mode test : la fin de la strat termine le match
                        print("[STRAT] Mode test : stratégie terminée, fin du match.")
                        shared.state["match_running"] = False
                        shared.state["match_finished"] = True

                    # --- ATTENTE FIN DE MATCH (90s) ---
                    # Si la stratégie finit avant les 90s, on attend patiemment le rappel à la base
                    print("[STRAT] Stratégie terminée. Attente du rappel à la base (90s)...")
                    while shared.state["match_running"]:
                        robot._check_time() # Lèvera EndOfMatchException à 90s
                        time.sleep(1)
                else:
                    print(f"[STRAT] Erreur : Stratégie '{strat_name}' inconnue ou fichier manquant !")
                
                print("[STRAT] Fini.")

            except EndOfMatchException:
                print("[STRAT] ⚠️ TIMEOUT -> RETOUR BASE")
                robot.GoBase()
            except Exception as e:
                print(f"[STRAT] Erreur d'exécution : {e}")
                robot.stop()
            finally:
                # Ne pas écraser un état si l'IHM a déjà fait un RESET ou un STOP
                if shared.state["fsm_state"] == "RUNNING":
                    shared.state["fsm_state"] = "FINISHED"

        # --- ETAT 3 : FINI ---
        elif current_state == "FINISHED":
            if not shared.state["match_running"]:
                shared.state["fsm_state"] = "WAIT_START"
            time.sleep(0.5)

        # --- ETAT 4 : ARRÊT D'URGENCE / STOP ---
        elif current_state == "STOPPED":
            # Attente du RESET depuis l'IHM (le /reset remet fsm_state = 'WAIT_START')
            time.sleep(0.5)