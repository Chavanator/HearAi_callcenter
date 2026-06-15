# Architecture

## System Overview

Call Quality Analyzer is a modular pipeline system that processes call center audio recordings through transcription, speaker separation, quality evaluation, and sentiment analysis stages.

## Data Flow

```
┌──────────────┐    ┌───────────┐    ┌──────────────┐    ┌──────────┐    ┌───────────┐
│  Data Source │───▶│  Reader   │───▶│  Transcriber │───▶│ Analyzer │───▶│  Writer   │
│ (Folder/DB)  │    │ (Adapter) │    │  (STT)       │    │  (LLM)   │    │ (Output)  │
└──────────────┘    └───────────┘    └──────────────┘    └──────────┘    └───────────┘
                                               │               │
                                               ▼               ▼
                                        ┌──────────┐    ┌────────────┐
                                        │Separator │    │Sentimentor │
                                        │(Channels)│    │  (Emotion) │
                                        └──────────┘    └────────────┘
```

## Component Design

### Manager (Orchestrator)
The `Manager` class coordinates the entire pipeline. It selects the active data source, initializes the appropriate reader, and routes audio through the processing stages.

### Reader Adapter Pattern
Each data source implements `BaseReader`:
- `FolderReader` — Scans directory for audio files
- `MongoReader` — Queries MongoDB for pending interactions
- `SQLReader` — Queries SQL Server for pending records
- `CSVReader` — Reads audio paths from CSV
- `WebSocketReader` — Receives audio paths via WebSocket

### AI Provider Factory
- `BaseProvider` — Abstract interface
- `ClaudeProvider` — Anthropic Claude API
- `GeminiProvider` — Google Gemini API

### Processing Pipeline
1. **Transcription** — Converts audio to text (Google STT or ElevenLabs)
2. **Separation** — Identifies speaker turns (agent/customer)
3. **Analysis** — Evaluates 10 quality criteria via LLM
4. **Sentiment** — Analyzes emotional tone via LLM

### Writer Adapter Pattern
Results are persisted through `BaseWriter` implementations:
- `JsonWriter`, `CsvWriter`, `MongoWriter`, `SqlWriter`, `WebSocketWriter`

## SQL Polling Engine

The `ImprovedSQLPoller` polls SQL Server for pending records with:
- Configurable poll intervals per stage (transcription/analysis/sentiment)
- Orphan record recovery (records stuck in "Processing" state)
- Timeout management (configurable per audio)
- Automatic retry with exponential backoff
- Watchdog health monitoring

## Error Recovery

- `RecoverySystem` — Retry logic with circuit breaker
- `Watchdog` — Component health monitoring and auto-restart
- `TimeoutManager` — Per-audio processing timeouts
- `SignalHandler` — Graceful shutdown on SIGINT/SIGTERM

## Deployment

The application can be:
- Run as a Python script (`python src/main.py`)
- Compiled to a Windows executable via PyInstaller
- Deployed as a Windows service
