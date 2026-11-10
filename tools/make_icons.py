#!/usr/bin/env python3
"""Genera los íconos PNG de la app, con el mismo dibujo que icon.svg."""
import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "site" / "icons"
BG = (11, 14, 12)
GREEN = (98, 245, 160)
RED = (255, 107, 112)
SEGMENT = ((256, 256), (362, 150))


def cover(distance: float, scale: float) -> float:
    """Cuánto cubre una forma al píxel, con borde suavizado."""
    return max(0.0, min(1.0, 0.5 - distance * scale))


def to_segment(x: float, y: float) -> float:
    (ax, ay), (bx, by) = SEGMENT
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - ax - t * dx, y - ay - t * dy)


def pixel(x: float, y: float, scale: float) -> tuple[int, ...]:
    r = math.hypot(x - 256, y - 256)
    shapes = [
        (GREEN, abs(r - 150) - 7),
        (GREEN, abs(r - 90) - 7),
        (GREEN, to_segment(x, y) - 8),
        (GREEN, r - 24),
        (RED, math.hypot(x - 330, y - 310) - 16),
    ]
    color = list(BG)
    for shade, distance in shapes:
        alpha = cover(distance, scale)
        color = [round(c + (s - c) * alpha) for c, s in zip(color, shade)]
    return tuple(color)


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def make(size: int) -> bytes:
    scale = size / 512
    rows = bytearray()
    for j in range(size):
        rows.append(0)
        for i in range(size):
            rows.extend(pixel((i + 0.5) / scale, (j + 0.5) / scale, scale))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b"")


for dimension in (192, 512):
    (OUT / f"icon-{dimension}.png").write_bytes(make(dimension))
