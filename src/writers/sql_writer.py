import pyodbc
from typing import Optional


analyzer_version="V:1.2.3.2026"

def _ejecutar_sp(conn_str: str, nombre_sp: str, parametros: list) -> bool:
    try:
        with pyodbc.connect(conn_str, timeout=10) as conn:
            cursor = conn.cursor()
            placeholders = ", ".join(["?"] * len(parametros))
            cursor.execute(f"EXEC {nombre_sp} {placeholders}", *parametros)
            conn.commit()
            return True
    except pyodbc.Error as e:
        msg = str(e)
        if "Could not find stored procedure" in msg:
            return False   # SP no existe 
        from log import get_logger
        get_logger().error(f"[sql_writer] Error en {nombre_sp}: {msg}")
        return False
    except Exception as e:
        from log import get_logger
        get_logger().error(f"[sql_writer] Error inesperado en {nombre_sp}: {e}")
        return False


def _ejecutar_query(conn_str: str, query: str, parametros: Optional[list] = None) -> list:
    try:
        with pyodbc.connect(conn_str, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute(query, parametros or [])
            return cursor.fetchall()
    except Exception as e:
        from log import get_logger
        get_logger().error(f"[sql_writer] Error en query: {e}")
        return []


class SqlWriter:

    def __init__(self, connection_string: str):
        self._cs = connection_string

    def guardar_transcripcion(self, transaction_id, path, name, tokens_in, tokens_out) -> bool:
        return _ejecutar_sp(self._cs, "SetTranscription",
                            [transaction_id, path, name, tokens_in, tokens_out])

    def guardar_separacion(self, transaction_id, path, name, tokens_in, tokens_out) -> bool:
        return _ejecutar_sp(self._cs, "SetSeparation",
                            [transaction_id, path, name, tokens_in, tokens_out])

    def guardar_analisis(self, transaction_id, path, name, tokens_in, tokens_out, model="") -> bool:
        return _ejecutar_sp(self._cs, "SetAnalysis",
                            [transaction_id, path, name, tokens_in, tokens_out])

    def guardar_sentimiento(self, transaction_id, path, name, tokens_in, tokens_out) -> bool:
        return _ejecutar_sp(self._cs, "SetFeeling",
                            [transaction_id, path, name, tokens_in, tokens_out])

    def actualizar_estado(self, transaction_id, estado, retry_count=None) -> bool:
        return _ejecutar_sp(self._cs, "UpdateTransactionStatus",
                            [transaction_id, estado, retry_count])

    def marcar_como_error(self, transaction_id, mensaje="Máximo de reintentos alcanzado") -> None:
        self.actualizar_estado(transaction_id, "Error")
        from log import get_logger
        get_logger().error(f"[sql_writer] TransactionId {transaction_id} → ERROR: {mensaje}")

    def set_analysis_error(self, transaction_id, mensaje: str = "Error en análisis") -> bool:
        """
        Marca el registro en AudioAnalyzer con onError=1 y errorType=mensaje.
        GetPendingAnalisys filtra onError=0, por lo que este registro
        queda descartado y no bloquea el queue.
        """
        ok = _ejecutar_sp(self._cs, "SetAnalysisError", [transaction_id, mensaje])
        from log import get_logger
        log = get_logger()
        if ok:
            log.error(
                f"[sql_writer] TransactionId {transaction_id} → "
                f"SetAnalysisError: {mensaje}"
            )
        else:
            log.error(
                f"[sql_writer] TransactionId {transaction_id} → "
                f"SetAnalysisError falló (SP no encontrado o error de BD)"
            )
        return ok

    def obtener_prompt_config(self, prompt_id: int) -> Optional[dict]:
        """
        SELECT * FROM PromptConfiguration WHERE Id = prompt_id
        Retorna dict con al menos 'Path' y 'FileName', o None si no existe.
        """
        try:
            with pyodbc.connect(self._cs, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM PromptConfiguration WHERE Id = ?", [prompt_id]
                )
                columns = [col[0] for col in cursor.description] if cursor.description else []
                row     = cursor.fetchone()
                if not row:
                    return None
                return dict(zip(columns, row))
        except Exception as e:
            from log import get_logger
            get_logger().error(
                f"[sql_writer] Error obteniendo PromptConfiguration id={prompt_id}: {e}"
            )
            return None

    def obtener_tokens_mes(self, mes: str) -> dict:
        _zero = {k: 0 for k in
                 ("transcription_in","transcription_out","analysis_in",
                  "analysis_out","sentiment_in","sentiment_out","total")}
        try:
            rows = _ejecutar_query(self._cs, "EXEC GetTokensUsedByMonth ?", [mes])
            if not rows:
                return _zero
            r = rows[0]
            t_in, t_out = r[0] or 0, r[1] or 0
            a_in, a_out = r[2] or 0, r[3] or 0
            f_in  = r[4] or 0 if len(r) > 4 else 0
            f_out = r[5] or 0 if len(r) > 5 else 0
            total = t_in + t_out + a_in + a_out + f_in + f_out
            return dict(transcription_in=t_in, transcription_out=t_out,
                        analysis_in=a_in, analysis_out=a_out,
                        sentiment_in=f_in, sentiment_out=f_out, total=total)
        except Exception:
            return _zero