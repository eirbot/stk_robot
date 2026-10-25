#!/usr/bin/env python3
"""Encombrement du robot (ou de la table) d'après son modèle MuJoCo (export Onshape de vision_deporte).

    uv run --project Base/Vision/vision_deporte python tools/encombrement_robot.py
    uv run --project Base/Vision/vision_deporte python tools/encombrement_robot.py <modele.xml>

Parcourt les géométries visuelles (maillages STL binaires) avec les positions / rotations des
corps, et affiche la boîte englobante dans le repère du modèle (robot : origine au milieu de
l'axe des roues, X vers l'avant). Les valeurs servent dans Rasp/core/frames.py et
Base/Web/static/js/frames.js (ROBOT_FRONT_MM, ROBOT_BACK_MM, ROBOT_HALF_WIDTH_MM, ROBOT_HEIGHT_MM).
"""
import os
import struct
import sys
import xml.etree.ElementTree as ET

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_MODEL = os.path.join(ROOT, "Base", "Vision", "vision_deporte", "src", "vision_deporte",
                             "models", "robot", "robot.xml")


def quat_matrix(q):
    """Quaternion MuJoCo (w, x, y, z) -> matrice de rotation."""
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def read_stl(path):
    """Sommets d'un STL binaire (tableau N x 3, mètres)."""
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        tri = np.frombuffer(f.read(n * 50), dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return tri["v"].reshape(-1, 3)


def vec(el, attr, default):
    return np.array([float(v) for v in el.get(attr, default).split()])


def visual_points(model_path):
    root = ET.parse(model_path).getroot()
    meshdir = os.path.join(os.path.dirname(model_path), root.find("compiler").get("meshdir", ""))
    points = []

    def walk(body, rot, pos):
        for g in body.findall("geom"):
            if g.get("class") != "visual" or g.get("type", "mesh") != "mesh":
                continue
            g_rot, g_pos = quat_matrix(vec(g, "quat", "1 0 0 0")), vec(g, "pos", "0 0 0")
            v = read_stl(os.path.join(meshdir, g.get("mesh") + ".stl"))
            points.append((v @ g_rot.T + g_pos) @ rot.T + pos)
        for b in body.findall("body"):
            b_rot, b_pos = quat_matrix(vec(b, "quat", "1 0 0 0")), vec(b, "pos", "0 0 0")
            walk(b, rot @ b_rot, rot @ b_pos + pos)

    for body in root.find("worldbody").findall("body"):
        walk(body, np.eye(3), np.zeros(3))
    return np.vstack(points) * 1000.0  # mm


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    p = visual_points(model)
    lo, hi = p.min(0), p.max(0)
    print(f"Modèle : {model}")
    print(f"X : {lo[0]:.1f} -> {hi[0]:.1f} mm   (avant {hi[0]:.1f}, arrière {-lo[0]:.1f})")
    print(f"Y : {lo[1]:.1f} -> {hi[1]:.1f} mm   (demi-largeur {max(-lo[1], hi[1]):.1f})")
    print(f"Z : {lo[2]:.1f} -> {hi[2]:.1f} mm")
    print(f"Taille : {hi[0] - lo[0]:.1f} x {hi[1] - lo[1]:.1f} x {hi[2] - lo[2]:.1f} mm")


if __name__ == "__main__":
    main()
