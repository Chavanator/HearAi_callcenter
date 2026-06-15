from pathlib import Path
from reader.base_reader import BaseReader

class FolderReader(BaseReader):
    def __init__(self, cfg: dict):
        self._path = cfg.get("path", "")

    def read(self, extension: str = "*.wav") -> list[dict]:
        if not self._path:
            raise ValueError("[FolderReader] 'path' vacío en config → folder.path")

        folder = Path(self._path)
        if not folder.exists():
            raise FileNotFoundError(f"[FolderReader] Carpeta no encontrada: {self._path}")

        files = list(folder.rglob(extension))
        return [{"audio_path": str(f), "source": "folder"} for f in files]
