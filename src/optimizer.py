import ast
import os
import re
import sys
import time
import json
from math import ceil
from pathlib import Path
from typing import Optional
from pydub import AudioSegment
from pydub.effects import normalize
import speech_recognition as sr

#version
optimizer_version="V:1.1.3.2026"


# config
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as _f:
    _config = json.load(_f)

_LANGUAGE    = _config.get("transcription_output", {}).get("language", "es-MX")
_SEGMENT_SEC = _config.get("transcription_output", {}).get("segment_seconds", 30)


# log
try:
    from log import get_logger as _get_logger
    logger = _get_logger()
except ImportError:
    import logging as _logging
    logger = _logging.getLogger("optimizer")
    _logging.basicConfig(level=_logging.INFO)


# diccionario
def _cargar_diccionario(ruta: str) ->  Optional[dict]:
    if not ruta or not os.path.exists(ruta):
        logger.warning(f"[optimizer] Diccionario no encontrado: '{ruta}' — se omite post-procesamiento")
        return {}

    try:
        with open(ruta, "r", encoding="utf-8") as f:
            raw = f.read()

        lines = []
        for line in raw.splitlines():
            stripped = line.rstrip()
            if stripped.lstrip().startswith("#"):
                continue
            in_str     = False
            quote_char = None
            for idx, ch in enumerate(stripped):
                if not in_str and ch in ('"', "'"):
                    in_str     = True
                    quote_char = ch
                elif in_str and ch == quote_char:
                    in_str = False
                elif not in_str and ch == "#":
                    stripped = stripped[:idx].rstrip()
                    break
            lines.append(stripped)

        diccionario = ast.literal_eval("\n".join(lines))
        logger.info(f"[optimizer] Diccionario cargado: {len(diccionario)} entradas — {ruta}")
        return diccionario

    except Exception as e:
        logger.error(f"[optimizer] Error cargando diccionario '{ruta}': {e}")
        return {}


_DICT_PATH   = _config.get("diccionario", "")
_DICCIONARIO = _cargar_diccionario(_DICT_PATH)

_TERMINOS_MAYUSCULAS: list[str] = [
    v for v in _DICCIONARIO.values()
    if isinstance(v, str) and v != v.lower()
]


# mejora de audio
def mejorar_audio(ruta_archivo: str, ruta_salida: Optional[str] = None) -> str:
    try:
        logger.info(f"[optimizer] Normalizando audio: {ruta_archivo}")
        audio              = AudioSegment.from_wav(ruta_archivo)
        audio_normalizado  = normalize(audio)

        if ruta_salida is None:
            ruta_salida = str(Path(ruta_archivo).with_stem(
                Path(ruta_archivo).stem + "_norm"
            ))

        audio_normalizado.export(ruta_salida, format="wav")
        duracion = len(audio_normalizado) / 1000
        logger.info(
            f"[optimizer] Audio normalizado → {ruta_salida}  "
            f"(duracion={duracion:.1f}s)"
        )
        return ruta_salida

    except Exception as e:
        logger.warning(f"[optimizer] No se pudo normalizar audio, se usa original: {e}")
        return ruta_archivo


# post-procesamiento de texto
def post_procesar(texto: str) -> str:
    if not texto or not texto.strip():
        return texto

    t = texto

    if _DICCIONARIO:
        for error, correcto in _DICCIONARIO.items():
            patron = re.compile(re.escape(error), re.IGNORECASE)
            t = patron.sub(correcto, t)
        logger.debug(f"[optimizer] Diccionario aplicado ({len(_DICCIONARIO)} reglas)")

    t = " ".join(t.split())

    patron_num = re.compile(r"\b(\d{1,3})\s(\d{3})\b")
    prev = None
    while prev != t:
        prev = t
        t = patron_num.sub(r"\1,\2", t)

    for termino in _TERMINOS_MAYUSCULAS:
        patron = re.compile(r"\b" + re.escape(termino.lower()) + r"\b", re.IGNORECASE)
        t = patron.sub(termino, t)

    oraciones = t.split(". ")
    t = ". ".join(s.strip().capitalize() if s.strip() else s for s in oraciones)

    t = t.encode("utf-8", errors="ignore").decode("utf-8")

    return t


# config recognizer optimizado para callcenter
def configurar_recognizer(recognizer: sr.Recognizer) -> sr.Recognizer:
    recognizer.energy_threshold         = 4000
    recognizer.dynamic_energy_threshold = True
    logger.debug(
        f"[optimizer] Recognizer configurado: "
        f"energy_threshold={recognizer.energy_threshold}, "
        f"dynamic={recognizer.dynamic_energy_threshold}"
    )
    return recognizer


# uso desde línea de comando
def _transcribir_standalone(ruta_archivo: str, mejorar: bool = True,
                             fragmentar: bool = True) -> Optional[str]:
    import tempfile

    ruta = ruta_archivo

    if mejorar:
        tmp = os.path.join(tempfile.gettempdir(), "_opt_norm.wav")
        ruta = mejorar_audio(ruta_archivo, tmp)

    recognizer = configurar_recognizer(sr.Recognizer())
    audio      = AudioSegment.from_wav(ruta)
    duracion   = len(audio) / 1000
    seg_ms     = _SEGMENT_SEC * 1000

    logger.info(f"[optimizer] Duracion total: {duracion:.1f}s | fragmento={_SEGMENT_SEC}s")

    if not fragmentar or duracion <= _SEGMENT_SEC:
        logger.info("[optimizer] Audio corto — procesando completo")
        with sr.AudioFile(ruta) as src:
            recognizer.adjust_for_ambient_noise(src, duration=0.3)
            data = recognizer.record(src)
        try:
            texto = recognizer.recognize_google(data, language=_LANGUAGE)
        except sr.UnknownValueError:
            logger.warning(f"[optimizer] No entendido en {_LANGUAGE}, intentando es-ES")
            texto = recognizer.recognize_google(data, language="es-ES")
        return post_procesar(texto)

    n_frags = ceil(len(audio) / seg_ms)
    logger.info(f"[optimizer] Procesando {n_frags} fragmentos...")
    partes  = []

    for i in range(0, len(audio), seg_ms):
        num    = i // seg_ms + 1
        tmpf   = os.path.join(tempfile.gettempdir(), f"_opt_frag_{num}.wav")
        frag   = audio[i : i + seg_ms]
        frag.export(tmpf, format="wav")

        try:
            with sr.AudioFile(tmpf) as src:
                recognizer.adjust_for_ambient_noise(src, duration=0.3)
                data = recognizer.record(src)

            try:
                txt = recognizer.recognize_google(data, language=_LANGUAGE)
                logger.info(f"[optimizer]   [{num}/{n_frags}] OK — {len(txt)} chars")
                partes.append(txt)
            except sr.UnknownValueError:
                logger.warning(f"[optimizer]   [{num}/{n_frags}] No entendido, reintentando es-ES")
                try:
                    txt = recognizer.recognize_google(data, language="es-ES")
                    partes.append(txt)
                except sr.UnknownValueError:
                    logger.warning(f"[optimizer]   [{num}/{n_frags}] Sin resultado (silencio?)")
            except sr.RequestError as e:
                logger.error(f"[optimizer]   [{num}/{n_frags}] Error de red: {e}")
        except Exception as e:
            logger.error(f"[optimizer]   [{num}/{n_frags}] Error inesperado: {e}")
        finally:
            try:
                Path(tmpf).unlink(missing_ok=True)
            except Exception:
                pass

    texto = " ".join(p for p in partes if p)
    return post_procesar(texto) if texto else None


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python optimizer.py <archivo.wav> [--sin-mejora] [--sin-fragmentos]")
        sys.exit(1)

    ruta      = sys.argv[1]
    mejorar   = "--sin-mejora"      not in sys.argv
    fragmentar = "--sin-fragmentos" not in sys.argv

    t0     = time.time()
    result = _transcribir_standalone(ruta, mejorar=mejorar, fragmentar=fragmentar)
    duracion = time.time() - t0

    if result:
        print("\n" + "=" * 70)
        print("RESULTADO")
        print("=" * 70)
        print(result)
        print("=" * 70)
        print(f"Tiempo: {duracion:.1f}s")

        salida = Path(ruta).stem + "_transcripcion.txt"
        with open(salida, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"Guardado en: {salida}")
    else:
        print("No se pudo completar la transcripcion")
        sys.exit(1)


if __name__ == "__main__":
    main()