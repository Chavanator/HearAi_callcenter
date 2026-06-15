import os
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from log             import get_logger
from transcriber     import transcribe
from separator       import separate
from analyzer        import analyze
from sentimentor     import sentiment
from recovery_system import get_recovery_manager, get_watchdog, TimeoutManager

logger   = get_logger()
_stop    = threading.Event()
_LLM_TIMEOUT = 3000   # segundos


class Manager:

    def __init__(self, config: dict):
        self._cfg      = config
        self._features = config.get("processing_features", {})
        self._sql_cfg  = config.get("sql_polling", {})
        self._recovery = get_recovery_manager()
        self._failed_tids: set = set()  # blacklist sesion — wav sin audio útil
        self._in_progress: set = set()  # tids actualmente en proceso — evita re-pick del poll

        # SqlWriter
        self._sql: Optional[object] = None
        from connection_settings import ACTIVE_SOURCE
        if ACTIVE_SOURCE == "sql" and config.get("db_connection"):
            from writer.sql_writer import SqlWriter
            self._sql = SqlWriter(config["db_connection"])
        
                # MongoWriter
        self._mongo: Optional[object] = None
        mongo_cfg = config.get("mongo_db", {})
        if mongo_cfg.get("host"):
            from writer.mongo_writer import MongoWriter
            self._mongo = MongoWriter(mongo_cfg)

    # ── entrada ───────────────────────────────────────────────────────────────
    def run(self) -> int:
        from connection_settings import ACTIVE_SOURCE
        self._log_banner(ACTIVE_SOURCE)

        if not ACTIVE_SOURCE:
            logger.error("[manager] Ninguna fuente habilitada — abortando")
            return 1

        watchdog = get_watchdog()
        watchdog.start()

        self._run_debug()

        try:
            if ACTIVE_SOURCE in ("folder", "csv", "mongo_db"):
                self._run_once()

            elif ACTIVE_SOURCE == "sql":
                if not self._sql_cfg.get("enabled", False):
                    logger.error("[manager] source=sql pero sql_polling.enabled=false")
                    return 1
                self._run_sql_polling()

            elif ACTIVE_SOURCE == "web_socket":
                self._run_websocket()

            else:
                logger.error(f"[manager] Fuente desconocida: {ACTIVE_SOURCE}")
                return 1

        except KeyboardInterrupt:
            logger.info("[manager] Interrupción por teclado")
        except Exception as e:
            logger.error(f"[manager] Error fatal: {e}", exc_info=True)
            return 1
        finally:
            _stop.set()
            watchdog.stop()
            logger.info("=" * 60)
            logger.info("  AI EVALUATOR — DETENIDO")
            logger.info("=" * 60)

        return 0

    # ── exec mode ─────────────────────────────────────────────────────────────
    def _run_once(self) -> None:
        from reader import get_audio_records
        records = get_audio_records(self._cfg)
        logger.info(f"[manager] {len(records)} registros encontrados")
        for record in records:
            if _stop.is_set():
                break
            self._safe_process(record)

    def _run_sql_polling(self) -> None:
        trans = self._sql_cfg.get("transcription", {})
        ana   = self._sql_cfg.get("analysis",      {})
        sent  = self._sql_cfg.get("sentiment",     {})

        ti, ai, si = (
            trans.get("poll_interval_seconds", 15),
            ana.get("poll_interval_seconds",   30),
            sent.get("poll_interval_seconds",  15),
        )
        tb, ab, sb = (
            trans.get("max_records_per_batch", 5),
            ana.get("max_records_per_batch",   2),
            sent.get("max_records_per_batch",  2),
        )

        logger.info(
            f"[manager] SQL polling → trans:{ti}s(b={tb}) "
            f"ana:{ai}s(b={ab}) sent:{si}s(b={sb})"
        )
        last_t = last_a = last_s = 0.0

        while not _stop.is_set():
            now = time.time()
            self._poll_queue("transcription", tb, ti, last_t, now)
            if self._features.get("analysis_enabled", True):
                self._poll_queue("analysis", ab, ai, last_a, now)
            if self._features.get("sentiment_enabled", True):
                self._poll_queue("sentiment", sb, si, last_s, now)

            if now - last_t >= ti: last_t = now
            if now - last_a >= ai: last_a = now
            if now - last_s >= si: last_s = now

            _stop.wait(1)

    def _poll_queue(self, tipo: str, batch: int, interval: float,
                    last: float, now: float) -> None:
        if now - last < interval:
            return
        from reader import get_audio_records
        try:
            records = get_audio_records(self._cfg, sql_tipo_proceso=tipo)
            if records:
                pending = [r for r in records if r.get("transaction_id") not in self._in_progress]
                skipped = len(records) - len(pending)
                if skipped:
                    logger.debug(f"[manager] [{tipo}] {skipped} omitidos (en proceso)")
                if pending:
                    logger.info(f"[manager] [{tipo}] {len(pending)} pendientes")
                    for r in pending[:batch]:
                        if _stop.is_set():
                            break
                        self._safe_process(r, desde_proceso=tipo)
        except Exception as e:
            logger.error(f"[manager] Error polling {tipo}: {e}")

    def _run_websocket(self) -> None:
        from reader import start_websocket_listener, stop_websocket_listener
        logger.info("[manager] WebSocket listener activo")
        start_websocket_listener(self._cfg, callback=self._safe_process)
        while not _stop.is_set():
            _stop.wait(5)
        stop_websocket_listener()

    # ── pipeline de registro ──────────────────────────────────────────────────
    def _safe_process(self, record: dict, desde_proceso: str = "transcription") -> None:
        tid = record.get("transaction_id")
        if tid and tid in self._failed_tids:
            logger.debug(f"[manager] tid={tid} en blacklist de sesión — omitiendo")
            if desde_proceso == "analysis" and self._sql:
                self._sql.guardar_analisis(tid, "", "", 0, 0)
                logger.info(
                    f"[manager] tid={tid} limpiado de AudioAnalyzer "
                    "(blacklist — sin transcripción válida)"
                )
            return

        if tid:
            self._in_progress.add(tid)
        try:
            self._process_record(record, desde_proceso)
        except Exception as e:
            logger.error(
                f"[manager] Error inesperado procesando "
                f"{record.get('audio_path')}: {e}", exc_info=True
            )
        finally:
            if tid:
                self._in_progress.discard(tid)

    def _process_record(self, record: dict, desde_proceso: str = "transcription") -> bool:
        if "requestedAt" not in record:
            record["requestedAt"] = datetime.now().isoformat(timespec="seconds")

        tid    = record.get("transaction_id")
        audio  = record.get("audio_path", "")
        source = record.get("source", "unknown")

        logger.info(f"-- Procesando: {audio}  [source={source}]")

        # ── Filtro de duración mínima ─────────────────────────────────────────
        min_duration = self._cfg.get("min_audio_duration_seconds", 30)
        if audio and os.path.exists(audio):
            try:
                from pydub import AudioSegment as _AS
                _dur = len(_AS.from_file(audio)) / 1000.0
                if _dur < min_duration:
                    logger.warning(
                        f"[manager] tid={tid} descartado — duración {_dur:.1f}s "
                        f"< mínimo {min_duration}s"
                    )
                    if tid and source == "sql" and self._sql:
                        self._sql.marcar_como_error(
                            tid, f"Grabación demasiado corta ({_dur:.1f}s < {min_duration}s)"
                        )
                        self._failed_tids.add(tid)
                    return False
            except Exception as _e:
                logger.warning(f"[manager] No se pudo verificar duración de {audio}: {_e}")

        if tid and source == "sql" and self._sql:
            self._sql.actualizar_estado(tid, "Procesando")

        # ── Transcripción ─────────────────────────────────────────────────────
        t_result = self._get_transcription(record)
        if not t_result:
            logger.warning(f"Sin transcripción para: {audio}")
            if tid and source == "sql" and self._sql:
                retry = record.get("retry_count", 0) + 1
                max_r = self._sql_cfg.get("transcription", {}).get("max_retries", 1)
                if retry >= max_r:
                    self._sql.marcar_como_error(tid, "Sin transcripción válida")
                    self._failed_tids.add(tid)
                    logger.info(f"[manager] tid={tid} agregado a blacklist — WAV sin audio útil")
                    if desde_proceso == "analysis":
                        self._sql.guardar_analisis(tid, "", "", 0, 0)
                        logger.info(
                            f"[manager] tid={tid} limpiado de AudioAnalyzer "
                            "(sin transcripción — queue analysis)"
                        )
                else:
                    self._sql.actualizar_estado(tid, "Pendiente", retry)
            return False

        # ── Separación (queue transcription) ──────────────────────────────────
        if desde_proceso == "transcription" \
                and self._features.get("separation_enabled", True):

            el_sep = t_result.get("_el_separation_result")
            if el_sep:
                sep  = el_sep
                # FIX: reconstruir path si _el_sep_path no llegó
                path = t_result.get("_el_sep_path", "")
                if not path:
                    path = self._build_sep_path(audio, el_sep)
                    logger.warning(
                        f"[manager] _el_sep_path vacío — path reconstruido: {path}"
                    )
                logger.info(
                    f"[manager] Separación via ElevenLabs diarización "
                    f"— {len(sep.get('output', []))} turnos "
                    f"(sin LLM, tokensIn=0 tokensOut=0)"
                )
                logger.info(f"[manager] _el_sep_path = '{path}'")
            else:
                sep  = self._timeout(separate, "separate", t_result, self._cfg)
                path = self._save(sep) if sep else None

            if sep:
                if tid and source == "sql" and self._sql:
                    m = sep["metadata"]
                    self._sql.guardar_transcripcion(
                        tid, path or "", os.path.basename(path or ""),
                        m["tokensIn"], m["tokensOut"]
                    )
                    logger.info(                          # ← regresa aquí, dentro del if sql
                        f"[manager] TranscriptionPath ← {os.path.basename(path or '')} "
                        f"| IN={m['tokensIn']} OUT={m['tokensOut']}"
                    )
                if self._mongo and self._out_dest("separacion", "mongo_db"):
                    self._mongo.write(sep, "separacion")  # limpio, sin logger aquí
            else:
                logger.warning(f"Separación no completada: {audio}")

        # ── FIX: Registrar separacion.json de ElevenLabs si viene por analysis ─
        # Cuando el registro entra directo por el queue de analysis, el bloque
        # de separación de arriba no corre y TranscriptionPath queda vacío en
        # SQL aunque el archivo ya existe en disco.
        if desde_proceso == "analysis" \
                and self._features.get("separation_enabled", True):
            el_sep = t_result.get("_el_separation_result")
            if el_sep and tid and source == "sql" and self._sql:
                path = t_result.get("_el_sep_path", "")
                if not path:
                    path = self._build_sep_path(audio, el_sep)
                    logger.warning(
                        f"[manager] _el_sep_path vacío (analysis queue) — "
                        f"path reconstruido: {path}"
                    )
                m = el_sep["metadata"]
                self._sql.guardar_transcripcion(
                    tid, path, os.path.basename(path),
                    m["tokensIn"], m["tokensOut"]
                )
                logger.info(
                    f"[manager] TranscriptionPath (via analysis queue) ← "
                    f"{os.path.basename(path)} | IN={m['tokensIn']} OUT={m['tokensOut']}"
                )

        # ── Análisis ──────────────────────────────────────────────────────────
        if desde_proceso in ("transcription", "analysis") \
                and self._features.get("analysis_enabled", True):
            if not self._check_token_limit():
                logger.warning("[manager] Análisis omitido — límite mensual")
            else:
                raw_pid    = record.get("prompt_id")
                is_default = (not raw_pid) or (raw_pid.lower() == "default")
                lookup_id  = "defaprompt" if is_default else raw_pid
                meta_pid   = "default"    if is_default else raw_pid

                prompt_file_override = None
                if self._sql:
                    prompt_cfg = self._sql.obtener_prompt_config(lookup_id)
                    if prompt_cfg:
                        p_path = (prompt_cfg.get("Path") or "").rstrip("\\/")
                        p_name =  prompt_cfg.get("FileName") or ""
                        prompt_file_override = os.path.join(p_path, p_name) if p_name else None
                        logger.info(
                            f"[manager] Prompt '{lookup_id}' → {prompt_file_override}"
                        )
                    else:
                        logger.warning(
                            f"[manager] PromptConfiguration id='{lookup_id}' no encontrado "
                            "— usando prompt_analysis de config.json"
                        )

                ana = self._recovery_call(
                    analyze, "analyze",
                    t_result, self._cfg,
                    prompt_file_override, meta_pid,
                )
                if ana:
                    path = self._save(ana)
                    if tid and source == "sql" and self._sql:
                        m = ana["metadata"]
                        self._sql.guardar_analisis(
                            tid, path or "", os.path.basename(path or ""),
                            m["tokensIn"], m["tokensOut"], m["model"]
                        )
                    if self._mongo and self._out_dest("analisis", "mongo_db"):
                        self._mongo.write(ana, "analisis")
                else:
                    logger.warning(f"Análisis no completado: {audio}")
                    self._handle_retry(record, "analysis", tid, source,
                                       "Análisis no completado tras reintentos")

        # ── Sentimiento ───────────────────────────────────────────────────────
        if desde_proceso in ("transcription", "analysis", "sentiment") \
                and self._features.get("sentiment_enabled", True):
            if not self._check_token_limit():
                logger.warning("[manager] Sentimiento omitido — límite mensual")
            else:
                sent = self._recovery_call(sentiment, "sentiment", t_result, self._cfg)
                if sent:
                    path = self._save(sent)
                    if tid and source == "sql" and self._sql:
                        m = sent["metadata"]
                        self._sql.guardar_sentimiento(
                            tid, path or "", os.path.basename(path or ""),
                            m["tokensIn"], m["tokensOut"]
                        )
                    if self._mongo and self._out_dest("sentimiento", "mongo_db"):
                        self._mongo.write(sent, "sentimiento")
                else:
                    logger.warning(f"Sentimiento no completado: {audio}")
                    self._handle_retry(record, "sentiment", tid, source,
                                       "Sentimiento no completado tras reintentos")

        if tid and source == "sql" and self._sql:
            self._sql.actualizar_estado(tid, "Completado")

        logger.info(f"Completado: {audio}")
        return True

    # ── helpers internos ──────────────────────────────────────────────────────
    def _build_sep_path(self, audio: str, el_sep: dict) -> str:
        """Reconstruye la ruta del separacion.json desde audioPath del metadata."""
        audio_path = (
            el_sep.get("metadata", {}).get("audioPath", "")
            or audio
        )
        return str(Path(audio_path).parent / (Path(audio_path).stem + ";separacion.json"))

    def _get_transcription(self, record: dict) -> Optional[dict]:
        tp = record.get("transcription_path")
        if tp and os.path.exists(tp):
            try:
                raw = open(tp, encoding="utf-8").read()
                if not raw.strip():
                    return None

                fragments = []
                content   = raw  # fallback: texto plano

                try:
                    parsed = json.loads(raw)
                    turns  = parsed.get("output", [])
                    if turns and isinstance(turns, list) and "message" in turns[0]:
                        fragments = turns
                        content   = "\n".join(
                            f"[{t.get('from','?')}-{t.get('to','?')}] "
                            f"{t.get('type','UNKNOWN')}: {t.get('message','')}"
                            for t in turns
                            if t.get("message", "").strip()
                        )
                        logger.debug(
                            f"[manager] separacion.json parseado — "
                            f"{len(fragments)} turnos extraídos de {os.path.basename(tp)}"
                        )
                except (json.JSONDecodeError, IndexError, KeyError):
                    logger.debug(f"[manager] {os.path.basename(tp)} no es JSON de separación — usando texto plano")

                if not content.strip():
                    return None

                return {
                    **record,
                    "input":   {"fragments": fragments, "content": content},
                    "txtPath": tp,
                    "txtName": os.path.basename(tp),
                }
            except Exception as e:
                logger.error(f"[manager] Error leyendo transcripción existente: {e}")
                return None

        return self._timeout(transcribe, "transcribe", record)

    def _timeout(self, fn, name, *args, **kwargs):
        ok, result = TimeoutManager.run_with_timeout(fn, _LLM_TIMEOUT, *args, **kwargs)
        if not ok:
            logger.error(f"[manager] Timeout en '{name}' ({_LLM_TIMEOUT}s)")
            return None
        return result

    def _recovery_call(self, fn, name, *args, **kwargs):
        ok, result = self._recovery.execute_with_recovery_async(
            fn, name, _stop, *args, **kwargs
        )
        if not ok:
            logger.error(f"[manager] '{name}' falló tras todos los reintentos")
            return None
        return result

    def _save(self, result: dict) -> Optional[str]:
        """Guarda el resultado junto al WAV original."""
        from writer import save
        import copy
        meta       = result.get("metadata", {})
        audio_path = meta.get("audioPath", "") or result.get("audio_path", "")
        if audio_path:
            cfg = copy.deepcopy(self._cfg)
            cfg.setdefault("output", {})["path"] = os.path.dirname(audio_path)
            return save(result, cfg)
        return save(result, self._cfg)

    def _handle_retry(self, record, tipo, tid, source, error_msg):
        if not tid or source != "sql" or not self._sql:
            return
        retry = record.get("retry_count", 0) + 1
        max_r = self._sql_cfg.get(tipo, {}).get("max_retries", 3)
        if retry >= max_r:
            self._sql.marcar_como_error(tid, error_msg)
        else:
            self._sql.actualizar_estado(tid, "Pendiente", retry)

    def _check_token_limit(self) -> bool:
        limits = self._cfg.get("token_limits", {})
        if not limits.get("check_enabled", True):
            return True
        if not self._sql:
            return True
        monthly = limits.get("monthly_limit", 1_000_000)
        warn    = limits.get("warning_threshold", 0.8)
        try:
            mes   = int(datetime.now().month)
            total = self._sql.obtener_tokens_mes(mes).get("total", 0)
            pct   = total / monthly if monthly else 0
            if total >= monthly:
                logger.error(f"[manager] LÍMITE TOKENS: {total:,}/{monthly:,}")
                return False
            if pct >= warn:
                logger.warning(f"[manager] Tokens al {pct:.0%}: {total:,}/{monthly:,}")
        except Exception:
            pass
        return True

    def _run_debug(self) -> None:
        from debug_mode import run_debug_once
        run_debug_once(self._cfg)

    def _log_banner(self, source: str) -> None:
        f = self._features
        logger.info("=" * 60)
        logger.info("  AI EVALUATOR — INICIO")
        logger.info("=" * 60)
        logger.info(f"  Fuente activa  : {source.upper()}")
        logger.info(f"  Transcripcion  : {'OK' if f.get('transcription_enabled', True) else '--'}")
        logger.info(f"  Separacion     : {'OK' if f.get('separation_enabled',    True) else '--'}")
        logger.info(f"  Analisis       : {'OK' if f.get('analysis_enabled',      True) else '--'}")
        logger.info(f"  Sentimiento    : {'OK' if f.get('sentiment_enabled',     True) else '--'}")
        logger.info(f"  LLM timeout    : {_LLM_TIMEOUT}s")
        logger.info("=" * 60)

    def _out_dest(self, proceso: str, destino: str) -> bool:
        """Retorna True si el destino está habilitado para ese proceso."""
        return self._cfg.get("output_destinations", {}) \
                        .get(proceso, {}) \
                        .get(destino, False)