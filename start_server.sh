#!/bin/bash
# AI Tax Preparer - Server Startup Script

echo "Starting AI Tax Preparer server..."

# Set Python path
export PYTHONPATH=/home/runner/work/AI-Tax-Preparer/AI-Tax-Preparer

# Check if dependencies are installed
if ! python -c "import flask" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -r requirements.txt -q
fi

# Kill any existing Flask processes on port 5000
if lsof -i :5000 >/dev/null 2>&1; then
    echo "Stopping existing server on port 5000..."
    pkill -f "python app/main.py" || true
    sleep 1
fi

# Start the Flask server
echo "Starting Flask server..."
PYTHONPATH=. nohup python app/main.py > /tmp/flask_server.log 2>&1 &
SERVER_PID=$!

# Wait for server to start
sleep 3

# Check if server is running
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo "✓ Server is running successfully!"
    echo "  URL: http://localhost:5000"
    echo "  PID: $SERVER_PID"
    echo "  Log: /tmp/flask_server.log"
    echo ""
    echo "To stop the server, run: pkill -f 'python app/main.py'"
else
    echo "✗ Server failed to start. Check the log: /tmp/flask_server.log"
    exit 1
fi
