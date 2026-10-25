#!/usr/bin/env python3
"""Image du robot vu de dessus pour le Strat Studio, rendue à partir de son modèle MuJoCo.

    uv run --with websockets python tools/rendu_robot_dessus.py [URL de la base]

Il faut une base qui tourne (par défaut http://127.0.0.1:8080) : elle sert la page outil
static/tools/rendu_robot.html et les modèles (/models/). Chromium (headless) rend la page,
et l'image du canvas (fond transparent) est écrite dans Base/Web/static/img/robot_dessus.png.
À relancer quand le modèle du robot change (et mettre à jour ?v= dans templates/blockly.html).
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

import websockets

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "Base", "Web", "static", "img", "robot_dessus.png")
PORT = 9334


async def render(base_url):
    profile = tempfile.mkdtemp(prefix="rendu_robot_")
    chrome = subprocess.Popen(["chromium", "--headless=new", "--no-sandbox", "--use-angle=swiftshader",
                               "--enable-unsafe-swiftshader", f"--user-data-dir={profile}",
                               f"--remote-debugging-port={PORT}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
                break
            except OSError:
                time.sleep(0.2)
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        async with websockets.connect(ws_url, max_size=100_000_000) as ws:
            ids = iter(range(1, 10_000))

            async def cmd(method, params=None):
                i = next(ids)
                await ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == i:
                        return msg.get("result", {})

            async def evaluate(expr):
                r = await cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True})
                return r.get("result", {}).get("value")

            await cmd("Page.navigate", {"url": base_url.rstrip("/") + "/static/tools/rendu_robot.html"})
            deadline = time.time() + 120
            title = ""
            while time.time() < deadline:
                title = await evaluate("document.title") or ""
                if title.startswith(("PRET", "ERREUR")):
                    break
                await asyncio.sleep(0.5)
            if not title.startswith("PRET"):
                raise SystemExit(f"Rendu impossible : {title or 'délai dépassé'}")
            data = await evaluate("document.querySelector('canvas').toDataURL('image/png')")
            with open(OUT, "wb") as f:
                f.write(base64.b64decode(data.split(",", 1)[1]))
            print(f"{OUT} ({title[5:]} px)")
    finally:
        chrome.terminate()


if __name__ == "__main__":
    asyncio.run(render(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"))
