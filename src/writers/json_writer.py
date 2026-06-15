import json
from pathlib import Path
from typing import Optional


class JsonWriter:
    def __init__(self, output_base: str):
        self._base = output_base

    def write(self, result: dict, process: str, audio_stem: str) -> Optional[str]:
        output_dir = Path(self._base)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename  = f"{audio_stem};{process}.json"
        file_path = output_dir / filename

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)
            return str(file_path)
        except Exception as e:
            from log import get_logger
            get_logger().error(f"[JsonWriter] Error guardando {filename}: {e}")
            return None