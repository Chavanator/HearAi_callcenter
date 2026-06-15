# Call Quality Analyzer

AI-powered call center quality evaluation system. Transcribes audio calls, evaluates agent performance across 10 quality criteria using LLMs (Claude/Gemini), performs sentiment analysis, and stores results in SQL Server / MongoDB / JSON.

## Features

- **Multi-source ingestion** — Reads audio from folders, MongoDB, SQL Server, CSV files, or WebSockets
- **Speech-to-Text** — Google Speech Recognition (free) or ElevenLabs Scribe (high accuracy)
- **Speaker Separation** — Identifies and separates agent vs. customer channels
- **Quality Evaluation** — LLM-powered analysis across 10 criteria (greeting, verification, active listening, empathy, closing, etc.)
- **Sentiment Analysis** — Emotional tone analysis of the call
- **SQL Polling** — Automatic processing with orphan record recovery and watchdog
- **Multi-output** — Results to SQL Server, MongoDB, JSON, CSV, or WebSocket
- **Token Management** — Monthly token limits with warnings and alerts

## Architecture

```
src/
├── main.py                    # Entry point (production orchestrator)
├── manager.py                 # Pipeline orchestrator
├── transcriber.py             # Speech-to-Text (Google / ElevenLabs)
├── separator.py               # Channel separation
├── analyzer.py                # Quality evaluation (10 criteria)
├── sentimentor.py             # Sentiment analysis
├── optimizer.py               # Token usage optimization
├── recovery_system.py         # Watchdog, timeouts, auto-recovery
├── connection_settings.py     # Configuration loader
├── log.py                     # Logging system
├── providers/                 # AI provider factory (Claude, Gemini)
├── readers/                   # Data source readers
├── writers/                   # Data output writers
├── socket_server/             # TCP socket server
└── sql_poller/                # SQL polling with recovery
```

## Quick Start

### Prerequisites

- Python 3.9+
- FFmpeg (for audio processing)
- ODBC Driver 17 for SQL Server (optional)
- MongoDB (optional)

### Installation

```bash
git clone https://github.com/your-org/call-quality-analyzer.git
cd call-quality-analyzer

python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

pip install -r requirements.txt
```

### Configuration

1. Copy the environment template:
   ```bash
   cp config/config.example.json config/config.json
   cp .env.example .env
   ```

2. Edit `.env` with your API keys and database credentials:
   ```env
   CLAUDE_API_KEY=your_claude_api_key
   GEMINI_API_KEY=your_gemini_api_key
   SQL_SERVER=localhost
   SQL_DATABASE=your_database
   SQL_USER=your_user
   SQL_PASSWORD=your_password
   ```

### Run

```bash
# Production mode (SQL Polling)
python src/main.py

# Socket server mode
python src/socket_server/audio_analyzer_server.py

# Standalone evaluation
python scripts/evaluator_standalone.py
```

### Database Setup

```bash
# Execute SQL scripts against your SQL Server
sqlcmd -S localhost -U sa -P your_password -i database/sql_setup.sql
```

## Project Structure

```
call-quality-analyzer/
├── src/                    # Production source code
│   ├── providers/          # AI provider implementations
│   ├── readers/            # Data source readers
│   ├── writers/            # Data output writers
│   ├── socket_server/      # TCP socket server
│   └── sql_poller/         # SQL polling engine
├── scripts/                # Standalone utilities & build scripts
├── notebooks/              # Jupyter prototypes
├── database/               # SQL schemas & migrations
├── prompts/                # LLM prompt templates
├── dictionary/             # Custom vocabulary / keyterms
├── config/                 # Configuration templates
├── data/                   # Sample data & outputs
├── docs/                   # Documentation
└── tests/                  # Test suite
```

## Tech Stack

- **Python** 3.9+ — Core runtime
- **Google Speech Recognition** — Free STT
- **ElevenLabs Scribe** — Premium STT
- **Claude (Anthropic)** — LLM evaluation
- **Gemini (Google)** — LLM evaluation (alternative)
- **SQL Server** — Primary data store
- **MongoDB** — Document store
- **PyODBC** — SQL Server connectivity
- **PyMongo** — MongoDB connectivity



1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
