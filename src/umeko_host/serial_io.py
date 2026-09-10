from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import queue
import re
import threading
import time
from typing import Callable

import serial
from serial.tools import list_ports

from .i18n import tr
from .protocol import FrameParser, ThermalFrame

_PASSIVE_DETECTION_SECONDS = 1.5
_STREAM_KEEPALIVE_SECONDS = 0.5
_STREAM_STALL_SECONDS = 1.5
_PHOTO_LIST_TIMEOUT_SECONDS = 3.0
_PHOTO_DOWNLOAD_TIMEOUT_SECONDS = 8.0
_PHOTO_SETTLE_SECONDS = 0.15


class ConnectionState(Enum):
    DISCONNECTED = "Not connected"
    CONNECTING = "Connecting"
    STREAMING = "Receiving"
    ERROR = "Error"


@dataclass(frozen=True, slots=True)
class PortInfo:
    device: str
    description: str
    serial_number: str | None
    vid: int | None
    pid: int | None

    @property
    def label(self) -> str:
        identity = self.description or tr("Serial device")
        serial_text = f" · {self.serial_number}" if self.serial_number else ""
        return f"{self.device} · {identity}{serial_text}"

    @property
    def is_preferred(self) -> bool:
        return self.vid == 0x2341 and self.pid == 0x005E


def available_ports() -> list[PortInfo]:
    ports = [
        PortInfo(p.device, p.description, p.serial_number, p.vid, p.pid)
        for p in list_ports.comports()
    ]
    return sorted(ports, key=lambda p: (not p.is_preferred, p.device))


class SerialSession:
    """Own a serial port in a worker thread and expose only the latest frame."""

    def __init__(
        self,
        state_callback: Callable[[ConnectionState, str], None],
        frame_callback: Callable[[], None],
        photo_callback: Callable[[str, bytes | None, str | None], None] | None = None,
    ) -> None:
        self._state_callback = state_callback
        self._frame_callback = frame_callback
        self._photo_callback = photo_callback or (lambda kind, data, error: None)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest: ThermalFrame | None = None
        self._serial: serial.Serial | None = None
        self._requests: queue.Queue[tuple[str, str | None]] = queue.Queue()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, port: str) -> None:
        if self.running:
            return
        self._stop.clear()
        while True:
            try:
                self._requests.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            self._latest = None
        self._thread = threading.Thread(target=self._run, args=(port,), daemon=True)
        self._thread.start()

    def stop(self, wait: float = 1.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(wait)

    def latest_frame(self) -> ThermalFrame | None:
        with self._lock:
            return self._latest

    def request_photo_list(self) -> None:
        self._queue_photo_request("list", None)

    def request_photo_download(self, filename: str) -> None:
        if not re.fullmatch(r"photo_\d+\.dat", filename):
            self._photo_callback(f"download:{filename}", None, tr("Invalid photo filename"))
            return
        self._queue_photo_request("download", filename)

    def _queue_photo_request(self, kind: str, argument: str | None) -> None:
        if not self.running:
            self._photo_callback(kind, None, tr("Device is not connected"))
            return
        self._requests.put((kind, argument))

    def _set_latest(self, frame: ThermalFrame) -> None:
        with self._lock:
            self._latest = frame
        self._frame_callback()

    def _set_state(self, state: ConnectionState, detail: str = "") -> None:
        self._state_callback(state, detail)

    def _run(self, port: str) -> None:
        parser = FrameParser()
        failed = False
        self._set_state(ConnectionState.CONNECTING, port)
        started_at = time.monotonic()
        last_frame_at = started_at
        last_keepalive_at = 0.0
        requested_stream = False
        received_frame = False
        try:
            with serial.Serial(
                port=port,
                baudrate=115200,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.05,
                write_timeout=0.5,
            ) as connection:
                self._serial = connection
                while not self._stop.is_set():
                    try:
                        request = self._requests.get_nowait()
                    except queue.Empty:
                        request = None
                    if request is not None:
                        self._execute_photo_request(connection, *request)
                        parser.reset()
                        requested_stream = True
                        last_keepalive_at = time.monotonic()
                        last_frame_at = last_keepalive_at
                        continue
                    chunk = connection.read(max(connection.in_waiting, 1))
                    for frame in parser.feed(chunk):
                        first_frame = not received_frame
                        received_frame = True
                        last_frame_at = time.monotonic()
                        self._set_latest(frame)
                        if first_frame:
                            self._set_state(ConnectionState.STREAMING, frame.format.value)
                    now = time.monotonic()
                    passive_timed_out = (
                        not received_frame and now - started_at >= _PASSIVE_DETECTION_SECONDS
                    )
                    passive_stream_stalled = (
                        received_frame and now - last_frame_at >= _STREAM_STALL_SECONDS
                    )
                    if not requested_stream and (passive_timed_out or passive_stream_stalled):
                        connection.write(b"stream\n")
                        connection.flush()
                        requested_stream = True
                        last_keepalive_at = now
                    elif requested_stream and now - last_keepalive_at >= _STREAM_KEEPALIVE_SECONDS:
                        connection.write(b"stream\n")
                        connection.flush()
                        last_keepalive_at = now
                try:
                    connection.write(b"stop_stream\n")
                    connection.flush()
                    time.sleep(0.1)
                except (serial.SerialException, serial.SerialTimeoutException):
                    pass
        except (serial.SerialException, OSError) as error:
            if not self._stop.is_set():
                failed = True
                self._set_state(ConnectionState.ERROR, str(error))
        finally:
            self._serial = None
            if not failed:
                self._set_state(ConnectionState.DISCONNECTED, "")

    def _execute_photo_request(
        self, connection: serial.Serial, kind: str, argument: str | None
    ) -> None:
        try:
            connection.write(b"stop_stream\n")
            connection.flush()
            time.sleep(_PHOTO_SETTLE_SECONDS)
            connection.reset_input_buffer()
            if kind == "list":
                command = b"check\n"
                timeout = _PHOTO_LIST_TIMEOUT_SECONDS
                complete = lambda data: b'"total":' in data and b"}" in data[data.find(b'"total":') :]
            else:
                assert argument is not None
                command = f"download {argument}\n".encode("ascii")
                timeout = _PHOTO_DOWNLOAD_TIMEOUT_SECONDS
                complete = lambda data: (
                    b"===== END FILE DATA =====" in data and b"Download completed." in data
                )
            connection.write(command)
            connection.flush()
            response = bytearray()
            deadline = time.monotonic() + timeout
            while not self._stop.is_set() and time.monotonic() < deadline:
                response.extend(connection.read(max(connection.in_waiting, 1)))
                if complete(response):
                    result_kind = kind if argument is None else f"{kind}:{argument}"
                    self._photo_callback(result_kind, bytes(response), None)
                    break
            else:
                result_kind = kind if argument is None else f"{kind}:{argument}"
                self._photo_callback(result_kind, None, tr("Device response timed out"))
        except (serial.SerialException, serial.SerialTimeoutException, OSError) as error:
            result_kind = kind if argument is None else f"{kind}:{argument}"
            self._photo_callback(result_kind, None, str(error))
        finally:
            if not self._stop.is_set():
                connection.reset_input_buffer()
                connection.write(b"stream\n")
                connection.flush()
