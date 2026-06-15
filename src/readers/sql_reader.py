import pyodbc
from reader.base_reader import BaseReader


class SqlReader(BaseReader):

    def __init__(self, connection_string: str):
        self._conn_str = connection_string

    def read(self, sp_name: str = "", tipo_proceso: str = "transcription") -> list[dict]:
        if not sp_name:
            raise ValueError(
                f"[SqlReader] spname requerido para tipoproceso='{tipo_proceso}'"
            )

        try:
            with pyodbc.connect(self._conn_str, timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute(f"EXEC {sp_name}")
                columns = [col[0] for col in cursor.description] if cursor.description else []
                rows    = cursor.fetchall()

        except pyodbc.Error as e:
            msg = str(e)
            if "No se pudo encontrar SP" in msg:
                return []   
            raise

        records = []
        for row in rows:
            row_dict       = dict(zip(columns, row))
            transaction_id = row_dict.get("TransactionId")
            audio_path     = row_dict.get("TransactionFile")
            retry_count    = row_dict.get("ReintentoCount", 0)

            if not isinstance(audio_path, str):
                continue

            record = {
                "transaction_id": int(transaction_id) if transaction_id else 0,
                "audio_path":     audio_path,
                "retry_count":    int(retry_count) if retry_count else 0,
                "source":         "sql",
            }

            if tipo_proceso == "analysis":
                tp = row_dict.get("TranscriptionPath")
                record["transcription_path"] = tp if isinstance(tp, str) else None

            raw_pid = row_dict.get("PromptId")
            raw_pid_str = str(raw_pid).strip() if raw_pid is not None else ""
            record["prompt_id"] = raw_pid_str if raw_pid_str else None

            records.append(record)

        return records