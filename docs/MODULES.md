# Module Reference

## Core (`src/`)

| Module | File | Description |
|---|---|---|
| **Manager** | `manager.py` | Pipeline orchestrator — coordinates readers, processors, and writers |
| **Transcriber** | `transcriber.py` | Speech-to-Text engine (Google STT or ElevenLabs Scribe) |
| **Separator** | `separator.py` | Speaker diarization — separates agent and customer channels |
| **Analyzer** | `analyzer.py` | Quality evaluation — scores 10 criteria via LLM |
| **Sentimentor** | `sentimentor.py` | Emotional tone analysis via LLM |
| **Optimizer** | `optimizer.py` | Token usage tracking and monthly limit enforcement |
| **RecoverySystem** | `recovery_system.py` | Watchdog, timeouts, auto-restart, circuit breaker |
| **ConnectionSettings** | `connection_settings.py` | Configuration loader and validation |
| **Log** | `log.py` | Rotating file + console logger |
| **ElevenLabsTranscriber** | `elevenlabs_transcriber.py` | ElevenLabs Scribe STT integration |

## Providers (`src/providers/`)

| Module | Description |
|---|---|
| `base_provider.py` | Abstract base class for AI providers |
| `claude_provider.py` | Anthropic Claude API integration |
| `gemini_provider.py` | Google Gemini API integration |

## Readers (`src/readers/`)

| Module | Data Source | Description |
|---|---|---|
| `folder_reader.py` | Local folder | Scans a directory for audio files |
| `mongo_reader.py` | MongoDB | Queries MongoDB for pending interactions |
| `sql_reader.py` | SQL Server | Queries via stored procedure |
| `csv_reader.py` | CSV file | Reads audio file paths from CSV |
| `websocket_reader.py` | WebSocket | Receives audio paths via WebSocket |

## Writers (`src/writers/`)

| Module | Output | Description |
|---|---|---|
| `json_writer.py` | JSON files | Writes results to local JSON |
| `csv_writer.py` | CSV files | Writes results to CSV |
| `mongo_writer.py` | MongoDB | Inserts results into MongoDB |
| `sql_writer.py` | SQL Server | Updates via stored procedure |
| `websocket_writer.py` | WebSocket | Sends results via WebSocket |

## Socket Server (`src/socket_server/`)

| File | Description |
|---|---|
| `audio_analyzer_server.py` | TCP socket server — receives audio paths, transcribes + evaluates |
| `socket_connection.py` | Improved socket handler with JSON messaging |

## SQL Poller (`src/sql_poller/`)

| File | Description |
|---|---|
| `sql_poller.py` | SQL polling engine with orphan recovery and retry logic |
| `monitor.py` | Server health monitor |

## Scripts (`scripts/`)

| File | Description |
|---|---|
| `evaluator_standalone.py` | Standalone audio transcription + evaluation script |
| `monitor_gui.py` | Tkinter GUI for disk monitoring and log viewer |
| `build_pyinstaller.bat` | Batch script to compile to Windows executable |
