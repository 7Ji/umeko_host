from __future__ import annotations

import struct
import threading
import time

import numpy as np

from umeko_host import serial_io


def _wire_frame() -> bytes:
    pixels = np.linspace(20, 35, 768, dtype="<f4")
    metadata = struct.pack("<fff", 35.0, 20.0, float(pixels.mean()))
    return b"BEGIN" + metadata + pixels.tobytes() + b"END"


class FakeSerial:
    def __init__(self, **kwargs) -> None:
        self.buffer = bytearray()
        self.writes: list[bytes] = []

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    @property
    def in_waiting(self) -> int:
        return len(self.buffer)

    def read(self, size: int) -> bytes:
        if not self.buffer:
            time.sleep(0.001)
            return b""
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        if data == b"stream\n":
            self.buffer.extend(_wire_frame())
        elif data == b"check\n":
            self.buffer.extend(b'{"photos":[],"total":0}\r\n')
        return len(data)

    def flush(self) -> None:
        return None

    def reset_input_buffer(self) -> None:
        self.buffer.clear()


def test_explicit_stream_is_kept_alive_and_stopped(monkeypatch) -> None:
    fake = FakeSerial()
    monkeypatch.setattr(serial_io.serial, "Serial", lambda **kwargs: fake)
    monkeypatch.setattr(serial_io, "_PASSIVE_DETECTION_SECONDS", 0.01)
    monkeypatch.setattr(serial_io, "_STREAM_KEEPALIVE_SECONDS", 0.01)
    wake = threading.Event()
    session = serial_io.SerialSession(lambda state, detail: None, wake.set)

    session.start("fake")
    deadline = time.monotonic() + 0.5
    while fake.writes.count(b"stream\n") < 3 and time.monotonic() < deadline:
        wake.wait(0.02)
        wake.clear()
    session.stop()

    assert fake.writes.count(b"stream\n") >= 3
    assert fake.writes[-1] == b"stop_stream\n"
    assert session.latest_frame() is not None


def test_photo_transaction_restores_stream(monkeypatch) -> None:
    fake = FakeSerial()
    monkeypatch.setattr(serial_io.serial, "Serial", lambda **kwargs: fake)
    monkeypatch.setattr(serial_io, "_PASSIVE_DETECTION_SECONDS", 0.01)
    monkeypatch.setattr(serial_io, "_STREAM_KEEPALIVE_SECONDS", 0.01)
    monkeypatch.setattr(serial_io, "_PHOTO_SETTLE_SECONDS", 0.0)
    frame_wake = threading.Event()
    photo_wake = threading.Event()
    responses = []
    session = serial_io.SerialSession(
        lambda state, detail: None,
        frame_wake.set,
        lambda kind, data, error: (responses.append((kind, data, error)), photo_wake.set()),
    )

    session.start("fake")
    assert frame_wake.wait(0.5)
    session.request_photo_list()
    assert photo_wake.wait(0.5)
    deadline = time.monotonic() + 0.5
    while fake.writes.count(b"stream\n") < 2 and time.monotonic() < deadline:
        time.sleep(0.005)
    session.stop()

    assert responses == [("list", b'{"photos":[],"total":0}\r\n', None)]
    check_index = fake.writes.index(b"check\n")
    assert b"stop_stream\n" in fake.writes[:check_index]
    assert b"stream\n" in fake.writes[check_index + 1 :]
