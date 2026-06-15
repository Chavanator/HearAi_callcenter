import os
import traceback
from typing import Optional


def run_debug_once(config: dict) -> None:
    debug_cfg = config.get("debug_mode", {})
    if not debug_cfg.get("enabled", False):
        return

    from log import get_logger
    log = get_logger()

    wav = debug_cfg.get("wav_file", "")
    if not wav or not os.path.exists(wav):
        log.error(f"[debug] Archivo WAV no encontrado: {wav}")
        return

    log.info("=" * 60)
    log.info("🔧 MODO DEBUG ACTIVADO")
    log.info("=" * 60)
    log.info(f"[debug] Archivo : {wav}")
    log.info("[debug] Sin escritura a BD | pollers pausados")
    log.info("=" * 60)

    from transcriber import transcribe
    from separator   import separate
    from analyzer    import analyze
    from sentimentor import sentiment
    from writer      import save

    features        = config.get("processing_features", {})
    record          = {"audio_path": wav, "source": "debug", "transaction_id": 999999}
    total_in = total_out = 0

    try:
        # transcripcion
        log.info("[debug] Paso 1/4 → Transcripción …")
        t_result = transcribe(record)
        if not t_result:
            log.warning("[debug] Sin transcripción — abortando")
            return

        content_len = len(t_result.get("input", {}).get("content", ""))
        log.info(f"[debug] ✔ Transcripción: {content_len} chars → {t_result.get('txtPath')}")

        # separacion
        if features.get("separation_enabled", True):
            log.info("[debug] Paso 2/4 → Separación …")
            sep = separate(t_result, config)
            if sep:
                m = sep["metadata"]
                total_in += m["tokensIn"]; total_out += m["tokensOut"]
                save(sep, config)
                log.info(f"[debug] ✔ Separación: {len(sep['output'])} bloques | IN={m['tokensIn']} OUT={m['tokensOut']}")
            else:
                log.warning("[debug] ⚠ Separación no completada")
        else:
            log.info("[debug] Paso 2/4 → Separación DESHABILITADA")

        # analisis
        if features.get("analysis_enabled", True):
            log.info("[debug] Paso 3/4 → Análisis …")
            ana = analyze(t_result, config)
            if ana:
                m = ana["metadata"]
                total_in += m["tokensIn"]; total_out += m["tokensOut"]
                save(ana, config)
                log.info(f"[debug] ✔ Análisis completado | IN={m['tokensIn']} OUT={m['tokensOut']}")
            else:
                log.warning("[debug] ⚠ Análisis no completado")
        else:
            log.info("[debug] Paso 3/4 → Análisis DESHABILITADO")

        # sentimiento
        if features.get("sentiment_enabled", True):
            log.info("[debug] Paso 4/4 → Sentimiento …")
            sent = sentiment(t_result, config)
            if sent:
                m = sent["metadata"]
                total_in += m["tokensIn"]; total_out += m["tokensOut"]
                save(sent, config)
                log.info(f"[debug] ✔ Sentimiento completado | IN={m['tokensIn']} OUT={m['tokensOut']}")
            else:
                log.warning("[debug] ⚠ Sentimiento no completado")
        else:
            log.info("[debug] Paso 4/4 → Sentimiento DESHABILITADO")

        log.info("=" * 60)
        log.info(f"✔ DEBUG COMPLETADO — Tokens IN={total_in} OUT={total_out}")
        log.info("=" * 60)

    except Exception as e:
        log.error(f"[debug] Error inesperado: {e}")
        log.error(traceback.format_exc())