import json
from datetime import datetime


class MongoWriter:
    def __init__(self, cfg: dict):
        self._host     = cfg.get("host", "localhost")
        self._port     = cfg.get("port", 27017)
        self._database = cfg.get("database", "")

    def write(self, result: dict, process: str) -> None:
        if not self._database:
            return

        from pymongo import MongoClient

        source_name = str(result.get("metadata", {}).get("id", ""))
        if not source_name or source_name == "None":
            return
        if not source_name.endswith(".wav"):
            source_name = source_name + ".wav"

        update_fragment = _build_update(result, process)
        if not update_fragment:
            return

        client = MongoClient(self._host, self._port, serverSelectionTimeoutMS=5000)
        try:
            collection = client[self._database]["interactionRecords"]
            result_op = collection.update_one(
                {"call.sourceName": source_name},
                {"$set": update_fragment},
            )
            if result_op.matched_count == 0:
                collection.update_one(
                    {"call.sourceName": source_name},
                    {"$setOnInsert": {"call": {"sourceName": source_name},
                                     "createdAt": datetime.utcnow()},
                     "$set": update_fragment},
                    upsert=True,
                )
        finally:
            client.close()


def _build_update(result: dict, process: str) -> dict:
    handlers = {
        "separacion":  _map_transcription,
        "analisis":    _map_quality,
        "sentimiento": _map_sentiment,
    }
    handler = handlers.get(process)
    if not handler:
        return {}
    return handler(result)


def _map_transcription(result: dict) -> dict:
    meta = result.get("metadata", {})
    inp  = result.get("input",    {})
    out  = result.get("output",   [])

    # Obtener ID de la transcripción
    transcription_id = meta.get("transcriptionId", "") or str(datetime.utcnow().timestamp())

    output_text = inp.get("content", "")
    
    chat_format = []
    if isinstance(out, list):
        for fragment in out:
            type_val = fragment.get("type", "").lower()
            if "agente" in type_val:
                type_val = "agent"
            elif "cliente" in type_val:
                type_val = "client"
            
            chat_format.append({
                "from": fragment.get("from", "00:00"),
                "to": fragment.get("to", "00:00"),
                "type": type_val,
                "message": fragment.get("message", "")
            })

    return {
        "transcription": {
            "id": transcription_id,  # CAMBIO: genera ID si no existe
            "createdAt": datetime.utcnow(),
            "startedAt": datetime.utcnow(),
            "endedAt": datetime.utcnow(),
            "output": output_text,
            "chatFormat": chat_format
        }
    }

def _map_quality(result: dict) -> dict:
    meta = result.get("metadata", {})
    out  = result.get("output",   {})

    tokens_in = meta.get("tokensIn", 0)
    tokens_out = meta.get("tokensOut", 0)
    total_tokens = tokens_in + tokens_out
    credits_used = total_tokens * 0.0001

    # Extraer criterios y construir output array
    criteria_raw = out.get("criterios", {})
    output_array = []
    
    for key, val in criteria_raw.items():
        scorecard_name = _format_scorecard(key)
        score_val = val.get("puntuacion", 0)
        score_str = f"{int(score_val)}%"
        
        output_array.append({
            "section": val.get("detalle", ""),  # CAMBIO: usar detalle del criterio, no recomendacion general
            "scoreCard": scorecard_name,
            "score": score_str,
            "analyticResult": val.get("comentario", ""),
            "overridenScore": None,
            "overridenAnalyticResult": None
        })

    return {
        "quality": {
            "id": meta.get("qualityId", ""),
            "createdAt": datetime.utcnow(),
            "startedAt": datetime.utcnow(),
            "endedAt": datetime.utcnow(),
            "aiProvider": {
                "promptId": meta.get("promptId", ""),
                "provider": meta.get("aiProvider", ""),
                "model": meta.get("model", ""),
                "tokensIn": tokens_in,
                "tokensOut": tokens_out,
                "tokens": total_tokens,
                "creditsUsed": credits_used
            },
            "reviewed": False,
            "reviewedDate": None,
            "reviewerId": None,
            "reviewerScore": None,
            "overallScore": out.get("puntuacion_final", 0),
            "output": output_array,
            "notes": []
        }
    }


def _map_sentiment(result: dict) -> dict:
    meta     = result.get("metadata", {})
    out_data = result.get("output", {})
    
    analyses = out_data.get("analisis_llamadas", [])
    first = analyses[0] if analyses else {}

    general = first.get("sentimiento_general", {})

    tokens_in = meta.get("tokensIn", 0)
    tokens_out = meta.get("tokensOut", 0)
    total_tokens = tokens_in + tokens_out
    credits_used = total_tokens * 0.0001

    # Clasificación general
    overall = general.get("clasificacion", "neutral").lower()

    return {
        "sentiment": {
            "overall": overall,
            "summary":{
                "agent": overall,  # CAMBIO: igual al overall
                "client": overall,  # CAMBIO: igual al overall
            },
            "aiProvider": {
                "promptId": meta.get("promptId", "default"),  # CAMBIO: asignar "default" si está vacío
                "provider": meta.get("aiProvider", ""),
                "model": meta.get("model", ""),
                "tokensIn": tokens_in,
                "tokensOut": tokens_out,
                "tokens": total_tokens,
                "creditsUsed": credits_used
            }
        }
    }
def _format_scorecard(key: str) -> str:
    """Convierte snake_case a Title Case. Ej: saludo_presentacion → Saludo Presentacion"""
    words = key.split("_")
    formatted = " ".join(word.capitalize() for word in words)
    return formatted
def _build_update(result: dict, process: str) -> dict:
    handlers = {
        "separacion":  _map_transcription,
        "analisis":    _map_quality,
        "sentimiento": _map_sentiment,
    }
    handler = handlers.get(process)
    if not handler:
        return {}
    
    update = handler(result)
    
    # Eliminar chatFormat si ya existe en transcription (evitar duplicados)
    if process == "sentimiento" and "transcription" in update:
        update["transcription"].pop("chatFormat", None)
    
    return update