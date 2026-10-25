# strat/main_strat.py
import time
import importlib
import os
import glob
import sys
import ihm.shared as shared

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

def _load_strategy(strat_name):
    """Importe (ou recharge, pour prendre les modifications) le module de stratégie."""
    available = shared.strategies_list
    if strat_name not in available:
        available = discover_strategies()  # stratégie créée récemment
    if strat_name not in available:
        return None
    full_mod_path = f"strat.strategies.{strat_name}"
    if full_mod_path in sys.modules:
        print(f"[STRAT] Rechargement de {strat_name}...")
        return importlib.reload(sys.modules[full_mod_path])
    print(f"[STRAT] Import de {strat_name}...")
    return importlib.import_module(full_mod_path)


def strat_loop(robot):
    """Exécute la stratégie quand le match démarre, avec `robot` (RobotActions, créé une seule
    fois par main_robot.py). Ne modifie jamais l'état du match : c'est le rôle de shared.match
    (core/match_state.py) ; on lui signale seulement la fin."""
    print("[STRAT] Thread démarré.")
    last_scan = 0.0
    last_run_start = None  # start_time du dernier match exécuté (une exécution par match)

    while True:
        now = time.time()
        if now - last_scan >= 1.0 and shared.match.phase != "RUNNING":
            shared.strategies_list = discover_strategies()  # liste pour l'IHM, 1 Hz hors match
            last_scan = now

        if shared.match.phase != "RUNNING" or shared.state.get("start_time") == last_run_start:
            time.sleep(0.01)  # tirette / GO réactifs
            continue

        last_run_start = shared.state.get("start_time")
        strat_name = shared.state["strat_id"]
        print(f"[STRAT] GO ! Lancement : {strat_name}")
        try:
            mod = _load_strategy(strat_name)
            if mod is None:
                print(f"[STRAT] Erreur : stratégie '{strat_name}' inconnue ou fichier manquant !")
                shared.send_log(f"Stratégie '{strat_name}' introuvable", "err")
            else:
                mod.run(robot)
                print("[STRAT] Stratégie terminée.")
            shared.match.strategy_finished()  # en mode test : fin du match

            # Hors mode test, le match continue jusqu'aux 100 s (règlement).
            # On attend la fin de CE match (même start_time) : un STOP + nouveau départ
            # rapprochés ne doivent pas être confondus avec le match en cours.
            while shared.match.running and shared.state.get("start_time") == last_run_start:
                time.sleep(0.2)
        except Exception as e:
            # Exception("Stop") levée par _check_abort quand le match s'arrête : cas normal
            if shared.match.running:
                print(f"[STRAT] Erreur d'exécution : {e}")
                shared.send_log(f"Erreur stratégie : {e}", "err")
            robot.stop()
        print("[STRAT] Fini.")
