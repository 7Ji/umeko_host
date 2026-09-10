from __future__ import annotations

import numpy as np
import pytest

from umeko_host.photos import PhotoInfo, parse_photo_catalog, parse_photo_download, write_photo_csv


def catalog_response() -> bytes:
    return (
        b'Photo check result:\r\n{"photos":['
        b'{"index":1,"filename":"photo_1.dat","size":3080},'
        b'{"index":0,"filename":"photo_0.dat","size":3080}'
        b'],"total":2}\r\n'
    )


def download_response() -> tuple[PhotoInfo, bytes, bytes]:
    values = np.linspace(21, 39, 770, dtype="<f4")
    values[0] = 40.0
    values[1] = 20.0
    raw = values.tobytes()
    lines = []
    for offset in range(0, len(raw), 16):
        encoded = " ".join(f"{byte:02X}" for byte in raw[offset : offset + 16])
        lines.append(f"{offset:08X}: {encoded}  |ignored|")
    response = (
        "Starting download\r\n==== BEGIN FILE DATA ====\r\n"
        + "\r\n".join(lines)
        + "\r\n===== END FILE DATA =====\r\nDownload completed. Total bytes: 3080"
    ).encode()
    return PhotoInfo(0, "photo_0.dat", 3080), response, raw


def test_parses_and_sorts_catalog() -> None:
    photos = parse_photo_catalog(catalog_response())
    assert [photo.filename for photo in photos] == ["photo_0.dat", "photo_1.dat"]


def test_rejects_unknown_catalog_layout() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        parse_photo_catalog(b'{"photos":[{"index":0,"filename":"secret","size":4}]}')


def test_decodes_stored_photo_layout(tmp_path) -> None:
    info, response, raw = download_response()
    photo = parse_photo_download(info, response)
    assert photo.raw == raw
    assert photo.reported_max == 40.0
    assert photo.reported_min == 20.0
    assert photo.temperatures.shape == (24, 32)
    output = tmp_path / "photo.csv"
    write_photo_csv(photo, output)
    assert len(output.read_text(encoding="utf-8").splitlines()) == 25


def test_rejects_truncated_download() -> None:
    info, response, _ = download_response()
    with pytest.raises(ValueError, match="Invalid photo length"):
        parse_photo_download(info, response.replace(b"00 00", b"", 1))
