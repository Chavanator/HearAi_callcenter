# Setup Guide

## Prerequisites

### Required
- **Python 3.9+**
- **FFmpeg** — [Download](https://ffmpeg.org/download.html) and add to PATH

### Optional
- **ODBC Driver 17 for SQL Server** — [Download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- **MongoDB** — Local or remote instance
- **ElevenLabs Account** — For premium STT

## Installation

### 1. Clone and enter the repository
```bash
git clone <repo-url>
cd call-quality-analyzer
```

### 2. Create virtual environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env with your API keys and credentials
```

### 5. Set up config
```bash
cp config/config.example.json config/config.json
# Edit config.json for your data sources
```

## Database Setup

### SQL Server
```bash
sqlcmd -S localhost -U sa -P your_password -i database/sql_setup.sql
```

This creates:
- `AudioQueue` table with tracking fields
- Stored procedures for queue management
- Indexes for performance
- Token usage views

## Running

### Production (SQL Polling)
```bash
python src/main.py
```

### Socket Server Mode
```bash
python src/socket_server/audio_analyzer_server.py
```

### Standalone Evaluation
```bash
python scripts/evaluator_standalone.py
```

### GUI Monitor
```bash
python scripts/monitor_gui.py
```

## Configuration Reference

Key settings in `config.json`:

| Setting | Description |
|---|---|
| `source` | Active data source (folder/mongo/sql/csv/websocket) |
| `ai_provider` | LLM provider: `claude` or `gemini` |
| `stt_provider` | STT engine: `google` or `elevenlabs` |
| `sql_polling.enabled` | Enable/disable SQL polling mode |
| `token_limits.monthly_limit` | Max tokens per month |
| `processing_features` | Enable/disable pipeline stages |
