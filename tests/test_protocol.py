from __future__ import annotations

import struct

import numpy as np
import pytest

from umeko_host.protocol import FrameFormat, FrameParser


def umeko_frame(values: np.ndarray | None = None) -> bytes:
    pixels = np.arange(768, dtype="<f4") / 10 if values is None else values.astype("<f4")
    metadata = struct.pack("<fff", float(pixels.max()), float(pixels.min()), float(pixels.mean()))
    return b"BEGIN" + metadata + pixels.tobytes() + b"END"


def mlx_frame(kind: FrameFormat) -> bytes:
    if kind is FrameFormat.MLX90640:
        begin, end, count = b"MLX40BEGIN", b"MLX40END", 768
    else:
        begin, end, count = b"MLX41BEGIN", b"MLX41END", 192
    pixels = np.linspace(18, 42, count, dtype="<f4")
    return begin + struct.pack("<ff", 42.0, 18.0) + pixels.tobytes() + end


def heimann_frame() -> bytes:
    pixels_kelvin_tenths = np.arange(1024, dtype="<u2") + 2931
    return b"BEGIN" + struct.pack("<HH", 3231, 2931) + pixels_kelvin_tenths.tobytes() + b"END"


@pytest.mark.parametrize(
    ("wire", "kind", "shape"),
    [
        (umeko_frame(), FrameFormat.UMEKO_LEGACY, (24, 32)),
        (mlx_frame(FrameFormat.MLX90640), FrameFormat.MLX90640, (24, 32)),
        (mlx_frame(FrameFormat.MLX90641), FrameFormat.MLX90641, (12, 16)),
        (heimann_frame(), FrameFormat.HEIMANN, (32, 32)),
    ],
)
def test_decodes_known_formats(wire: bytes, kind: FrameFormat, shape: tuple[int, int]) -> None:
    frames = FrameParser().feed(wire)
    assert len(frames) == 1
    assert frames[0].format is kind
    assert frames[0].temperatures.shape == shape
    assert np.isfinite(frames[0].temperatures).all()


def test_handles_byte_at_a_time_and_text_noise() -> None:
    parser = FrameParser()
    frames = []
    wire = b"streaming started\r\n" + umeko_frame() + b"status text\n" + umeko_frame()
    for byte in wire:
        frames.extend(parser.feed(bytes((byte,))))
    assert [frame.sequence for frame in frames] == [1, 2]


def test_prefers_long_marker_over_begin_suffix() -> None:
    frame = FrameParser().feed(mlx_frame(FrameFormat.MLX90640))[0]
    assert frame.format is FrameFormat.MLX90640


def test_recovers_after_corrupt_frame() -> None:
    corrupt = bytearray(umeko_frame())
    corrupt[-1] = 0
    frames = FrameParser().feed(bytes(corrupt) + b"noise" + umeko_frame())
    assert len(frames) == 1
    assert frames[0].format is FrameFormat.UMEKO_LEGACY


def test_rejects_non_finite_pixels_and_recovers() -> None:
    values = np.arange(768, dtype=np.float32)
    values[100] = np.nan
    frames = FrameParser().feed(umeko_frame(values) + umeko_frame())
    assert len(frames) == 1
    assert frames[0].sequence == 1


def test_heimann_units_are_celsius() -> None:
    frame = FrameParser().feed(heimann_frame())[0]
    assert frame.temperatures[0, 0] == pytest.approx(19.95, abs=0.01)
    assert frame.reported_max == pytest.approx(49.95, abs=0.01)

