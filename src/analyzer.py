import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

#version
analyzer_version="V:1.2.3.2026"

def _load_prompt(prompt_file: str) -> str:
    if not prompt_file or not os.path.exists(prompt_file):
        raise FileNotFoundError(
            f"[analyzer] prompt_analysis no encontrado: '{prompt_file}'"
        )
    with open(prompt_file, "r", encoding="utf-8") as f:
        return f.read()


def _build_prompt(template: str, text: str) -> str:
    if "{call_text}" in template:
        return template.replace("{call_text}", text)
    return template + text


def _parse_response(raw: str):
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            l for l in cleaned.splitlines()
            if not l.strip().startswith("```")
        ).strip()
    return json.loads(cleaned)


def analyze(
    transcriber_result: dict,
    config: dict,
    prompt_file_override: str = None,
    prompt_id=None,
) -> Optional[dict]:
    from log import get_logger
    from providers import get_provider
    log = get_logger()

    input_data = transcriber_result.get("input", {})
    text = (
        input_data.get("content", "") if isinstance(input_data, dict)
        else transcriber_result.get("text", "")
    )
    if not text:
        log.error("[analyzer] No hay texto en el resultado del transcriber")
        return None

    # prompt_file_override tiene prioridad sobre config si no hay nada usa default
    prompt_file = prompt_file_override or config.get("prompt_analysis", "")
    resolved_prompt_id = prompt_id if prompt_id is not None else "default"

    try:
        prompt = _load_prompt(prompt_file)
    except FileNotFoundError as e:
        log.error(str(e))
        return None

    provider = get_provider(config)

    t0 = time.time()
    try:
        log.info(f"[analyzer] Llamando a {provider.provider_name} …")
        raw, tokens_in, tokens_out, model_used = provider.call(_build_prompt(prompt, text))
    except Exception as e:
        log.error(f"[analyzer] Error LLM: {e}")
        return None

    processed_date = datetime.now().isoformat(timespec="seconds")
    duration_ms    = int((time.time() - t0) * 1000)

    try:
        analysis_output = _parse_response(raw)
    except (json.JSONDecodeError, KeyError) as e:
        log.error(f"[analyzer] No se pudo parsear respuesta: {e}\nRaw: {raw[:300]}")
        return None

    audio_path = transcriber_result.get("audio_path", "")
    record_id  = (
        transcriber_result.get("transaction_id")
        or transcriber_result.get("mongo_id")
        or Path(audio_path).stem
    )

    log.info(
        f"[analyzer] ✔ Análisis completado | "
        f"tokens in={tokens_in} out={tokens_out} | {duration_ms} ms"
    )

    return {
        "process": "analisis",
        "metadata": {
            "id":            record_id,
            "requestedDate": transcriber_result.get("requestedAt", processed_date),
            "processedDate": processed_date,
            "source":        transcriber_result.get("source", "unknown"),
            "audioPath":     audio_path,
            "txtPath":       transcriber_result.get("txtPath", ""),
            "txtName":       transcriber_result.get("txtName", ""),
            "promptFile":    prompt_file,
            "promptId":      resolved_prompt_id,
            "aiProvider":    provider.provider_name,
            "model":         model_used,
            "tokensIn":      tokens_in,
            "tokensOut":     tokens_out,
            "durationMs":    duration_ms,
            "version":       analyzer_version,
        },
        "input":  input_data,
        "output": analysis_output,
    }