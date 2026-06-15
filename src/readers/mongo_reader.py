from reader.base_reader import BaseReader


class MongoReader(BaseReader):
    def __init__(self, cfg: dict):
        self._host        = cfg.get("host", "localhost")
        self._port        = cfg.get("port", 27017)
        self._database    = cfg.get("database", "")
        self._collection  = cfg.get("collection", "")
        self._audio_field = cfg.get("audio_field", "directorio")

    def read(self, **_) -> list[dict]:
        from pymongo import MongoClient

        if not self._database or not self._collection:
            raise ValueError(
                "[MongoReader] 'database' y 'collection' son requeridos en config=mongo_db"
            )

        client = MongoClient(self._host, self._port)
        try:
            docs = list(client[self._database][self._collection].find({}))
        finally:
            client.close()

        records = []
        for doc in docs:
            audio_path = doc.get(self._audio_field)
            if not isinstance(audio_path, str):
                continue
            records.append({
                "audio_path": audio_path,
                "source":     "mongo_db",
                "mongo_id":   str(doc.get("_id", "")),
            })

        return records
