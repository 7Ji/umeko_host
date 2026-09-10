from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


PALETTE_NAMES = ("Iron", "Inferno", "Turbo", "Grayscale", "Inverted Grayscale")

_STOPS: dict[str, tuple[tuple[float, tuple[int, int, int]], ...]] = {
    "Iron": (
        (0.0, (0, 0, 0)),
        (0.25, (65, 0, 95)),
        (0.5, (190, 25, 45)),
        (0.75, (255, 150, 20)),
        (1.0, (255, 255, 235)),
    ),
    "Inferno": (
        (0.0, (0, 0, 4)),
        (0.25, (87, 16, 110)),
        (0.5, (188, 55, 84)),
        (0.75, (249, 142, 9)),
        (1.0, (252, 255, 164)),
    ),
    "Turbo": (
        (0.0, (48, 18, 59)),
        (0.2, (50, 100, 210)),
        (0.4, (27, 190, 180)),
        (0.6, (150, 225, 55)),
        (0.8, (250, 135, 15)),
        (1.0, (125, 0, 0)),
    ),
    "Grayscale": ((0.0, (0, 0, 0)), (1.0, (255, 255, 255))),
    "Inverted Grayscale": ((0.0, (255, 255, 255)), (1.0, (0, 0, 0))),
}


def make_lut(name: str) -> NDArray[np.uint8]:
    stops = _STOPS.get(name, _STOPS["Iron"])
    positions = np.array([stop[0] for stop in stops], dtype=np.float32)
    colors = np.array([stop[1] for stop in stops], dtype=np.float32)
    samples = np.linspace(0, 1, 256, dtype=np.float32)
    channels = [np.interp(samples, positions, colors[:, channel]) for channel in range(3)]
    return np.stack(channels, axis=1).round().astype(np.uint8)


def colorize(
    temperatures: NDArray[np.float32], minimum: float, maximum: float, palette: str
) -> NDArray[np.uint8]:
    span = max(maximum - minimum, 1e-6)
    indices = np.clip((temperatures - minimum) / span * 255, 0, 255).astype(np.uint8)
    return make_lut(palette)[indices]


def orient(
    matrix: NDArray[np.float32], horizontal_flip: bool, vertical_flip: bool, rotation: int
) -> NDArray[np.float32]:
    result = matrix
    if horizontal_flip:
        result = np.fliplr(result)
    if vertical_flip:
        result = np.flipud(result)
    if rotation:
        result = np.rot90(result, k=-(rotation // 90))
    return np.ascontiguousarray(result)
