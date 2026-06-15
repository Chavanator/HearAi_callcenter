from __future__ import annotations
import traceback
from typing import Optional, Callable

_ws_reader = None


def get_audio_records(
    config: dict,
    folder_extension: str = "*.wav",
    sql_tipo_proceso: str = "transcription",
) -> list[dict]:

    from log import get_logger
    log = get_logger()

    sources = config.get("source", {})
    records: list[dict] = []

    if sources.get("folder"):
        try:
            from reader.folder_reader import FolderReader
            records.extend(FolderReader(config["folder"]).read(extension=folder_extension))
            log.debug(f"[reader] folder: {len(records)} registros")
        except Exception as e:
            log.error(f"[reader][folder] {e}\n{traceback.format_exc()}")

    if sources.get("csv"):
        try:
            from reader.csv_reader import CsvReader
            r = CsvReader(config["csv"]).read()
            log.debug(f"[reader] csv: {len(r)} registros")
            records.extend(r)
        except Exception as e:
            log.error(f"[reader][csv] {e}\n{traceback.format_exc()}")

    if sources.get("mongo_db"):
        try:
            from reader.mongo_reader import MongoReader
            r = MongoReader(config["mongo_db"]).read()
            log.debug(f"[reader] mongo: {len(r)} registros")
            records.extend(r)
        except Exception as e:
            log.error(f"[reader][mongo] {e}\n{traceback.format_exc()}")

    if sources.get("sql"):
        try:
            from reader.sql_reader import SqlReader
            polling = config.get("sql_polling", {})
            proc    = polling.get(sql_tipo_proceso, {})
            sp      = proc.get("sp_get_pending", "")
            r = SqlReader(config["db_connection"]).read(sp_name=sp, tipo_proceso=sql_tipo_proceso)
            log.debug(f"[reader] sql ({sql_tipo_proceso}): {len(r)} registros")
            records.extend(r)
        except Exception as e:
            log.error(f"[reader][sql] {e}\n{traceback.format_exc()}")

    if sources.get("web_socket"):
        ws = _get_ws_reader(config)
        r  = ws.drain()
        log.debug(f"[reader] websocket: {len(r)} registros drenados")
        records.extend(r)

    log.info(f"[reader] Total registros: {len(records)}")
    return records


def start_websocket_listener(config: dict, callback: Optional[Callable] = None) -> None:
    _get_ws_reader(config).start(callback=callback)


def stop_websocket_listener() -> None:
    if _ws_reader is not None:
        _ws_reader.stop()


def _get_ws_reader(config: dict):
    global _ws_reader
    if _ws_reader is None:
        from reader.websocket_reader import WebSocketReader
        _ws_reader = WebSocketReader(
            cfg        = config.get("web_socket", {}),
            retry_time = config.get("retry_time", 5),
        )
    return _ws_reader


__all__ = ["get_audio_records", "start_websocket_listener", "stop_websocket_listener"]