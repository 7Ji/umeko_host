from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re

import numpy as np
from numpy.typing import NDArray

from .i18n import tr


_HEX_LINE = re.compile(rb"^[0-9A-Fa-f]{8}:\s+((?:[0-9A-Fa-f]{2}\s+)+)", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class PhotoInfo:
    index: int
    filename: str
    size: int


@dataclass(frozen=True, slots=True)
class StoredPhoto:
    info: PhotoInfo
    raw: bytes
    temperatures: NDArray[np.float32]
    reported_max: float
    reported_min: float

    @property
    def minimum(self) -> float:
        return float(np.min(self.temperatures))

    @property
    def maximum(self) -> float:
        return float(np.max(self.temperatures))

    @property
    def average(self) -> float:
        return float(np.mean(self.temperatures))


def parse_photo_catalog(response: bytes) -> list[PhotoInfo]:
    start = response.find(b'{"photos":')
    if start < 0:
        raise ValueError(tr("Photo list not found in device response"))
    decoder = json.JSONDecoder()
    text = response[start:].decode("utf-8", "replace")
    try:
        payload, _ = decoder.raw_decode(text)
    except json.JSONDecodeError as error:
        raise ValueError(tr("Incomplete photo list JSON")) from error
    photos = payload.get("photos")
    if not isinstance(photos, list):
        raise ValueError(tr("Invalid photo list"))
    result: list[PhotoInfo] = []
    for item in photos:
        try:
            info = PhotoInfo(int(item["index"]), str(item["filename"]), int(item["size"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(tr("Invalid photo entry")) from error
        if not re.fullmatch(r"photo_\d+\.dat", info.filename) or info.size != 3080:
            raise ValueError(tr("Unsupported photo entry: {filename} ({size} bytes)", filename=info.filename, size=info.size))
        result.append(info)
    return sorted(result, key=lambda item: item.index)


def parse_photo_download(info: PhotoInfo, response: bytes) -> StoredPhoto:
    if b"==== BEGIN FILE DATA ====" not in response or b"===== END FILE DATA =====" not in response:
        raise ValueError(tr("Incomplete photo download response"))
    raw = bytearray()
    for match in _HEX_LINE.finditer(response):
        raw.extend(bytes.fromhex(match.group(1).decode("ascii")))
    if len(raw) != info.size:
        raise ValueError(tr("Invalid photo length: expected {expected}, received {actual} bytes", expected=info.size, actual=len(raw)))
    values = np.frombuffer(raw, dtype="<f4")
    if values.size != 770 or not np.isfinite(values).all():
        raise ValueError(tr("Invalid photo temperature data"))
    matrix = values[2:].reshape(24, 32).copy()
    return StoredPhoto(
        info=info,
        raw=bytes(raw),
        temperatures=matrix,
        reported_max=float(values[0]),
        reported_min=float(values[1]),
    )


def write_photo_csv(photo: StoredPhoto, path: str | Path) -> None:
    import csv

    with Path(path).open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(["y/x", *range(photo.temperatures.shape[1])])
        for row_index, row in enumerate(photo.temperatures):
            writer.writerow([row_index, *(f"{float(value):.4f}" for value in row)])
