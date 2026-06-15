import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

elevenlabs_transcriber_version = "V:1.1.2.2026"

# ── config ────────────────────────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as _f:
    _config = json.load(_f)

_EL_CFG   = _config.get("elevenlabs_stt", {})
_API_KEY  = _EL_CFG.get("api_key", "")
_MODEL_ID = _EL_CFG.get("model", "scribe_v2")

# Etiquetas de canal: {"0": "AGENTE", "1": "CLIENTE"} en config.json
_RAW_LABELS     = _EL_CFG.get("channel_labels", {"0": "Agente", "1": "Cliente"})
_CHANNEL_LABELS = {int(k): v for k, v in _RAW_LABELS.items()}

_VALID_ROLES = {"agente": "Agente", "cliente": "Cliente"}

def _normalize_role(label: str) -> str:
    """Normaliza el label al casing esperado por la web: Agente / Cliente."""
    return _VALID_ROLES.get(label.strip().lower(), label.title())

# ── log ───────────────────────────────────────────────────────────────────────
try:
    from log import get_logger as _get_logger
    logger = _get_logger()
except ImportError:
    import logging as _logging
    logger = _logging.getLogger("elevenlabs_transcriber")
    _logging.basicConfig(level=_logging.INFO)

# ── post-procesamiento (diccionario) ─────────────────────────────────────────
try:
    from optimizer import post_procesar as _post_procesar
    _POST_PROCESAR_AVAILABLE = True
    logger.info("[eleven_transcriber] optimizer.post_procesar cargado correctamente")
except ImportError as _e:
    _POST_PROCESAR_AVAILABLE = False
    logger.warning(
        f"[eleven_transcriber] optimizer.py no disponible ({_e}) "
        "— se omitirá post-procesamiento del diccionario"
    )

    def _post_procesar(texto: str) -> str:
        return texto

# ── keyterms ──────────────────────────────────────────────────────────────────
def _cargar_keyterms() -> list[str]:
    keyterms: list[str] = []
 
    # fuente de keyterms
        # keyterms directos en config
    keyterms.extend(_EL_CFG.get("keyterms", []))

    # keyterms_file
    keyterms_file = _EL_CFG.get("keyterms_file", "")
    
    if keyterms_file and os.path.exists(keyterms_file):
        try:
            with open(keyterms_file, "r", encoding="utf-8") as f:
                ##eliminar comillas del diccionario (importante para evitar /)
                lines = [l.strip().strip('"\'') for l in f.readlines() if l.strip() and not l.startswith("#")]
            keyterms.extend(lines)
            logger.info(f"[eleven_transcriber] keyterms_file cargado: {len(lines)} términos — {keyterms_file}")
        except Exception as e:
            logger.warning(f"[eleven_transcriber] No se pudo leer keyterms_file: {e}")
    elif keyterms_file:
        logger.warning(f"[eleven_transcriber] keyterms_file no encontrado: {keyterms_file}")
 
    # deduplicar preservando orden
    seen = set()
    unique = []
    for k in keyterms:
        if k.lower() not in seen:
            seen.add(k.lower())
            unique.append(k)
 
    # límite de 1000 según ElevenLabs API
    if len(unique) > 1000:
        logger.warning(f"[eleven_transcriber] keyterms exceden el límite (1000) — truncando a 1000")
        unique = unique[:1000]
 
    if unique:
        logger.info(f"[eleven_transcriber] {len(unique)} keyterm(s) activos: {unique}")
    else:
        logger.info("[eleven_transcriber] Sin keyterms configurados")
 
    return unique
 
 
_KEYTERMS = _cargar_keyterms()
 

# ── helpers ───────────────────────────────────────────────────────────────────
def _format_time(seconds: float) -> str:
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _build_transcription_name(audio_path: str) -> str:
    return f"{Path(audio_path).stem};transcription.json"


def _build_separation_name(audio_path: str) -> str:
    return f"{Path(audio_path).stem};separacion.json"


def _detect_channels(audio_path: str) -> int:
    """Detecta cantidad de canales del WAV. Retorna 1 (mono) o 2+ (estéreo)."""
    try:
        from pydub import AudioSegment as _AS
        return _AS.from_file(audio_path).channels
    except Exception:
        return 1  # fallback seguro: asumir mono


def _parse_words(result) -> dict[int, list[dict]]:
    """
    Extrae palabras agrupadas por canal/speaker del resultado de ElevenLabs.
    Retorna {channel_int: [{"text", "start", "end"}, ...]}
    """
    words_by_channel: dict[int, list[dict]] = {}

    if hasattr(result, "transcripts"):
        # Modo multichannel (estéreo): un transcript por canal
        for transcript in result.transcripts:
            ch = int(transcript.channel_index)
            words_by_channel.setdefault(ch, [])
            if hasattr(transcript, "words"):
                for w in transcript.words:
                    words_by_channel[ch].append({
                        "text":  w.text,
                        "start": float(getattr(w, "start", 0) or 0),
                        "end":   float(getattr(w, "end",   0) or 0),
                        "wtype": getattr(w, "type", "word"),
                    })

    elif hasattr(result, "words"):
        # Modo mono con diarización: speaker_id puede ser int o "speaker_0"
        for w in result.words:
            raw_sid = getattr(w, "speaker_id", 0) or 0
            if isinstance(raw_sid, str):
                digits = "".join(c for c in raw_sid if c.isdigit())
                ch = int(digits) if digits else 0
            else:
                ch = int(raw_sid)
            words_by_channel.setdefault(ch, [])
            words_by_channel[ch].append({
                "text":  w.text,
                "start": float(getattr(w, "start", 0) or 0),
                "end":   float(getattr(w, "end",   0) or 0),
                "wtype": getattr(w, "type", "word"),
            })

    else:
        # Fallback: solo texto plano sin timestamps
        text = getattr(result, "text", "") or ""
        words_by_channel[0] = [{"text": text, "start": 0.0, "end": 0.0, "wtype": "word"}]

    return words_by_channel


def _map_speakers_to_roles(words_by_channel: dict[int, list[dict]]) -> dict[int, str]:
    """
    Mapea los speaker_ids de ElevenLabs a AGENTE/CLIENTE.

    Regla: los dos speakers con más palabras reales (type="word") son
    AGENTE y CLIENTE. El que habla primero entre esos dos es AGENTE,
    el segundo es CLIENTE. Los demás speakers (IVR, ruido) se fusionan
    al speaker dominante más cercano en el tiempo.
    """
    # Contar solo palabras reales por canal
    word_count: dict[int, int] = {}
    for ch, words in words_by_channel.items():
        word_count[ch] = sum(1 for w in words if w.get("wtype", "word") == "word")

    # Ordenar por cantidad de palabras descendente
    ranked = sorted(word_count.items(), key=lambda x: x[1], reverse=True)

    if not ranked:
        return {}

    if len(ranked) == 1:
        return {ranked[0][0]: _CHANNEL_LABELS.get(0, "Agente")}

    # Los dos con más palabras son los roles principales
    top_two = [ch for ch, _ in ranked[:2]]

    # Entre los dos, el que habla primero es AGENTE
    first_word: dict[int, float] = {}
    for ch in top_two:
        real_words = [w for w in words_by_channel[ch] if w.get("wtype", "word") == "word"]
        if real_words:
            first_word[ch] = min(w["start"] for w in real_words)
        else:
            first_word[ch] = float("inf")

    top_two_sorted = sorted(top_two, key=lambda ch: first_word.get(ch, float("inf")))
    agente_ch  = top_two_sorted[0]
    cliente_ch = top_two_sorted[1]

    mapping: dict[int, str] = {
        agente_ch:  _normalize_role(_CHANNEL_LABELS.get(0, "Agente")),
        cliente_ch: _normalize_role(_CHANNEL_LABELS.get(1, "Cliente")),
    }

    # Speakers extra (IVR, ruido, terceros) → omitir en _build_conversation
    for ch in word_count:
        if ch not in mapping:
            mapping[ch] = None

    return mapping


def _build_conversation(words_by_channel: dict[int, list[dict]]) -> list[dict]:
    """
    Construye turnos de conversación ordenados cronológicamente.
    Solo incluye AGENTE y CLIENTE. Formato: type, message, from, to.
    """
    role_map = _map_speakers_to_roles(words_by_channel)

    # Combinar palabras de todos los canales mapeados y ordenar por tiempo
    all_words = []
    for ch, words in words_by_channel.items():
        role = role_map.get(ch)
        if role is None:
            continue  # omitir speakers extra (IVR, ruido)
        for w in words:
            all_words.append({**w, "channel": ch, "role": role})
    all_words.sort(key=lambda x: x["start"])

    if not all_words:
        return []

    turns    = []
    cur_role = all_words[0]["role"]
    buf      = []
    t_start  = all_words[0]["start"]
    t_end    = all_words[0]["end"]

    def _flush():
        text = " ".join(buf).strip()
        if text:
            turns.append({
                "type":    cur_role,
                "message": text,
                "from":    _format_time(t_start),
                "to":      _format_time(t_end),
            })

    for w in all_words:
        if w["role"] == cur_role:
            buf.append(w["text"])
            t_end = w["end"]
        else:
            _flush()
            cur_role = w["role"]
            buf      = [w["text"]]
            t_start  = w["start"]
            t_end    = w["end"]

    _flush()
    return turns


def _build_plain_text(words_by_channel: dict[int, list[dict]]) -> str:
    """Texto plano completo de todos los canales ordenado por tiempo."""
    all_words = []
    for ch, words in words_by_channel.items():
        for w in words:
            all_words.append(w)
    all_words.sort(key=lambda x: x["start"])
    return " ".join(w["text"] for w in all_words if w["text"].strip())


# ── función principal ─────────────────────────────────────────────────────────
def transcribe_elevenlabs(record: dict) -> Optional[dict]:
    """
    Transcripción + diarización en un solo paso sin LLM.
    Retorna el mismo dict que transcribe() más _el_separation_result
    para que manager.py salte el paso de separación con LLM.
    """
    t_total    = time.time()
    audio_path = record.get("audio_path", "")

    logger.info("=" * 60)
    logger.info(f"[eleven_transcriber] INICIO (ElevenLabs) — {audio_path}")

    if not audio_path or not os.path.exists(audio_path):
        logger.error(f"[eleven_transcriber] Archivo no encontrado: {audio_path}")
        return None

    size_kb = os.path.getsize(audio_path) / 1024
    if size_kb == 0:
        logger.warning(f"[eleven_transcriber] Archivo vacío: {audio_path}")
        return None

    logger.info(f"[eleven_transcriber] Archivo: {size_kb:.1f} KB")

    if not _API_KEY or _API_KEY.strip() in ("", "XXXXXXXXXXX"):
        logger.error("[eleven_transcriber] elevenlabs_stt.api_key no configurada en config.json")
        return None

    try:
        from elevenlabs import ElevenLabs
        client = ElevenLabs(api_key=_API_KEY)
    except ImportError:
        logger.error("[eleven_transcriber] Librería 'elevenlabs' no instalada — pip install elevenlabs")
        return None

    # ── detectar canales y elegir modo ───────────────────────────────────────
    channels  = _detect_channels(audio_path)
    is_stereo = channels >= 2
    logger.info(
        f"[eleven_transcriber] Canales: {channels} "
        f"→ modo={'multichannel' if is_stereo else 'mono+diarize'}"
    )

    # ── llamada a ElevenLabs ──────────────────────────────────────────────────
    t0 = time.time()
    try:
        logger.info(f"[eleven_transcriber] Llamando a ElevenLabs ({_MODEL_ID}) …")
        with open(audio_path, "rb") as audio_file:
            if is_stereo:
                # Estéreo: canal 0 = AGENTE, canal 1 = CLIENTE garantizado
                result = client.speech_to_text.convert(
                    file=audio_file,
                    model_id=_MODEL_ID,
                    use_multi_channel=True,
                    timestamps_granularity="word",
                    keyterms=_KEYTERMS,
                )
            else:
                # Mono: diarización automática por speaker
                result = client.speech_to_text.convert(
                    file=audio_file,
                    model_id=_MODEL_ID,
                    diarize=True,
                    timestamps_granularity="word",
                    keyterms=_KEYTERMS,
                )
        duration_ms = int((time.time() - t0) * 1000)
        logger.info(f"[eleven_transcriber] ElevenLabs OK — {duration_ms} ms")
    except Exception as e:
        logger.error(f"[eleven_transcriber] Error ElevenLabs: {e}")
        return None

    # ── procesar palabras ─────────────────────────────────────────────────────
    words_by_channel = _parse_words(result)

    if not words_by_channel:
        logger.warning(f"[eleven_transcriber] Sin palabras en respuesta: {audio_path}")
        return None

    total_words = sum(len(v) for v in words_by_channel.values())
    logger.info(
        f"[eleven_transcriber] {len(words_by_channel)} canal(es) | "
        f"{total_words} palabras"
    )

    # ── construir conversación y texto plano ──────────────────────────────────
    conversation = _build_conversation(words_by_channel)
    content      = _build_plain_text(words_by_channel)

    if not conversation:
        logger.warning(f"[eleven_transcriber] Sin turnos útiles: {audio_path}")
        return None

    # ── post-procesamiento: aplicar diccionario al content y a cada turno ─────
    content_raw = content
    content     = _post_procesar(content)
    for turn in conversation:
        turn["message"] = _post_procesar(turn["message"])

    if _POST_PROCESAR_AVAILABLE:
        logger.info(
            f"[eleven_transcriber] post_procesar aplicado — "
            f"content: {len(content_raw)} → {len(content)} chars | "
            f"{len(conversation)} turno(s) corregidos"
        )

    logger.info(
        f"[eleven_transcriber] {len(content)} chars | "
        f"{len(conversation)} turno(s)"
    )

    # ── metadatos comunes ─────────────────────────────────────────────────────
    processed_date = datetime.now().isoformat(timespec="seconds")
    record_id = (
        record.get("transaction_id")
        or record.get("mongo_id")
        or Path(audio_path).stem
    )
    out_dir   = os.path.dirname(audio_path)
    json_name = _build_transcription_name(audio_path)
    json_path = os.path.join(out_dir, json_name)

    # ── guardar transcription.json (solo se guarda, la web no lo lee) ─────────
    transcription_payload = {
        "process": "transcripcion",
        "metadata": {
            "id":            record_id,
            "requestedDate": record.get("requestedAt", processed_date),
            "processedDate": processed_date,
            "source":        record.get("source", "unknown"),
            "audioPath":     audio_path,
            "jsonPath":      json_path,
            "jsonName":      json_name,
            "aiProvider":    "elevenlabs",
            "model":         _MODEL_ID,
            "version":       elevenlabs_transcriber_version,
        },
        "input":   None,
        "output":  [],       # sin fragmentos de 30s
        "content": content,  # texto plano ya post-procesado para el analyzer
    }

    try:
        with open(json_path, "w", encoding="utf-8") as out:
            json.dump(transcription_payload, out, ensure_ascii=False, indent=2)
        logger.info(f"[eleven_transcriber] transcription.json → {json_path}")
    except Exception as e:
        logger.error(f"[eleven_transcriber] No se pudo guardar transcription.json: {e}")
        return None

    # ── guardar separacion.json (este sí lo lee la web) ──────────────────────
    sep_name = _build_separation_name(audio_path)
    sep_path = os.path.join(out_dir, sep_name)

    separation_result = {
        "process": "separacion",
        "metadata": {
            "id":            record_id,
            "requestedDate": record.get("requestedAt", processed_date),
            "processedDate": processed_date,
            "source":        record.get("source", "unknown"),
            "audioPath":     audio_path,
            "txtPath":       json_path,
            "txtName":       json_name,
            "promptFile":    "elevenlabs_diarization",
            "aiProvider":    "elevenlabs",
            "model":         _MODEL_ID,
            "tokensIn":      0,
            "tokensOut":     0,
            "durationMs":    duration_ms,
            "version":       elevenlabs_transcriber_version,
        },
        "input":  {"fragments": [], "content": content},
        "output": conversation,   # [{type, message, from, to}, ...] ya post-procesado
    }

    try:
        with open(sep_path, "w", encoding="utf-8") as out:
            json.dump(separation_result, out, ensure_ascii=False, indent=2)
        logger.info(f"[eleven_transcriber] separacion.json → {sep_path}")
    except Exception as e:
        logger.error(f"[eleven_transcriber] No se pudo guardar separacion.json: {e}")
        # No fatal — el pipeline puede continuar

    duration_total = time.time() - t_total
    logger.info(
        f"[eleven_transcriber] COMPLETADO — {len(content)} chars | "
        f"{len(conversation)} turnos | tiempo total: {duration_total:.1f}s"
    )
    logger.info("=" * 60)

    # ── retorno compatible con transcribe() ───────────────────────────────────
    return {
        **record,
        "input": {
            "fragments": [],
            "content":   content,
        },
        "jsonName": json_name,
        "jsonPath": json_path,
        # Señal para que manager.py salte el paso LLM de separación
        "_el_separation_result": separation_result,
        "_el_sep_path":          sep_path,
        "_el_sep_name":          sep_name,
    }