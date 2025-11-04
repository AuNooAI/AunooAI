#!/bin/bash
# Restart multi.aunoo.ai server to pick up route changes

echo "🔄 Restarting multi.aunoo.ai server..."

# Find and kill the current process
PID=$(ps aux | grep "/home/orochford/tenants/multi.aunoo.ai" | grep "server_run.py" | grep -v grep | awk '{print $2}')

if [ -z "$PID" ]; then
    echo "❌ Server not running, starting fresh..."
else
    echo "🛑 Stopping server (PID: $PID)..."
    kill $PID
    sleep 2

    # Check if still running
    if ps -p $PID > /dev/null; then
        echo "⚠️  Force killing..."
        kill -9 $PID
        sleep 1
    fi
fi

# Start the server
echo "🚀 Starting server..."
cd /home/orochford/tenants/multi.aunoo.ai
source .venv/bin/activate
nohup python app/server_run.py > server.log 2>&1 &

NEW_PID=$!
echo "✅ Server started with PID: $NEW_PID"
echo "📋 Check logs: tail -f /home/orochford/tenants/multi.aunoo.ai/server.log"
echo ""
echo "🌐 Access at: http://localhost:6005/trend-convergence"
