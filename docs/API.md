# API Reference

## Socket Server Protocol

The socket server listens on TCP port 5050 (configurable). Clients send JSON messages and receive JSON responses.

### Request Format
```json
{
  "transaction_id": 12345,
  "audio_path": "C:/audio/call_001.wav"
}
```

### Response Format
```json
{
  "status": "ok",
  "transaction_id": 12345
}
```

### Error Response
```json
{
  "status": "error",
  "mensaje": "Archivo no encontrado"
}
```

## LLM Evaluation Schema

The Analyzer module returns JSON with this structure:

```json
{
  "id_llamada": "12345",
  "fecha": "2026-06-15T19:30:00",
  "criterios": {
    "saludo_presentacion": { "comentario": "...", "puntuacion": 8 },
    "verificacion_cliente": { "comentario": "...", "puntuacion": 7 },
    "escucha_activa": { "comentario": "...", "puntuacion": 9 },
    "identificacion_necesidad": { "comentario": "...", "puntuacion": 8 },
    "conocimiento_producto": { "comentario": "...", "puntuacion": 6 },
    "ofrecimiento_solucion": { "comentario": "...", "puntuacion": 7 },
    "manejo_objeciones": { "comentario": "...", "puntuacion": 5 },
    "empatia_tono": { "comentario": "...", "puntuacion": 8 },
    "cierre_despedida": { "comentario": "...", "puntuacion": 9 },
    "cumplimiento_protocolo": { "comentario": "...", "puntuacion": 8 }
  },
  "puntuacion_final": 7.5,
  "puntuacion_transcripcion": 8,
  "recomendacion": "Mejorar manejo de objeciones..."
}
```

## SQL Server Stored Procedures

### GetPendingTranscriptions
Returns pending records for transcription.
```sql
EXEC GetPendingTranscriptions;
```

### GetPendingAnalysis
Returns records pending analysis (already transcribed).
```sql
EXEC GetPendingAnalysis;
```

### SetTranscription
Updates a record with transcription results.
```sql
EXEC SetTranscription @TransactionId, @RutaTranscripcion, @NombreTranscripcion, @TokensIn, @TokensOut;
```

### SetAnalysis
Updates a record with analysis results and marks as Completed.
```sql
EXEC SetAnalysis @TransactionId, @RutaAnalisis, @NombreAnalisis, @TokensIn, @TokensOut;
```

## Configuration

All configuration is loaded from `config.json`. Key sections:

- `source` — Active data source selection
- `ai_provider` — LLM backend (claude/gemini)
- `stt_provider` — STT engine (google/elevenlabs)
- `sql_polling` — Polling engine configuration
- `processing_features` — Pipeline stage toggles
- `token_limits` — Monthly token budget
