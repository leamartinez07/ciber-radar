#!/usr/bin/env python3
"""Genera collector/world_land.txt: el contorno de los continentes para el mapa de la portada.

Parte de ne_110m_land.geojson de Natural Earth (dominio público, naturalearthdata.com), versión 5.1.2:
    https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_land.geojson
Lo proyecta a una caja de 1000 × 460 (de 84° N a 58° S, sin la Antártida), descarta las islas mínimas
y redondea a enteros: queda un trazo SVG de unos 21 KB.

    python tools/make_map.py ne_110m_land.geojson
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

W, H, TOP, BOTTOM = 1000, 460, 84, -58
MIN_AREA = 6  # en unidades de la caja; por debajo, la isla no se distingue


def project(lon: float, lat: float) -> tuple[float, float]:
    return (lon + 180) / 360 * W, (TOP - lat) / (TOP - BOTTOM) * H


def area(ring: list[tuple[float, float]]) -> float:
    return abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))) / 2


def main() -> int:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    paths = []
    for feature in data["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for polygon in polygons:
            ring = polygon[0]
            if max(point[1] for point in ring) < BOTTOM:
                continue
            projected = [project(*point[:2]) for point in ring]
            if area(projected) < MIN_AREA:
                continue
            points: list[tuple[int, int]] = []
            for x, y in projected:
                point = (round(x), round(min(max(y, 0), H)))
                if not points or point != points[-1]:
                    points.append(point)
            if len(points) < 4:
                continue
            steps = " ".join(f"{b[0] - a[0]} {b[1] - a[1]}" for a, b in zip(points, points[1:]))
            paths.append(f"M{points[0][0]} {points[0][1]}l{steps}z")
    out = Path(__file__).resolve().parent.parent / "collector" / "world_land.txt"
    out.write_text("".join(paths), encoding="utf-8")
    print(f"{len(paths)} polígonos, {out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
