#!/usr/bin/env python3
"""Génère Base/Web/static/icons/win95.svg : icônes pixel art 16x16 façon Windows 95
(dessins maison, palette 16 couleurs de Windows ; pas les icônes de Microsoft).

Chaque icône est une grille de 16 lignes de 16 caractères, une lettre = une couleur
(voir PALETTE), '.' = transparent. Modifier une grille puis relancer :
    tools/win95_icons.py
Utilisation : <svg class="w95-ico"><use href="/static/icons/win95.svg#w95-NOM"></use></svg>
(afficher en 16 ou 32 px pour garder des pixels nets).
"""

import os

PALETTE = {
    "k": "#000000", "w": "#ffffff", "g": "#c0c0c0", "d": "#808080",
    "r": "#ff0000", "R": "#800000", "y": "#ffff00", "Y": "#808000",
    "G": "#00ff00", "e": "#008000", "b": "#0000ff", "n": "#000080",
    "c": "#00ffff", "t": "#008080", "m": "#ff00ff", "p": "#800080",
    "h": "#e0b060",
}

ICONS = {
    # Poste de travail
    "home": [
        "................",
        ".kkkkkkkkkkkkkk.",
        ".kggggggggggggk.",
        ".kgkkkkkkkkkkgk.",
        ".kgkttttttttkgk.",
        ".kgkttwtttttkgk.",
        ".kgktwttttttkgk.",
        ".kgkttttttttkgk.",
        ".kgkkkkkkkkkkgk.",
        ".kggggggggggggk.",
        ".kkkkkkkkkkkkkk.",
        "......kddk......",
        "...kkkkkkkkkk...",
        "..kgggggggGegk..",
        "..kddddddddddk..",
        "...kkkkkkkkkk...",
    ],
    # Manette d'arcade
    "joystick": [
        "................",
        ".....kkkk.......",
        "....krrrrk......",
        "...krrwrrrk.....",
        "...krwrrrrk.....",
        "...krrrrrRk.....",
        "....kRRRRk......",
        ".....kkkk.......",
        "......kk........",
        "......kk........",
        "..kkkkkkkkkkkk..",
        ".kwwwwwwwwwwwwdk",
        ".kwggggggggrrgdk",
        ".kwggggggggRRgdk",
        ".kdddddddddddddk",
        "..kkkkkkkkkkkkk.",
    ],
    # Carte avec punaise
    "map": [
        "................",
        ".kkkkkkkkkkkkkk.",
        ".kbbbbeeebbbbbk.",
        ".kbbbeeeeebbbbk.",
        ".kbbeeehheebbbk.",
        ".kbbeeerreeebbk.",
        ".kbbbeerreeebbk.",
        ".kbbbbeeRhebbbk.",
        ".kbbbbbeeebbbbk.",
        ".kbbbbbbbbbeebk.",
        ".kbbbbbbbbeeeek.",
        ".kbbbbbbbbbeebk.",
        ".kbbbbbbbbbbbbk.",
        ".kkkkkkkkkkkkkk.",
        "................",
        "................",
    ],
    # Coccinelle (debug)
    "bug": [
        "................",
        "....k......k....",
        ".....k....k.....",
        "......kkkk......",
        ".....kkwkkk.....",
        "..k.krrrkrrrk.k.",
        "...krrkrkrkrrk..",
        "kkkrrrrrkrrrrrkk",
        "...krkrrkrrkrk..",
        "..krrrrrkrrrrrk.",
        "kkkrrkrrkrrkrrkk",
        "...krrrrkrrrrk..",
        "..k.krrrkrrrk.k.",
        ".....kkkkkk.....",
        "....k......k....",
        "................",
    ],
    # Pièces de puzzle (stratégie)
    "puzzle": [
        "................",
        ".kkkkkkkkkkkkkk.",
        ".krrrrrkbbbbbbk.",
        ".krrrrrkbbbbbbk.",
        ".krrrrrrrbbbbbk.",
        ".krrrrrrrbbbbbk.",
        ".krrrrrkbbbbbbk.",
        ".kkkyykkkkkeekk.",
        ".kyyyyykeeeeeek.",
        ".kyyyyykeeeeeek.",
        ".kyyyyyyyeeeeek.",
        ".kyyyyyyyeeeeek.",
        ".kyyyyykeeeeeek.",
        ".kyyyyykeeeeeek.",
        ".kkkkkkkkkkkkkk.",
        "................",
    ],
    # Ampoule (LED)
    "bulb": [
        "................",
        ".....kkkkk......",
        "....kyyyyyk.....",
        "...kyywyyyyk....",
        "...kywyyyyyk....",
        "...kyyyyyyyk....",
        "...kyyyyyyYk....",
        "....kyyyyYk.....",
        ".....kyyYk......",
        ".....kgggk......",
        ".....kdddk......",
        ".....kgggk......",
        ".....kdddk......",
        "......kkk.......",
        "................",
        "................",
    ],
    # Haut-parleur et note (sons)
    "sound": [
        "................",
        "...........n....",
        "...........nn...",
        "......kk...n.n..",
        ".....kgk...n..n.",
        "....kggk...n....",
        "kkkkgggk.nnn....",
        "kwwkgggk.nnn....",
        "kwgkgggk........",
        "kwgkgggk........",
        "kddkgggk........",
        "kkkkgggk........",
        "....kggk........",
        ".....kgk........",
        "......kk........",
        "................",
    ],
    # Pellicule (replay)
    "film": [
        "................",
        "................",
        "kkkkkkkkkkkkkkkk",
        "kwkkwkkwkkwkkwkk",
        "kkkkkkkkkkkkkkkk",
        "kcccckcccckcccck",
        "kcccckccyckcccck",
        "kcccckcccckcccck",
        "keeeekeeeekeeeek",
        "keeeekeeeekeeeek",
        "kkkkkkkkkkkkkkkk",
        "kwkkwkkwkkwkkwkk",
        "kkkkkkkkkkkkkkkk",
        "................",
        "................",
        "................",
    ],
    # Palette de peintre (thèmes)
    "palette": [
        "................",
        ".....kkkkkk.....",
        "...kkhhhhhhkk...",
        "..khhrrhhbbhhk..",
        ".khhrrrhhbbbhhk.",
        ".khhhrhhhhbhhhk.",
        "khhehhhhhhhhhhk.",
        "kheeehhhhhhkkk..",
        "khhehhhhhhk.....",
        "khhhhhhhhk......",
        "khmmhhhhhk......",
        ".kmmmhhhhhk.....",
        ".khmhhyyhhhk....",
        "..khhhyyyhhk....",
        "...kkhhhhkk.....",
        ".....kkkk.......",
    ],
    # Bouton marche/arrêt
    "power": [
        "................",
        ".....kkkkkk.....",
        "...kkrrrrrrkk...",
        "..krrrrwwrrrrk..",
        ".krrrwrwwrwrrrk.",
        ".krrwrrwwrrwrrk.",
        "krrwrrrwwrrrwrrk",
        "krrwrrrwwrrrwrrk",
        "krrwrrrrrrrrwrrk",
        "krrwrrrrrrrrwrrk",
        ".krrwrrrrrrwrrk.",
        ".krrrwwwwwwrrrk.",
        "..krrrrrrrrrrk..",
        "...kkrrrrrrkk...",
        ".....kkkkkk.....",
        "................",
    ],
    # Tête de robot
    "robot": [
        "................",
        ".......kk.......",
        ".......rr.......",
        ".......kk.......",
        "..kkkkkkkkkkkk..",
        ".kggggggggggggk.",
        ".kgkkkggggkkkgk.",
        ".kgkcckggkcckgk.",
        ".kgkkkggggkkkgk.",
        "kkggggggggggggkk",
        "kdggggggggggggdk",
        "kkggkkkkkkkkggkk",
        ".kggkwkwkwkwggk.",
        ".kggkkkkkkkkggk.",
        ".kggggggggggggk.",
        "..kkkkkkkkkkkk..",
    ],
    # Appareil photo (caméras)
    "camera": [
        "................",
        "................",
        "................",
        "....kkkkk.......",
        "...kdddddk......",
        ".kkkkkkkkkkkkkk.",
        ".kggggkkkkggrgk.",
        ".kgggkddddkgggk.",
        ".kggkdbbbbdkggk.",
        ".kggkdbwbbdkggk.",
        ".kggkdbbbbdkggk.",
        ".kgggkddddkgggk.",
        ".kddddkkkkddddk.",
        ".kkkkkkkkkkkkkk.",
        "................",
        "................",
    ],
    # Fenêtre avec courbe (conso & logs)
    "chart": [
        "................",
        "kkkkkkkkkkkkkkkk",
        "knnnnnnnnnnnnnnk",
        "kwwwwwwwwwwwwwwk",
        "kwwwwwwwwwwwwrwk",
        "kwwwwwwwwwwwrwwk",
        "kwwwwwrwwwwrwwwk",
        "kwwwwrwrwwrwwwwk",
        "kwwwrwwwrrwwwwwk",
        "kwwrwwwwwwwwwwwk",
        "kwrwwwwwwwwwwwwk",
        "kwwwwwwwwwwwwwwk",
        "kwdddddddddddddk",
        "kkkkkkkkkkkkkkkk",
        "................",
        "................",
    ],
    # Engrenage (système)
    "gear": [
        "................",
        "......kkkk......",
        "..kk..kggk..kk..",
        "..kgkkkggkkkgk..",
        "...kgwggggggk...",
        "...kgwgkkgggk...",
        ".kkkggk..kggkkk.",
        ".kgwggk..kggggk.",
        ".kggggk..kggddk.",
        ".kkkggk..kgdkkk.",
        "...kgggkkgddk...",
        "...kggggggddk...",
        "..kgkkkggkkkdk..",
        "..kk..kddk..kk..",
        "......kkkk......",
        "................",
    ],
    # Invite MS-DOS (console)
    "dos": ["", "kkkkkkkkkkkkkkkk", "knnnnnnnnnnnnnnk", "kkkkkkkkkkkkkkkk", "kkkkkkkkkkkkkkkk",
            "kkgkkkkkkkkkkkkk", "kkkgkkkkkkkkkkkk", "kkkkgkkkkkkkkkkk", "kkkgkkkkkkkkkkkk",
            "kkgkkkgggggkkkkk", "kkkkkkkkkkkkkkkk", "kkkkkkkkkkkkkkkk", "", "", "", ""],
    # --- Boîtes de dialogue (MessageBox) ---
    "error": ["", ".....kkkkkk", "...kkrrrrrrkk", "..krrrrrrrrrrk", ".krrwwrrrrwwrrk", ".krrwwwrrwwwrrk",
              "krrrrwwwwwwrrrrk", "krrrrrwwwwrrrrrk", "krrrrrwwwwrrrrrk", "krrrrwwwwwwrrrrk",
              ".krrwwwrrwwwrrk", ".krrwwrrrrwwrrk", "..krrrrrrrrrrk", "...kkrrrrrrkk", ".....kkkkkk", ""],
    "info": ["", "....kkkkkkkk", "..kkwwwwwwwwkk", ".kwwwwwbbwwwwwk", "kwwwwwwbbwwwwwwk", "kwwwwwwwwwwwwwwk",
             "kwwwwwbbbwwwwwwk", "kwwwwwwbbwwwwwwk", "kwwwwwwbbwwwwwwk", ".kwwwwwbbwwwwwk",
             "..kkwwbbbbwwkk", "....kkwwwkkk", "......kwwk", ".......kwk", "........kk", ""],
    "question": ["", "....kkkkkkkk", "..kkwwwwwwwwkk", ".kwwwwbbbbwwwwk", "kwwwwbbwwbbwwwwk",
                 "kwwwwwwwwbbwwwwk", "kwwwwwwwbbwwwwwk", "kwwwwwwbbwwwwwwk", "kwwwwwwbbwwwwwwk",
                 ".kwwwwwwwwwwwwk", "..kkwwwbbwwwkk", "....kkwwwkkk", "......kwwk", ".......kwk", "........kk", ""],
    # --- Boutons ---
    "play": ["", "..kk", "..kGkk", "..kGGGkk", "..kGGGGGkk", "..kGGGGGGGkk", "..kGGGGGGGGGkk",
             "..kGGGGGGGGGGGk", "..kGGGGGGGGGeek", "..kGGGGGGGeekk", "..kGGGGGeekk", "..kGGGeekk",
             "..kGeekk", "..kekk", "..kk", ""],
    "stop": ["", ".....kkkkkk", "....krrrrrrk", "...krrrrrrrrk", "..krrrrrrrrrrk", ".krrrrrrrrrrrrk",
             ".krrrrrrrrrrrrk", ".krwwwwwwwwwwrk", ".krwwwwwwwwwwrk", ".krrrrrrrrrrrrk", ".kRrrrrrrrrrrRk",
             "..kRrrrrrrrrRk", "...kRRrrrrRRk", "....kRRRRRRk", ".....kkkkkk", ""],
    "save": ["", "kkkkkkkkkkkkkkk", "knnwwwwwwwwwnnk", "knnwddddddddnnk", "knnwwwwwwwwwnnk",
             "knnwddddddddnnk", "knnwwwwwwwwwnnk", "knnnnnnnnnnnnnk", "knnnggggggggnnk", "knnnggkkggggnnk",
             "knnnggkkggggnnk", "knnnggkkggggnnk", "kknnggggggggnnk", ".kkkkkkkkkkkkkk", "", ""],
    "folder": ["", "", ".kkkk", "khhhhk", "khhhhhkkkkkkk", "khhhhhhhhhhhk", "khhhhkkkkkkkkkk",
               "khhhkyyyyyyyyyk", "khhkyyyyyyyyyk", "khhkyyyyyyyyyk", "khkyyyyyyyyyk", "khkyyyyyyyyyk",
               "kkyyyyyyyyyk", "kkkkkkkkkkkk", "", ""],
    "trash": ["", "...kkkkkkkkkk", "..kwwwwwwwwwwk", "..kkkkkkkkkkkk", "...kgdgdgdgdk", "...kdgdgdgdgk",
              "...kgdgeedgdk", "...kdgeggegdk", "...kgdgdedgdk", "...kdgdeedggk", "...kgdgdgdgdk",
              "....kdgdgdgk", "....kkkkkkkk", "", "", ""],
    "refresh": ["", ".....kkkkk", "...kkbbbbbkk.k", "..kbbbkkkbbbkbk", ".kbbk...kbbbbbk", ".kbk.....kbbbbk",
                "kbbk....kbbbbbk", "kbk.....kkkkkkk", "kkkkkkk.....kbk", "kbbbbbk....kbbk", "kbbbbk.....kbk",
                "kbbbbbk...kbbk", "kbkbbbkkkbbbk", ".k.kkbbbbbkk", ".....kkkkk", ""],
    "zap": ["", "........kkkk", ".......kyyyk", "......kyyyk", ".....kyyyk", "....kyyyk", "...kyyyykkkk",
            "..kyyyyyyyyk", "..kkkkkyyyk", "......kyyk", ".....kyyk", "....kyyk", "...kyyk", "..kyk",
            "..kk", ""],
    "radar": ["", ".....kkkkkk", "...kkeeeeeekk", "..keeeeGeeeeek", ".keeeeeGeeeeeek", ".keeeeeGeeeGeek",
              "keeeeeeGeeGeeeek", "keeeeeeGeGeeeeek", "kGGGGGGGGeeeeeek", "keeeeeeGeeeeeeek",
              ".keeeeeGeeeeeek", ".keeyeeGeeeeeek", "..keeeeGeeeeek", "...kkeeeeeekk", ".....kkkkkk", ""],
    "target": ["", ".....kkkkkk", "...kkrrrrrrkk", "..krrwwwwwwrrk", ".krwwrrrrrrwwrk", ".krwrrwwwwrrwrk",
               "krwrrwwrrwwrrwrk", "krwrwwrrrrwwrwrk", "krwrwwrrrrwwrwrk", "krwrrwwrrwwrrwrk",
               ".krwrrwwwwrrwrk", ".krwwrrrrrrwwrk", "..krrwwwwwwrrk", "...kkrrrrrrkk", ".....kkkkkk", ""],
    # Navigateur : « e » bleu et son orbite jaune
    "ie": [
        "...........yyy..",
        ".....nnnnn....y.",
        "...nnbbbbbnn..y.",
        "..nbbcnnnbbbn.y.",
        ".nbbcn...nbbbny.",
        ".nbbn.....nbbn..",
        "nbbbnnnnnnnbbbn.",
        "nbbbbbbbbbbbbbn.",
        "nbbbnnnnnnnnnn..",
        "nbbbn...........",
        "ynbbbn.....nnn..",
        "y.nbbbnnnnnbbn..",
        "y..nnbbbbbbbn...",
        ".y...nnnnnnn....",
        "..yyy...........",
        "",
    ],
    # Calculatrice
    "calc": [
        "..kkkkkkkkkkkk..",
        "..kggggggggggk..",
        "..kgkkkkkkkkgk..",
        "..kgkGGGGGGkgk..",
        "..kgkkkkkkkkgk..",
        "..kggggggggggk..",
        "..kgwkgwkgwkgk..",
        "..kgddgddgddgk..",
        "..kggggggggggk..",
        "..kgwkgwkgrkgk..",
        "..kgddgddgRRgk..",
        "..kggggggggggk..",
        "..kgwkgwkgrkgk..",
        "..kgddgddgRRgk..",
        "..kggggggggggk..",
        "..kkkkkkkkkkkk..",
    ],
    # Démineur : mine
    "mine": [
        "",
        ".......k",
        ".......k",
        "...k.kkkkk.k",
        "....kkkkkkk",
        "...kkwwkkkkk",
        "...kkwwkkkkk",
        ".kkkkkkkkkkkkk",
        "...kkkkkkkkk",
        "...kkkkkkkkk",
        "....kkkkkkk",
        "...k.kkkkk.k",
        ".......k",
        ".......k",
        "",
        "",
    ],
    # Démineur : drapeau
    "flag": [
        "",
        "",
        ".....rrk",
        "...rrrrk",
        "..rrrrrk",
        "...rrrrk",
        ".....rrk",
        ".......k",
        ".......k",
        ".....kkkkk",
        "...kkkkkkkkk",
        "...kkkkkkkkk",
        "",
        "",
        "",
        "",
    ],
    # Windows Update : globe et fenêtre
    "update": [
        "....kkkkkk......",
        "..kkbbeebbkk....",
        ".kbbbeeebbbbk...",
        ".kbeeeebbbeebk..",
        "kbbeeebbbbeeebk.",
        "kbbbeebbbbbeebk.",
        "kbbbbebbbbbbbbk.",
        "kbbbbbbbeebbbbk.",
        "kbbbbbbbkkkkkkkk",
        ".kbbbbbbknnnnnnk",
        ".kbbeebbkwwwwwwk",
        "..kbbbbbkwrrGGwk",
        "...kkbbbkwbbyywk",
        ".....kkkkwwwwwwk",
        "........kkkkkkkk",
        "",
    ],
    "warning": ["", ".......kk", "......kyyk", "......kyyk", ".....kyyyyk", ".....kykkyk", "....kyykkyyk",
                "....kyykkyyk", "...kyyykkyyyk", "...kyyykkyyyk", "..kyyyyyyyyyyk", "..kyyyykkyyyyk",
                ".kyyyyykkyyyyyk", ".kyyyyyyyyyyyyk", "kkkkkkkkkkkkkkkk", ""],
}


def _grid(name, rows):
    """16 lignes de 16 caractères ; les lignes courtes sont complétées par du transparent."""
    assert len(rows) <= 16, f"{name}: {len(rows)} lignes"
    rows = [r.ljust(16, ".") for r in rows] + ["." * 16] * (16 - len(rows))
    for y, row in enumerate(rows):
        assert len(row) == 16, f"{name} ligne {y}: {len(row)} caractères ({row!r})"
        bad = set(row) - set(PALETTE) - {"."}
        assert not bad, f"{name} ligne {y}: couleurs inconnues {bad}"
    return rows


def _rects(rows):
    rects = []
    for y, row in enumerate(rows):
        x = 0
        while x < 16:
            c = row[x]
            n = 1
            while x + n < 16 and row[x + n] == c:
                n += 1
            if c != ".":
                rects.append(f'<rect x="{x}" y="{y}" width="{n}" height="1" fill="{PALETTE[c]}"/>')
            x += n
    return "".join(rects)


def symbol(name, rows):
    return f'<symbol id="w95-{name}" viewBox="0 0 16 16">{_rects(_grid(name, rows))}</symbol>'


def css_rule(name, rows):
    """Icône en image de fond (data URI) : .w95i-NOM, seulement en thème win95."""
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' shape-rendering='crispEdges'>"
           f"{_rects(_grid(name, rows))}</svg>").replace('"', "'").replace("#", "%23")
    return f'html[data-theme="win95"] .w95i-{name} {{ background-image: url("data:image/svg+xml,{svg}"); }}'


def main():
    out = os.path.join(os.path.dirname(__file__), "..", "Base", "Web", "static", "icons", "win95.svg")
    body = "\n".join(symbol(n, r) for n, r in ICONS.items())
    with open(out, "w") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges">\n'
                "<!-- Généré par tools/win95_icons.py : modifier les grilles là-bas -->\n"
                f"{body}\n</svg>\n")
    css = os.path.join(os.path.dirname(__file__), "..", "Base", "Web", "static", "css", "win95-icons.css")
    with open(css, "w") as f:
        f.write("/* Généré par tools/win95_icons.py : icônes Win95 en image de fond (.w95i .w95i-NOM) */\n"
                'html[data-theme="win95"] .w95i { background: no-repeat center / 16px 16px; }\n'
                + "\n".join(css_rule(n, r) for n, r in ICONS.items()) + "\n")
    print(f"{len(ICONS)} icônes -> {os.path.normpath(out)} + {os.path.normpath(css)}")


if __name__ == "__main__":
    main()
