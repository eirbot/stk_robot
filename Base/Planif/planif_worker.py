#!/usr/bin/env python3
"""Planificateur de trajectoire de la base (lancé et relancé par base_stk : Base/Web/planif.go).

    uv run --project <racine du dépôt> python Base/Planif/planif_worker.py

ZMQ SUB tcp://localhost:STK_ZMQ_PLANIF_PORT (5557) : ce que la base lui relaie
    vision (caméra zénithale : adversaires, pierres), telemetry (pose fusionnée du robot, 10 Hz),
    lidar_frame (points du robot, repère table), nav_demande {id, cible, cfg}, nav_fin {id}
ZMQ PUSH tcp://localhost:STK_ZMQ_ROBOT_PORT (5555) : vers la base, qui relaie au robot / aux pages
    plan (10 Hz pendant une navigation), carte_planif (2 Hz : carte de coûts, prédictions, pierres)
Toute la logique est dans Rasp/core/navigation.py (le robot l'utilise aussi en secours).
"""

import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Rasp"))
from core.navigation import Navigateur  # noqa: E402

PERIODE_PLAN_S = 0.1
PERIODE_CARTE_S = 0.5


def traiter(nav, msg, t):
    """Un message relayé par la base -> navigateur. Renvoie les messages à renvoyer tout de suite."""
    kind, data = msg.get("type"), msg.get("data") or {}
    out = []
    if kind == "vision":
        nav.observer_vision(data, t)
    elif kind == "telemetry":
        try:
            nav.observer_pose(data["x"], data["y"], data["theta"], t)
        except (KeyError, TypeError, ValueError):
            pass
    elif kind == "lidar_frame":
        nav.observer_lidar(data.get("points") or [], t)
    elif kind == "nav_demande":
        try:
            nav.demander(data["id"], data["cible"], data.get("cfg"))
            if data.get("pose"):
                nav.observer_pose(*data["pose"][:3], t)
        except (KeyError, TypeError, ValueError):
            return out
        out.append(("plan", None))          # plan tout de suite, sans attendre la période
    elif kind == "nav_fin":
        nav.terminer(data.get("id"))
    return out


def tic(nav, t, dernier_plan, derniere_carte, forcer=False):
    """Messages périodiques : (liste de (type, data), dernier_plan, derniere_carte)."""
    out = []
    if nav.nav is not None and (forcer or t - dernier_plan >= PERIODE_PLAN_S):
        t0 = time.perf_counter()
        plan, change = nav.planifier(t)
        msg = nav.message_plan(t, plan, change, round((time.perf_counter() - t0) * 1000, 1))
        if msg:
            out.append(("plan", msg))
        dernier_plan = t
    if t - derniere_carte >= PERIODE_CARTE_S:
        out.append(("carte_planif", nav.message_carte(t)))
        derniere_carte = t
    return out, dernier_plan, derniere_carte


def main():
    import zmq  # ici : traiter() / tic() se testent sans pyzmq
    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.connect(f"tcp://localhost:{os.environ.get('STK_ZMQ_PLANIF_PORT', '5557')}")
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    push = ctx.socket(zmq.PUSH)
    push.setsockopt(zmq.SNDHWM, 10)
    push.setsockopt(zmq.LINGER, 0)
    push.connect(f"tcp://localhost:{os.environ.get('STK_ZMQ_ROBOT_PORT', '5555')}")
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)
    nav = Navigateur()
    dernier_plan = derniere_carte = 0.0
    print("[PLANIF] Planificateur de la base prêt", flush=True)

    def envoyer(kind, data):
        try:
            push.send_json({"type": kind, "data": data}, zmq.NOBLOCK)
        except zmq.Again:
            pass

    while True:
        forcer = False
        for sock, _ in poller.poll(20):
            while True:
                try:
                    raw = sock.recv_string(zmq.NOBLOCK)
                except zmq.Again:
                    break
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                forcer |= any(k == "plan" for k, _ in traiter(nav, msg, time.time()))
        try:
            msgs, dernier_plan, derniere_carte = tic(nav, time.time(), dernier_plan, derniere_carte, forcer)
        except Exception as e:  # noqa: BLE001 - le planificateur ne doit jamais tomber
            print(f"[PLANIF] Erreur : {e}", flush=True)
            continue
        for kind, data in msgs:
            envoyer(kind, data)


if __name__ == "__main__":
    main()
