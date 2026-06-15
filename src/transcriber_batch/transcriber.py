import os
import sys
import csv
import json
import time
import logging
import tempfile
from math import ceil
from logging.handlers import TimedRotatingFileHandler
from pydub import AudioSegment

_ffmpeg = os.environ.get("FFMPEG_PATH")
if _ffmpeg:
    AudioSegment.converter = _ffmpeg
    AudioSegment.ffmpeg    = _ffmpeg
    AudioSegment.ffprobe   = os.environ.get("FFPROBE_PATH", _ffmpeg)


def load_config(path="config.json") -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, path)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"No se encontro config en: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_logger(log_dir: str, log_level: str = "INFO") -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger("Transcriber")

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, "transcriber.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def leer_csv(csv_path: str, columna: str) -> list:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV no encontrado: {csv_path}")

    rutas = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)

        if columna not in (reader.fieldnames or []):
            raise ValueError(
                f"Columna '{columna}' no encontrada en el CSV. "
                f"Columnas disponibles: {reader.fieldnames}"
            )

        for row in reader:
            ruta = row[columna].strip()
            if ruta:
                rutas.append(ruta)

    return rutas


def transcribir_audio(archivo: str, language: str, segment_seconds: int, logger: logging.Logger):
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
    except ImportError as e:
        raise ImportError(
            f"Dependencia faltante: {e}. "
            "Instala con: pip install SpeechRecognition pydub"
        ) from e

    if not os.path.exists(archivo):
        raise FileNotFoundError(f"Archivo no existe: {archivo}")

    if os.path.getsize(archivo) == 0:
        logger.warning(f"Archivo vacio (0 bytes), omitiendo: {archivo}")
        return None

    timestamp = str(int(time.time() * 1000))
    temp_dir = tempfile.gettempdir()
    archivo_convertido = os.path.join(temp_dir, f"tsc_pcm_{timestamp}.wav")

    try:
        # Cargar el OGG (o cualquier formato) y convertir a WAV 16kHz mono
        logger.info(f"  Convirtiendo audio a WAV 16kHz mono...")
        sound = AudioSegment.from_file(archivo)
        sound = sound.set_frame_rate(16000).set_channels(1)
        sound.export(archivo_convertido, format="wav")  # <-- corregido: era "ogg"

        audio = AudioSegment.from_wav(archivo_convertido)
        duracion_seg = len(audio) / 1000

        if duracion_seg < 1:
            logger.warning(f"Audio muy corto ({duracion_seg:.1f}s), omitiendo: {archivo}")
            return None

        segment_ms = segment_seconds * 1000
        num_segmentos = ceil(len(audio) / segment_ms)
        logger.info(f"  Duracion: {duracion_seg:.1f}s | Segmentos: {num_segmentos}")

        recognizer = sr.Recognizer()
        partes = []
        exitosos = 0
        vacios = 0
        errores = 0

        for i in range(num_segmentos):
            inicio = i * segment_ms
            fin = min((i + 1) * segment_ms, len(audio))
            fragmento = audio[inicio:fin]
            frag_path = os.path.join(temp_dir, f"tsc_frag_{timestamp}_{i}.wav")

            try:
                fragmento.export(frag_path, format="wav")
                with sr.AudioFile(frag_path) as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    audio_data = recognizer.record(source)

                texto = recognizer.recognize_google(audio_data, language=language)
                if texto and texto.strip():
                    partes.append(texto.strip())
                    exitosos += 1
                    logger.debug(f"  Segmento {i+1}/{num_segmentos}: OK ({len(texto)} chars)")
                else:
                    vacios += 1

            except sr.UnknownValueError:
                vacios += 1
                logger.debug(f"  Segmento {i+1}/{num_segmentos}: ininteligible")
            except sr.RequestError as e:
                errores += 1
                logger.warning(f"  Segmento {i+1}/{num_segmentos}: error de red - {e}")
            except Exception as e:
                errores += 1
                logger.warning(f"  Segmento {i+1}/{num_segmentos}: error - {e}")
            finally:
                _eliminar(frag_path)

        resultado = " ".join(partes).strip()

        if not resultado:
            logger.warning(
                f"Sin transcripcion valida - "
                f"Exitosos: {exitosos} | Vacios: {vacios} | Errores: {errores}"
            )
            return None

        logger.info(f"  {len(resultado)} caracteres | {exitosos}/{num_segmentos} segmentos OK")
        return resultado

    except (FileNotFoundError, ImportError):
        raise
    except Exception as e:
        logger.error(f"Error critico convirtiendo audio: {e}", exc_info=True)
        raise
    finally:
        _eliminar(archivo_convertido)


def _eliminar(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def guardar_transcripcion(archivo_audio: str, texto: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    nombre_base = os.path.splitext(os.path.basename(archivo_audio))[0]
    ruta_salida = os.path.join(output_dir, f"{nombre_base}_transcripcion.txt")

    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(texto)

    return ruta_salida


def main():
    cfg = load_config()

    logger = setup_logger(
        log_dir=cfg.get("log_dir", "logs"),
        log_level=cfg.get("log_level", "INFO")
    )

    output_dir = cfg.get("output_dir", "transcripciones")
    language   = cfg.get("language", "es-ES")
    seg_secs   = int(cfg.get("segment_duration_seconds", 60))
    skip_errors = cfg.get("skip_on_error", True)

    logger.info("=" * 60)
    logger.info("TRANSCRIPTOR DE AUDIO - INICIO")
    logger.info(f"Idioma:  {language}")
    logger.info(f"Salida:  {output_dir}")
    logger.info("=" * 60)

    # --- Obtener lista de archivos ---
    # Modo 1: un solo archivo (audio_input)
    # Modo 2: lista desde CSV (csv_input + csv_column)
    if "audio_input" in cfg:
        rutas = [cfg["audio_input"]]
        logger.info(f"Modo: archivo unico -> {cfg['audio_input']}")
    elif "csv_input" in cfg:
        columna = cfg.get("csv_column", "ruta_audio")
        logger.info(f"Modo: CSV -> {cfg['csv_input']} | Columna: {columna}")
        try:
            rutas = leer_csv(cfg["csv_input"], columna)
        except Exception as e:
            logger.error(f"Error leyendo CSV: {e}")
            sys.exit(1)
    else:
        logger.error("Config debe tener 'audio_input' (archivo unico) o 'csv_input' (lista CSV).")
        sys.exit(1)

    total  = len(rutas)
    ok     = 0
    vacios = 0
    fallos = 0

    logger.info(f"Archivos a procesar: {total}\n")

    for idx, ruta in enumerate(rutas, start=1):
        logger.info(f"[{idx}/{total}] {ruta}")

        try:
            texto = transcribir_audio(ruta, language, seg_secs, logger)

            if texto:
                salida = guardar_transcripcion(ruta, texto, output_dir)
                logger.info(f"  -> Guardado: {salida}")
                ok += 1
            else:
                logger.warning("  -> Sin transcripcion valida (audio vacio/mudo)")
                vacios += 1

        except FileNotFoundError as e:
            fallos += 1
            logger.error(f"  Archivo no encontrado: {e}")
            if not skip_errors:
                sys.exit(1)

        except Exception as e:
            fallos += 1
            logger.error(f"  Error procesando {ruta}: {e}", exc_info=True)
            if not skip_errors:
                sys.exit(1)

        print()

    logger.info("=" * 60)
    logger.info("RESUMEN FINAL")
    logger.info(f"  Total procesados : {total}")
    logger.info(f"  Exitosos         : {ok}")
    logger.info(f"  Sin voz          : {vacios}")
    logger.info(f"  Con error        : {fallos}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()