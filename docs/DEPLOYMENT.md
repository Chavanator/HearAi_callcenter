# Deployment Guide

## Windows Service (Production)

### Option 1: Python Script
```bash
# Run as background process
python src/main.py

# Or using PowerShell to run in background
Start-Process -NoNewWindow -FilePath "python" -ArgumentList "src/main.py"
```

### Option 2: Windows Executable (PyInstaller)

Build the executable:
```bash
# Using the provided build script
scripts\build_pyinstaller.bat

# Or manually
pyinstaller scripts\build.spec
```

Run the compiled executable:
```bash
dist\ai_evaluator\ai_evaluator.exe
```

### Option 3: Windows Service (NSSM)

1. Download [NSSM](https://nssm.cc/)
2. Install as service:
```bash
nssm install CallQualityAnalyzer "C:\path\to\python.exe" "C:\path\to\src\main.py"
nssm start CallQualityAnalyzer
```

## Docker (Coming Soon)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "src/main.py"]
```

## Required Directory Structure

```
call-quality-analyzer/
├── config/
│   └── config.json          # Production config (not in repo)
├── logs/                    # Auto-created
├── data/
│   ├── sample/              # Input audio (depends on source config)
│   └── results/             # Output files
└── .env                     # Environment variables
```

## Environment Variables

All sensitive configuration should use environment variables (via `.env`):
- API keys for Claude, Gemini, OpenAI, ElevenLabs
- Database connection strings
- Network configuration

## Monitoring

- **Logs**: Rotating log files in `logs/` directory
- **GUI Monitor**: `scripts/monitor_gui.py` for real-time monitoring
- **Watchdog**: Automatic component health checks and restarts
- **Token Tracking**: Monthly token usage via SQL Server views
