from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math
import struct

import numpy as np
from numpy.typing import NDArray


class FrameFormat(Enum):
    UMEKO_LEGACY = "Umeko MLX90640"
    MLX90640 = "MLX90640"
    MLX90641 = "MLX90641"
    HEIMANN = "Heimann 32x32"


@dataclass(frozen=True, slots=True)
class ThermalFrame:
    format: FrameFormat
    width: int
    height: int
    temperatures: NDArray[np.float32]
    reported_max: float | None
    reported_min: float | None
    reported_avg: float | None
    received_at: datetime
    sequence: int

    @property
    def minimum(self) -> float:
        return float(np.min(self.temperatures))

    @property
    def maximum(self) -> float:
        return float(np.max(self.temperatures))

    @property
    def average(self) -> float:
        return float(np.mean(self.temperatures))


class FrameParser:
    """Incrementally decode all known Umeko/Windows-host stream formats."""

    _MLX40_BEGIN = b"MLX40BEGIN"
    _MLX40_END = b"MLX40END"
    _MLX41_BEGIN = b"MLX41BEGIN"
    _MLX41_END = b"MLX41END"
    _LEGACY_BEGIN = b"BEGIN"
    _LEGACY_END = b"END"
    _MLX40_SIZE = 10 + 8 + 768 * 4 + 8
    _MLX41_SIZE = 10 + 8 + 192 * 4 + 8
    _HEMEANN_SIZE = 5 + 4 + 1024 * 2 + 3
    _UMEKO_SIZE = 5 + 12 + 768 * 4 + 3
    _MAX_BUFFER = 128 * 1024

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._sequence = 0

    def reset(self) -> None:
        self._buffer.clear()

    def feed(self, data: bytes) -> list[ThermalFrame]:
        if data:
            self._buffer.extend(data)
        frames: list[ThermalFrame] = []
        while True:
            marker = self._find_marker()
            if marker is None:
                self._retain_marker_prefix()
                break
            position, kind = marker
            if position:
                del self._buffer[:position]
            result = self._extract(kind)
            if result is None:
                break
            if result is False:
                del self._buffer[0]
                continue
            frame, consumed = result
            del self._buffer[:consumed]
            frames.append(frame)
        if len(self._buffer) > self._MAX_BUFFER:
            del self._buffer[:-10]
        return frames

    def _find_marker(self) -> tuple[int, FrameFormat] | None:
        candidates: list[tuple[int, int, FrameFormat]] = []
        for marker, kind in (
            (self._MLX40_BEGIN, FrameFormat.MLX90640),
            (self._MLX41_BEGIN, FrameFormat.MLX90641),
            (self._LEGACY_BEGIN, FrameFormat.UMEKO_LEGACY),
        ):
            pos = self._buffer.find(marker)
            if pos >= 0:
                candidates.append((pos, -len(marker), kind))
        if not candidates:
            return None
        pos, _, kind = min(candidates)
        return pos, kind

    def _extract(
        self, kind: FrameFormat
    ) -> tuple[ThermalFrame, int] | bool | None:
        if kind is FrameFormat.MLX90640:
            return self._extract_float_marker(
                kind, self._MLX40_SIZE, self._MLX40_BEGIN, self._MLX40_END, 32, 24
            )
        if kind is FrameFormat.MLX90641:
            return self._extract_float_marker(
                kind, self._MLX41_SIZE, self._MLX41_BEGIN, self._MLX41_END, 16, 12
            )

        # A short BEGIN frame may be either Heimann uint16 or Umeko float32.
        if len(self._buffer) >= self._HEMEANN_SIZE and self._buffer[
            self._HEMEANN_SIZE - 3 : self._HEMEANN_SIZE
        ] == self._LEGACY_END:
            raw = memoryview(self._buffer)[5 : self._HEMEANN_SIZE - 3]
            reported = np.frombuffer(raw[:4], dtype="<u2").astype(np.float32)
            reported = reported * 0.1 - 273.15
            values = np.frombuffer(raw[4:], dtype="<u2").astype(np.float32)
            values = values * 0.1 - 273.15
            return self._make_frame(
                FrameFormat.HEIMANN, 32, 32, values, reported[0], reported[1], None
            ), self._HEMEANN_SIZE
        if len(self._buffer) < self._UMEKO_SIZE:
            return None
        if self._buffer[self._UMEKO_SIZE - 3 : self._UMEKO_SIZE] != self._LEGACY_END:
            return False
        raw = memoryview(self._buffer)[5 : self._UMEKO_SIZE - 3]
        metadata = np.frombuffer(raw[:12], dtype="<f4")
        values = np.frombuffer(raw[12:], dtype="<f4")
        return self._validated_frame(
            FrameFormat.UMEKO_LEGACY,
            32,
            24,
            values,
            float(metadata[0]),
            float(metadata[1]),
            float(metadata[2]),
            self._UMEKO_SIZE,
        )

    def _extract_float_marker(
        self,
        kind: FrameFormat,
        total_size: int,
        begin: bytes,
        end: bytes,
        width: int,
        height: int,
    ) -> tuple[ThermalFrame, int] | bool | None:
        if len(self._buffer) < total_size:
            return None
        if self._buffer[total_size - len(end) : total_size] != end:
            return False
        raw = memoryview(self._buffer)[len(begin) : total_size - len(end)]
        metadata = np.frombuffer(raw[:8], dtype="<f4")
        values = np.frombuffer(raw[8:], dtype="<f4")
        return self._validated_frame(
            kind,
            width,
            height,
            values,
            float(metadata[0]),
            float(metadata[1]),
            None,
            total_size,
        )

    def _validated_frame(
        self,
        kind: FrameFormat,
        width: int,
        height: int,
        values: NDArray[np.float32],
        reported_max: float,
        reported_min: float,
        reported_avg: float | None,
        consumed: int,
    ) -> tuple[ThermalFrame, int] | bool:
        metadata = (reported_max, reported_min)
        if reported_avg is not None:
            metadata += (reported_avg,)
        if not np.isfinite(values).all() or not all(math.isfinite(v) for v in metadata):
            return False
        return self._make_frame(
            kind, width, height, values, reported_max, reported_min, reported_avg
        ), consumed

    def _make_frame(
        self,
        kind: FrameFormat,
        width: int,
        height: int,
        values: NDArray[np.float32],
        reported_max: float | np.float32 | None,
        reported_min: float | np.float32 | None,
        reported_avg: float | None,
    ) -> ThermalFrame:
        self._sequence += 1
        matrix = np.asarray(values, dtype=np.float32).reshape(height, width).copy()
        return ThermalFrame(
            format=kind,
            width=width,
            height=height,
            temperatures=matrix,
            reported_max=None if reported_max is None else float(reported_max),
            reported_min=None if reported_min is None else float(reported_min),
            reported_avg=reported_avg,
            received_at=datetime.now().astimezone(),
            sequence=self._sequence,
        )

    def _retain_marker_prefix(self) -> None:
        max_prefix = 0
        data = bytes(self._buffer)
        for marker in (self._MLX40_BEGIN, self._MLX41_BEGIN, self._LEGACY_BEGIN):
            for length in range(1, len(marker)):
                if data.endswith(marker[:length]):
                    max_prefix = max(max_prefix, length)
        if max_prefix:
            del self._buffer[:-max_prefix]
        else:
            self._buffer.clear()
