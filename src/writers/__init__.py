from __future__ import annotations
from datetime import datetime
from typing import Optional


def save(result: dict, config: dict) -> Optional[str]:
    if not result:
        return None

    from log import get_logger
    log = get_logger()

    process   = result.get("process", "unknown")
    metadata  = result.get("metadata", {})
    fecha     = metadata.get("processedDate", datetime.now().isoformat(timespec="seconds"))
    record_id = str(metadata.get("id", "sin_id"))

    try:
        dt       = datetime.fromisoformat(fecha)
        date_str = dt.strftime("%Y%m%d")
        time_str = dt.strftime("%H%M%S")
    except ValueError:
        date_str = datetime.now().strftime("%Y%m%d")
        time_str = datetime.now().strftime("%H%M%S")

    output_cfg   = config.get("output", {})
    output_base  = output_cfg.get("path", "resultados")
    dest_cfg     = config.get("output_destinations", {}).get(process, {})
    source_flags = config.get("source", {})

    # stem del WAV: DMCC_ext20184_2026_03_04_14;47;34;656
    from pathlib import Path as _Path
    audio_path = metadata.get("audioPath", "")
    audio_stem = _Path(audio_path).stem if audio_path else record_id

    saved_path: Optional[str] = None

    # local json
    if dest_cfg.get("local_json", True):
        from writer.json_writer import JsonWriter
        saved_path = JsonWriter(output_base).write(
            result, process, audio_stem
        )
        if saved_path:
            result["_saved_path"] = saved_path
            log.info(f"[writer] JSON → {saved_path}")

    # csv
    if dest_cfg.get("csv") and source_flags.get("csv"):
        try:
            from writer.csv_writer import CsvWriter
            CsvWriter(output_cfg.get("results_csv", "resultados/resultados.csv")).write(
                result, process, saved_path or ""
            )
            log.info("[writer] CSV appended")
        except Exception as e:
            log.error(f"[writer][csv] {e}")

    # mongo DB
    if dest_cfg.get("mongo_db") and source_flags.get("mongo_db"):
        try:
            from writer.mongo_writer import MongoWriter
            MongoWriter(config.get("mongo_db", {})).write(result, process)
            log.info("[writer] Mongo insertado")
        except Exception as e:
            log.error(f"[writer][mongo] {e}")

    #ws
    if dest_cfg.get("web_socket") and source_flags.get("web_socket"):
        try:
            from writer.websocket_writer import WebSocketWriter
            WebSocketWriter(config.get("web_socket", {})).write(result)
            log.info("[writer] WS notificado")
        except Exception as e:
            log.error(f"[writer][ws] {e}")

    return saved_path


__all__ = ["save"]