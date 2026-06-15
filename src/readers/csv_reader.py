from reader.base_reader import BaseReader

class CsvReader(BaseReader):
    def __init__(self, cfg: dict):
        self._path      = cfg.get("path", "")
        self._delimiter = cfg.get("delimiter", ",")
        self._encoding  = cfg.get("encoding", "utf-8")

    def read(self, **_) -> list[dict]:
        import pandas as pd

        if not self._path:
            raise ValueError("[CsvReader] 'path' vacío en config → csv.path")

        data = pd.read_csv(self._path, delimiter=self._delimiter, encoding=self._encoding)

        if "directorio" not in data.columns:
            raise ValueError(
                f"[CsvReader] Columna 'directorio' no encontrada. "
                f"Columnas disponibles: {list(data.columns)}"
            )

        return [
            {
                "audio_path": str(row["directorio"]),
                "source": "csv",
                **{k: v for k, v in row.items() if k != "directorio"},
            }
            for _, row in data.iterrows()
        ]
