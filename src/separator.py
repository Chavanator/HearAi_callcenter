import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

#version
separator_version="V:1.1.3.2026"

def _load_prompt(prompt_file: str) -> str:
    if not prompt_file or not os.path.exists(prompt_file):
        raise FileNotFoundError(
            f"[separator] prompt_separation no encontrado: '{prompt_file}'"
        )
    with open(prompt_file, "r", encoding="utf-8") as f:
        return f.read()


def _build_llm_input(input_data: dict) -> str:
    fragments = input_data.get("fragments", [])
    if fragments:
        return "\n".join(
            f"[{fr['from']} → {fr['to']}] {fr['content']}"
            for fr in fragments
        )
    return input_data.get("content", "")


def _parse_response(raw: str) -> list:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            l for l in cleaned.splitlines()
            if not l.strip().startswith("```")
        ).strip()
    return json.loads(cleaned).get("transcription", [])


def separate(transcriber_result: dict, config: dict) -> Optional[dict]:
    from log import get_logger
    from providers import get_provider
    log = get_logger()

    input_data = transcriber_result.get("input", {})
    if not isinstance(input_data, dict):
        input_data = {"fragments": [], "content": transcriber_result.get("text", "")}

    if not input_data.get("content"):
        log.error("[separator] No hay texto en el resultado del transcriber")
        return None

    prompt_file = config.get("prompt_separation", "")
    try:
        prompt = _load_prompt(prompt_file)
    except FileNotFoundError as e:
        log.error(str(e))
        return None

    provider = get_provider(config)
    llm_input = _build_llm_input(input_data)

    t0 = time.time()
    try:
        log.info(f"[separator] Llamando a {provider.provider_name} …")
        raw, tokens_in, tokens_out, model_used = provider.call(prompt + llm_input)
    except Exception as e:
        log.error(f"[separator] Error LLM: {e}")
        return None

    processed_date = datetime.now().isoformat(timespec="seconds")
    duration_ms    = int((time.time() - t0) * 1000)

    try:
        conversation = _parse_response(raw)
    except (json.JSONDecodeError, KeyError) as e:
        log.error(f"[separator] No se pudo parsear respuesta: {e}\nRaw: {raw[:300]}")
        return None

    audio_path = transcriber_result.get("audio_path", "")
    record_id  = (
        transcriber_result.get("transaction_id")
        or transcriber_result.get("mongo_id")
        or Path(audio_path).stem
    )

    log.info(
        f"[separator] ✔ {len(conversation)} bloques | "
        f"tokens in={tokens_in} out={tokens_out} | {duration_ms} ms"
    )

    return {
        "process": "separacion",
        "metadata": {
            "id":            record_id,
            "requestedDate": transcriber_result.get("requestedAt", processed_date),
            "processedDate": processed_date,
            "source":        transcriber_result.get("source", "unknown"),
            "audioPath":     audio_path,
            "txtPath":       transcriber_result.get("txtPath", ""),
            "txtName":       transcriber_result.get("txtName", ""),
            "promptFile":    prompt_file,
            "aiProvider":    provider.provider_name,
            "model":         model_used,
            "tokensIn":      tokens_in,
            "tokensOut":     tokens_out,
            "durationMs":    duration_ms,
            "version":       separator_version,
        },
        "input":  input_data,
        "output": conversation,
    }