import json


class WebSocketWriter:
    def __init__(self, cfg: dict):
        self._host = cfg.get("host", "localhost")
        self._port = int(cfg.get("port", 8765))

    def write(self, result: dict) -> None:
        import websocket
        url     = f"ws://{self._host}:{self._port}"
        payload = json.dumps(result, ensure_ascii=False, default=str)
        ws      = websocket.create_connection(url, timeout=10)
        try:
            ws.send(payload)
        finally:
            ws.close()
