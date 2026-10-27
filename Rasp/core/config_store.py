"""Configuration du robot : source unique de vérité (Rasp/config.json).

La base ne fait que l'afficher et envoyer des modifications ; c'est ce module
qui les valide et les enregistre. Pur Python, sans dépendance matérielle
(testable sur PC, cf. test/test_config_store.py).

- Les clés connues (SCHEMA) sont typées et validées ; les autres sont gardées telles quelles.
- Clés imbriquées acceptées en notation pointée : "camera.enabled".
- Écriture atomique (fichier temporaire + rename) : un arrêt brutal ne laisse pas
  un config.json à moitié écrit.
- `data` est un dict modifié en place : les modules qui gardent une référence
  (shared.cfg) voient toujours la config à jour.
"""

import copy
import json
import os
import threading


def _one_of(*choices):
    def check(v):
        if v not in choices:
            raise ValueError(f"valeur attendue parmi {choices}")
        return v
    return check


def _bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.lower() in ("true", "false"):
        return v.lower() == "true"
    raise ValueError("booléen attendu")


def _number(lo=None, hi=None):
    def check(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("nombre attendu")
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            raise ValueError(f"nombre attendu entre {lo} et {hi}")
        return v
    return check


def _str_or_none(v):
    if v is None or isinstance(v, str):
        return v
    raise ValueError("texte attendu")


def _str(v):
    if isinstance(v, str):
        return v
    raise ValueError("texte attendu")


# clé (notation pointée) -> (valeur par défaut, validateur)
SCHEMA = {
    "team":           ("BLEUE", _one_of("BLEUE", "JAUNE")),
    "strat_mode":     ("STATIC", _one_of("STATIC", "DYNAMIC")),
    "static_strat":   (None, _str_or_none),
    "test_mode":      (False, _bool),
    "lidar_mode":     ("MATCH", _one_of("OFF", "MATCH", "HOMOLOGATION")),
    "music_enabled":  (True, _bool),
    "leds_enabled":   (True, _bool),
    "server_ip":      ("192.168.10.2", _str),
    "camera.enabled": (True, _bool),
    "audio.volume":   (0.8, _number(0, 1)),
    "leds.luminosite": (0.1, _number(0, 1)),  # luminosité du bandeau DotStar (curseur Debug : 100 % = 0,5)
}


class ConfigError(ValueError):
    pass


def _get_path(d, dotted):
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None, False
        cur = cur[k]
    return cur, True


def _set_path(d, dotted, value):
    keys = dotted.split(".")
    cur = d
    for k in keys[:-1]:
        if not isinstance(cur.get(k), dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value


def _flatten(prefix, value, out):
    """{"camera": {"enabled": True}} -> {"camera.enabled": True} (pour valider un dict imbriqué)."""
    if isinstance(value, dict) and any(k.startswith(prefix + ".") for k in SCHEMA):
        for k, v in value.items():
            _flatten(f"{prefix}.{k}", v, out)
    else:
        out[prefix] = value


class ConfigStore:
    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self.data = {}
        self.load()

    # ------------------------------------------------------------------
    def load(self):
        """Charge le fichier, complète les clés manquantes, corrige les valeurs invalides."""
        with self._lock:
            raw = {}
            if os.path.exists(self.path):
                try:
                    with open(self.path, encoding="utf-8") as f:
                        raw = json.load(f)
                except (OSError, ValueError) as e:
                    print(f"[CONFIG] config.json illisible ({e}) : valeurs par défaut utilisées")
                    raw = {}
            self.data.clear()
            self.data.update(raw if isinstance(raw, dict) else {})
            for key, (default, check) in SCHEMA.items():
                value, present = _get_path(self.data, key)
                if not present:
                    _set_path(self.data, key, copy.deepcopy(default))
                    continue
                try:
                    _set_path(self.data, key, check(value))
                except ValueError as e:
                    print(f"[CONFIG] {key}={value!r} invalide ({e}) : remis à {default!r}")
                    _set_path(self.data, key, copy.deepcopy(default))
            return self.data

    def get(self, key, default=None):
        with self._lock:
            value, present = _get_path(self.data, key)
            return value if present else default

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self.data)

    # ------------------------------------------------------------------
    def validate(self, changes):
        """Vérifie {clé pointée ou dict imbriqué: valeur} sans rien modifier.
        Renvoie un dict à plat {clé pointée: valeur validée}. Lève ConfigError."""
        flat = {}
        for key, value in changes.items():
            _flatten(key, value, flat)
        out, errors = {}, []
        for key, value in flat.items():
            if key in SCHEMA:
                try:
                    out[key] = SCHEMA[key][1](value)
                except ValueError as e:
                    errors.append(f"{key} : {e}")
            else:
                out[key] = value
        if errors:
            raise ConfigError(" ; ".join(errors))
        return out

    def update(self, changes, save=True):
        """Applique des modifications validées. Renvoie {clé: nouvelle valeur} pour les clés
        réellement modifiées (vide si rien n'a changé). Tout ou rien en cas d'erreur."""
        with self._lock:
            valid = self.validate(changes)
            changed = {}
            for key, value in valid.items():
                old, present = _get_path(self.data, key)
                if not present or old != value:
                    _set_path(self.data, key, copy.deepcopy(value))
                    changed[key] = value
            if changed and save:
                self.save()
            return changed

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
