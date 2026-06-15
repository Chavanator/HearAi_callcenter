import json
import os
import sys

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

# fuente de datos seleccionada
_source_cfg = config.get("source", {})
ACTIVE_SOURCE = next((k for k, v in _source_cfg.items() if v is True), None)

if ACTIVE_SOURCE is None:
    import warnings
    warnings.warn(
        "ADVERTENCIA: Ninguna fuente esta seleccionada en config. "
        "El sistema no procesará ningún audio hasta que se configure.",
        stacklevel=2,
    )
    ACTIVE_SOURCE = ""

print(f"[CONFIG] Fuente activa: {ACTIVE_SOURCE.upper()}")

# proveedor IA
AI_PROVIDER = config.get("ai_provider", "claude").lower()

# Claude
claude_cfg     = config.get("claude", {})
CLAUDE_API_KEY = claude_cfg.get("api_key", "")
CLAUDE_MODEL   = claude_cfg.get("model", "claude-haiku-4-5-20251001")

# Gemini
gemini_cfg     = config.get("Gemini", {})
GEMINI_API_KEY = gemini_cfg.get("api_key", "")
GEMINI_MODEL   = gemini_cfg.get("model", "models/gemini-2.0-flash-exp")

# prompts
PROMPT_SEPARATION = config.get("prompt_separation", "")
PROMPT_ANALYSIS   = config.get("prompt_analysis",   "")
PROMPT_SENTIMENT  = config.get("prompt_sentiment",  "")

# SQL
DB_CONNECTION_STRING = config.get("db_connection", "")

# WebSocket
_ws_cfg     = config.get("web_socket", {})
SERVER_HOST = _ws_cfg.get("host", config.get("server_host", "0.0.0.0"))
SERVER_PORT = int(_ws_cfg.get("port", config.get("server_port", 15001)))
RETRY_TIME  = int(config.get("retry_time", 5))

# Modo debug
DEBUG_MODE = config.get("debug_mode", {"enabled": False})

# Tokens por mes
TOKEN_LIMITS = config.get("token_limits", {
    "monthly_limit":     1_000_000,
    "warning_threshold": 0.8,
    "check_enabled":     True,
})

#caracterisicas activas
PROCESSING_FEATURES = config.get("processing_features", {
    "transcription_enabled": True,
    "separation_enabled":    True,  
    "analysis_enabled":      True,
    "sentiment_enabled":     True,
})

# SQL polling
SQL_POLLING_CONFIG = config.get("sql_polling", {
    "enabled": False,
    "transcription": {
        "sp_get_pending":        "GetPendingTranscription",
        "poll_interval_seconds": 15,
        "max_records_per_batch": 5,
        "max_retries":           1,
    },
    "analysis": {
        "sp_get_pending":        "GetPendingAnalisys",
        "poll_interval_seconds": 30,
        "max_records_per_batch": 2,
        "max_retries":           3,
    },
    "sentiment": {
        "sp_get_pending":        "GetPendingSentiment",
        "poll_interval_seconds": 15,
        "max_records_per_batch": 2,
        "max_retries":           3,
    },
    "sp_get_monthly_tokens": "GetTokensUsedByMonth",
})

# Transcripcion
TRANSCRIPTION_OUTPUT = config.get("transcription_output", {
    "path":            "transcripciones",
    "language":        "es-MX",
    "segment_seconds": 60,
    "name_format":     "{stem}_{date}_{time}",
})

# validar API keys
if AI_PROVIDER == "claude":
    if not CLAUDE_API_KEY or CLAUDE_API_KEY.strip() in ("", "xxxxxxxxx", "XXXXXXXXXXX"):
        raise ValueError("ERROR: 'claude.api_key' no está definida en config.json")

elif AI_PROVIDER in ("gemini", "google"):
    if not GEMINI_API_KEY or GEMINI_API_KEY.strip() in ("", "xxxxxxxxx", "XXXXXXXXXXX"):
        raise ValueError("ERROR: 'Gemini.api_key' no está definida en config.json")

else:
    raise ValueError(
        f"ERROR: ai_provider no válido: '{AI_PROVIDER}'. Use 'claude' o 'gemini'"
    )

# Resumen de inicio
print(f"[CONFIG] Proveedor IA      : {AI_PROVIDER.upper()} ({CLAUDE_MODEL if AI_PROVIDER == 'claude' else GEMINI_MODEL})")
print(f"[CONFIG] SQL Polling       : {'HABILITADO' if SQL_POLLING_CONFIG.get('enabled') else 'DESHABILITADO'}")
print(f"[CONFIG] Transcripción     : {'✔' if PROCESSING_FEATURES.get('transcription_enabled') else '✗'}")
print(f"[CONFIG] Separación        : {'✔' if PROCESSING_FEATURES.get('separation_enabled')    else '✗'}")
print(f"[CONFIG] Análisis          : {'✔' if PROCESSING_FEATURES.get('analysis_enabled')      else '✗'}")
print(f"[CONFIG] Sentimiento       : {'✔' if PROCESSING_FEATURES.get('sentiment_enabled')     else '✗'}")
print(f"[CONFIG] Límite tokens/mes : {TOKEN_LIMITS.get('monthly_limit'):,}")