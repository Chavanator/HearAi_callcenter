import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# localizar config
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_log_cfg: dict = {}
try:
    _config_path = os.path.join(BASE_DIR, "config.json")
    with open(_config_path, "r", encoding="utf-8") as _f:
        _log_cfg = json.load(_f).get("log", {})
except Exception:
    pass 

_LOG_DIR     = _log_cfg.get("path",    os.path.join(BASE_DIR, "logs"))
_LOG_LEVEL   = _log_cfg.get("level",   "INFO").upper()
_LOG_CONSOLE = _log_cfg.get("console", True)

# verificar y o crear carpeta de logs
Path(_LOG_DIR).mkdir(parents=True, exist_ok=True)

# formato
_FORMATTER = logging.Formatter(
    fmt   = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt = "%Y-%m-%d %H:%M:%S",
)

# crear un log diario
_log_filename = os.path.join(
    _LOG_DIR,
    f"ai_eval_{datetime.now().strftime('%Y%m%d')}.log"
)

_file_handler = TimedRotatingFileHandler(
    filename    = _log_filename,
    when        = "midnight",
    interval    = 1,
    backupCount = 365, #importante tiempo de vida de cada log en dias(1año)
    encoding    = "utf-8",
)
_file_handler.setFormatter(_FORMATTER)
_file_handler.suffix = "%Y%m%d"

# consola
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_FORMATTER)

# log root
_root = logging.getLogger("app")
_root.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))
_root.addHandler(_file_handler)
if _LOG_CONSOLE:
    _root.addHandler(_console_handler)
_root.propagate = False   # evitar duplicados con el root log

#funcion principl
def get_logger(name: str = "") -> logging.Logger:
    if not name:
        import inspect
        frame = inspect.stack()[1]
        name  = os.path.splitext(os.path.basename(frame.filename))[0]

    child = _root.getChild(name)
    child.setLevel(_root.level)
    return child

def log(message: str, level: str = "info") -> None:
    _fn = getattr(_root, level.lower(), _root.info)
    _fn(message)