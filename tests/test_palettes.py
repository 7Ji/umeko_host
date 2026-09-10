from __future__ import annotations

import numpy as np

from umeko_host.palettes import PALETTE_NAMES, colorize, make_lut, orient


def test_palettes_are_complete_luts() -> None:
    for name in PALETTE_NAMES:
        lut = make_lut(name)
        assert lut.shape == (256, 3)
        assert lut.dtype == np.uint8


def test_colorize_clamps_values() -> None:
    image = colorize(
        np.array([[-10.0, 0.0, 10.0]], dtype=np.float32), 0, 10, "Grayscale"
    )
    assert image.tolist() == [[[0, 0, 0], [0, 0, 0], [255, 255, 255]]]


def test_orientation_order_and_shape() -> None:
    source = np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32)
    result = orient(source, horizontal_flip=True, vertical_flip=False, rotation=90)
    assert result.shape == (3, 2)
    assert result.tolist() == [[6, 3], [5, 2], [4, 1]]
