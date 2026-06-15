import csv
import os


class CsvWriter:
    def __init__(self, csv_path: str):
        self._path = csv_path

    def write(self, result: dict, process: str, json_path: str = "") -> None:
        metadata = result.get("metadata", {})
        row = {
            "id":            metadata.get("id", ""),
            "proceso":       process,
            "requestedDate": metadata.get("requestedDate", ""),
            "processedDate": metadata.get("processedDate", ""),
            "source":        metadata.get("source", ""),
            "audioPath":     metadata.get("audioPath", ""),
            "txtPath":       metadata.get("txtPath", ""),
            "aiProvider":    metadata.get("aiProvider", ""),
            "model":         metadata.get("model", ""),
            "tokensIn":      metadata.get("tokensIn", 0),
            "tokensOut":     metadata.get("tokensOut", 0),
            "durationMs":    metadata.get("durationMs", 0),
            "jsonPath":      json_path,
        }

        write_header = not os.path.exists(self._path)
        os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)

        try:
            with open(self._path, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(row.keys()))
                if write_header:
                    w.writeheader()
                w.writerow(row)
        except Exception as e:
            from log import get_logger
            get_logger().error(f"[CsvWriter] Error escribiendo CSV: {e}")
