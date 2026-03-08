# Quick Start Guide

## Starting the Web Interface

The easiest way to start the AI Tax Preparer web interface is to use the provided startup script:

```bash
./start_server.sh
```

This script will:
1. Install dependencies if needed
2. Stop any existing server instances
3. Start the Flask development server
4. Verify the server is running

### Manual Start

If you prefer to start the server manually:

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
PYTHONPATH=. python app/main.py
```

The server will start on **http://localhost:5000**

### Troubleshooting

**Problem: Server won't start**
- Solution: Check if port 5000 is already in use: `lsof -i :5000`
- Solution: Install dependencies: `pip install -r requirements.txt`

**Problem: "Module not found" errors**
- Solution: Set PYTHONPATH: `export PYTHONPATH=/home/runner/work/AI-Tax-Preparer/AI-Tax-Preparer`
- Solution: Run from project root directory

**Problem: Server stops unexpectedly**
- Solution: Check the log file: `cat /tmp/flask_server.log`
- Solution: Restart using the startup script: `./start_server.sh`

**Stopping the Server**
```bash
pkill -f 'python app/main.py'
```

### Server Status

Check if the server is running:
```bash
curl http://localhost:5000/health
```

Expected response:
```json
{
    "service": "AI-Tax-Preparer",
    "status": "ok"
}
```

## Accessing the Web Interface

Once the server is running, open your browser and navigate to:
- **http://localhost:5000** - Main web interface
- **http://localhost:5000/health** - Health check endpoint

The web interface provides:
- 4-step tax form wizard
- Real-time tax calculations
- Compliance review with audit risk scoring
- AI-powered tax assistant (requires OpenAI API key)
- Support for 2024 and 2026 (with OBBBA) tax years
