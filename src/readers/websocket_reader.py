import json
import queue
import threading
from typing import Optional, Callable
from reader.base_reader import BaseReader


class WebSocketReader(BaseReader):

    def __init__(self, cfg: dict, retry_time: int = 5):
        self._host       = cfg.get("host", "localhost")
        self._port       = int(cfg.get("port", 8765))
        self._retry_time = retry_time
        self._queue: queue.Queue      = queue.Queue()
        self._stop:  threading.Event  = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # read=drain
    def read(self, **_) -> list[dict]:
        return self.drain()

    #funcion principal
    def start(self, callback: Optional[Callable[[dict], None]] = None) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._listener_loop,
            daemon=True,
            name="ws-listener",
        )
        self._thread.start()

        if callback:
            threading.Thread(
                target=self._dispatcher_loop,
                args=(callback,),
                daemon=True,
                name="ws-dispatcher",
            ).start()

    def stop(self) -> None:
        self._stop.set()

    def drain(self) -> list[dict]:
        records = []
        while not self._queue.empty():
            try:
                records.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return records

    #helpers internos
    def _listener_loop(self) -> None:
        try:
            import websocket
        except ImportError:
            return

        url = f"ws://{self._host}:{self._port}"

        while not self._stop.is_set():
            try:
                ws = websocket.create_connection(url, timeout=10)
                while not self._stop.is_set():
                    try:
                        ws.settimeout(1)
                        raw = ws.recv()
                        if not raw:
                            continue
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            msg = {"audio_path": raw}

                        if "audio_path" not in msg:
                            continue

                        self._queue.put({"source": "web_socket", **msg})

                    except websocket.WebSocketTimeoutException:
                        continue
                    except Exception:
                        break
                ws.close()
            except Exception:
                self._stop.wait(self._retry_time)

    def _dispatcher_loop(self, callback: Callable[[dict], None]) -> None:
        while not self._stop.is_set():
            try:
                record = self._queue.get(timeout=1)
                callback(record)
            except queue.Empty:
                continue
            except Exception:
                pass
