import json
import os
import sys
import tempfile
import time
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Optional, List
import speech_recognition as sr
from pydub import AudioSegment


#version
transcriber_version="V:1.1.3.2026"


# config
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as _f:
    _config = json.load(_f)

_OUTPUT_DIR  = _config.get("transcription_output", {}).get("path",           "transcripciones")
_LANGUAGE    = _config.get("transcription_output", {}).get("language",        "es-MX")
_SEGMENT_SEC = _config.get("transcription_output", {}).get("segment_seconds", 30)
_NAME_FORMAT = _config.get("transcription_output", {}).get("name_format",     "{stem}_{date}_{time}")

Path(_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

_LANGUAGE_FALLBACK = _config.get("transcription_output", {}).get("alt_lan", "es-ES")

# noise config
_NOISE_CFG   = _config.get("transcription_output", {}).get("noise_handling", {})
_FRESH_REC   = _NOISE_CFG.get("fresh_recognizer",    True)
_ENERGY_THR  = _NOISE_CFG.get("energy_threshold",    4000)
_DYNAMIC_E   = _NOISE_CFG.get("dynamic_energy",      True)
_DAMPING     = _NOISE_CFG.get("damping",              0.08)
_RATIO       = _NOISE_CFG.get("ratio",                1.2)
_PAUSE_THR   = _NOISE_CFG.get("pause_threshold",     0.5)
_PROP_FACTOR = _NOISE_CFG.get("proportional_factor", 0.05)
_CAL_MIN     = _NOISE_CFG.get("calibration_min",     0.1)
_CAL_MAX     = _NOISE_CFG.get("calibration_max",     1.5)

# log
try:
    from log import get_logger as _get_logger
    logger = _get_logger()
except ImportError:
    import logging as _logging
    logger = _logging.getLogger("transcriber")
    _logging.basicConfig(level=_logging.INFO)

# optimizer
try:
    from optimizer import mejorar_audio, configurar_recognizer, post_procesar  # FIX #4
    _OPTIMIZER_AVAILABLE = True
    logger.info("[transcriber] Optimizer cargado correctamente")
except ImportError as _e:
    _OPTIMIZER_AVAILABLE = False
    logger.warning(
        f"[transcriber] optimizer.py no disponible ({_e}) — "
        "se usara transcripcion basica sin mejoras"
    )

    def mejorar_audio(ruta, ruta_salida=None):
        return ruta

    def configurar_recognizer(recognizer):
        return recognizer

    def post_procesar(texto: str) -> str:  # stub cuando optimizer no está disponible
        return texto


# helpers
def _format_time(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _build_output_name(audio_path: str) -> str:
    stem = Path(audio_path).stem
    return f"{stem};transcription.json"


def _convert_to_pcm(audio_path: str, dest_path: str) -> None:
    sound = AudioSegment.from_file(audio_path)
    sound = sound.set_frame_rate(16000).set_channels(1)
    sound.export(dest_path, format="wav")


def _make_recognizer() -> sr.Recognizer:
    rec = configurar_recognizer(sr.Recognizer())
    rec.energy_threshold                  = _ENERGY_THR
    rec.dynamic_energy_threshold          = _DYNAMIC_E
    rec.dynamic_energy_adjustment_damping = _DAMPING
    rec.dynamic_energy_adjustment_ratio   = _RATIO
    rec.pause_threshold                   = _PAUSE_THR
    return rec


_shared_recognizer: Optional[sr.Recognizer] = None


def _get_recognizer() -> sr.Recognizer:
    global _shared_recognizer
    if _FRESH_REC:
        return _make_recognizer()          # nuevo por cada fragmento
    if _shared_recognizer is None:
        _shared_recognizer = _make_recognizer()
    return _shared_recognizer              # reutilizar entre fragmentos


# stt
def _reconocer_fragmento(
    frag_path: str,
    num: int,
    total: int,
) -> str:
    rec = _get_recognizer() 

    with sr.AudioFile(frag_path) as src:
        duracion_frag = src.DURATION
        calibracion = max(_CAL_MIN, min(_CAL_MAX, duracion_frag * _PROP_FACTOR))
        rec.adjust_for_ambient_noise(src, duration=calibracion)
        data = rec.record(src)

    logger.debug(
        f"[transcriber]   [{num}/{total}] "
        f"dur={duracion_frag:.1f}s cal={calibracion:.2f}s "
        f"energy={rec.energy_threshold:.0f} fresh={_FRESH_REC}"
    )

    # intento principal
    try:
        texto = rec.recognize_google(data, language=_LANGUAGE)
        logger.info(
            f"[transcriber]   [{num}/{total}] OK ({_LANGUAGE}) — "
            f"{len(texto)} chars"
        )
        return texto

    except sr.UnknownValueError:
        logger.warning(
            f"[transcriber]   [{num}/{total}] No entendido en {_LANGUAGE}, "
            f"reintentando con {_LANGUAGE_FALLBACK}"
        )

    # fallback de idioma
    try:
        texto = rec.recognize_google(data, language=_LANGUAGE_FALLBACK)
        logger.info(
            f"[transcriber]   [{num}/{total}] OK ({_LANGUAGE_FALLBACK}) — "
            f"{len(texto)} chars"
        )
        return texto

    except sr.UnknownValueError:
        logger.warning(
            f"[transcriber]   [{num}/{total}] Sin resultado — "
            "fragmento silencioso o ininteligible"
        )
        return ""

    except sr.RequestError as e:
        logger.error(f"[transcriber]   [{num}/{total}] Error de red: {e}")
        return ""


def _transcribe_wav(wav_path: str) -> Optional[List[dict]]:
    t_inicio = time.time()

    audio = AudioSegment.from_wav(wav_path)

    duracion_total_ms  = len(audio)
    duracion_total_seg = duracion_total_ms / 1000
    seg_ms             = _SEGMENT_SEC * 1000
    n_segmentos        = ceil(duracion_total_ms / seg_ms)

    logger.info(
        f"[transcriber] Duracion: {duracion_total_seg:.1f}s | "
        f"fragmento={_SEGMENT_SEC}s | total fragmentos={n_segmentos} | "
        f"idioma={_LANGUAGE} | fallback={_LANGUAGE_FALLBACK} | "
        f"noise: energy={_ENERGY_THR} damping={_DAMPING} ratio={_RATIO} fresh={_FRESH_REC}"
    )

    tmp_dir   = tempfile.gettempdir()
    ts        = str(int(time.time() * 1000))
    fragments = []

    for i in range(n_segmentos):
        num       = i + 1
        frag_path = os.path.join(tmp_dir, f"_frag_{ts}_{i}.wav")
        inicio_ms = i * seg_ms
        fin_ms    = min((i + 1) * seg_ms, duracion_total_ms)
        duracion_frag = (fin_ms - inicio_ms) / 1000

        logger.info(
            f"[transcriber]   [{num}/{n_segmentos}] "
            f"{inicio_ms/1000:.1f}s → {fin_ms/1000:.1f}s "
            f"({duracion_frag:.1f}s)"
        )

        try:
            fragmento = audio[inicio_ms:fin_ms]
            fragmento.export(frag_path, format="wav")
            texto = _reconocer_fragmento(frag_path, num, n_segmentos)
            if texto:
                fragments.append({
                    "from":    _format_time(inicio_ms / 1000),
                    "to":      _format_time(fin_ms / 1000),
                    "content": texto,
                })

        except Exception as e:
            logger.error(f"[transcriber]   [{num}/{n_segmentos}] Error inesperado: {e}")

        finally:
            try:
                if os.path.exists(frag_path):
                    os.remove(frag_path)
            except Exception:
                pass

    duracion_proc = time.time() - t_inicio
    exitosos      = len(fragments)
    logger.info(
        f"[transcriber] Fragmentos exitosos: {exitosos}/{n_segmentos} | "
        f"tiempo STT: {duracion_proc:.1f}s"
    )

    return fragments if fragments else None


# transcribe — funcion principal
def transcribe(record: dict) -> Optional[dict]:
    # Routing: si stt_provider == "elevenlabs" delegar al módulo dedicado
    # que hace transcripción + diarización en un solo paso sin LLM
    if _config.get("stt_provider", "google").lower() == "elevenlabs":
        try:
            from elevenlabs_transcriber import transcribe_elevenlabs
            return transcribe_elevenlabs(record)
        except Exception as e:
            logger.error(
                f"[transcriber] Error al cargar elevenlabs_transcriber: {e} "
                "— cayendo a Google STT"
            )

    t_total    = time.time()
    audio_path = record.get("audio_path", "")

    logger.info("=" * 60)
    logger.info(f"[transcriber] INICIO — {audio_path}")

    if not audio_path or not os.path.exists(audio_path):
        logger.error(f"[transcriber] Archivo no encontrado: {audio_path}")
        return None

    size_kb = os.path.getsize(audio_path) / 1024
    if size_kb == 0:
        logger.warning(f"[transcriber] Archivo vacio: {audio_path}")
        return None

    logger.info(f"[transcriber] Archivo: {size_kb:.1f} KB")
    logger.info("[transcriber] Paso 1/3 — Mejora de audio (normalizacion)")
    ts            = str(int(time.time() * 1000))
    tmp_norm      = os.path.join(tempfile.gettempdir(), f"_norm_{ts}.wav")
    ruta_mejorada = mejorar_audio(audio_path, tmp_norm)
    audio_mejorado = (ruta_mejorada != audio_path)

    logger.info("[transcriber] Paso 2/3 — Conversion a PCM 16kHz mono")
    tmp_pcm = os.path.join(tempfile.gettempdir(), f"_pcm_{ts}.wav")

    try:
        _convert_to_pcm(ruta_mejorada, tmp_pcm)
    except Exception as e:
        logger.error(f"[transcriber] No se pudo convertir el audio: {e}")
        _limpiar(tmp_norm if audio_mejorado else None)
        return None
    finally:
        if audio_mejorado:
            _limpiar(tmp_norm)

    logger.info("[transcriber] Paso 3/3 — Transcripcion STT literal (Google)")
    t_stt = time.time()
    try:
        fragments = _transcribe_wav(tmp_pcm)
    finally:
        _limpiar(tmp_pcm)

    if not fragments:
        logger.warning(f"[transcriber] Sin texto util para: {audio_path}")
        return None
    raw_content = " ".join(f["content"] for f in fragments)
    content     = post_procesar(raw_content)

    if content != raw_content:
        logger.info(
            f"[transcriber] post_procesar aplicado — "
            f"{len(raw_content)} → {len(content)} chars"
        )

    logger.info(
        f"[transcriber] STT completado en {time.time()-t_stt:.1f}s — "
        f"{len(fragments)} fragmentos | {len(content)} chars"
    )

# guardar — siempre junto al WAV, formato estructurado completo
    json_name      = _build_output_name(audio_path)
    out_dir        = os.path.dirname(audio_path)
    json_path      = os.path.join(out_dir, json_name)
    processed_date = datetime.now().isoformat(timespec="seconds")

    record_id = (
        record.get("transaction_id")
        or record.get("mongo_id")
        or Path(audio_path).stem
    )

    payload = {
        "process": "transcripcion",
        "metadata": {
            "id":            record_id,
            "requestedDate": record.get("requestedAt", processed_date),
            "processedDate": processed_date,
            "source":        record.get("source", "unknown"),
            "audioPath":     audio_path,
            "jsonPath":      json_path,
            "jsonName":      json_name,
            "version":       transcriber_version,
        },
        "input": None,
        # output es array de fragments para compatibilidad con la web (.forEach)
        "output": fragments,
        # content separado para uso del pipeline interno
        "content": content,
    }

    try:
        with open(json_path, "w", encoding="utf-8") as out:
            json.dump(payload, out, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[transcriber] No se pudo guardar JSON: {e}")
        return None

    duracion_total = time.time() - t_total
    logger.info(
        f"[transcriber] COMPLETADO — {json_path} | "
        f"{len(content)} chars | tiempo total: {duracion_total:.1f}s"
    )
    logger.info("=" * 60)

    return {
        **record,
        "input": {
            "fragments": fragments,
            "content":   content,
        },
        "jsonName": json_name,
        "jsonPath": json_path,
    }


def _limpiar(ruta: Optional[str]) -> None:
    if ruta and os.path.exists(ruta):
        try:
            os.remove(ruta)
        except Exception:
            pass