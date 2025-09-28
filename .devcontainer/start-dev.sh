#!/bin/bash

# CRLChecker Development Startup Script
# This script helps you get started with development

echo "🚀 Starting CRLChecker Development Environment"
echo "=============================================="

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from template..."
    cp env.example .env
    echo "📝 Please edit .env file with your Telegram bot credentials"
    echo "   - TELEGRAM_BOT_TOKEN=your_bot_token"
    echo "   - TELEGRAM_CHAT_ID=your_chat_id"
    echo ""
    echo "Press Enter to continue after editing .env file..."
    read
fi

# Load environment variables
if [ -f ".env" ]; then
    echo "📋 Loading environment variables from .env"
    export $(cat .env | grep -v '^#' | xargs)
fi

# Create data directory if it doesn't exist
mkdir -p ../data/crl_cache
mkdir -p ../data/logs
mkdir -p ../data/stats

echo "📁 Data directories created"

# Initialize database if needed
if [ ! -f "../data/crlchecker.db" ]; then
    echo "🗄️  Initializing database..."
    python -c "
import sys
sys.path.insert(0, '/app')
from db import init_db
init_db()
print('Database initialized')
"
fi

echo "✅ Development environment ready!"
echo ""
echo "Available commands:"
echo "  python run_all_monitors.py  - Start the full monitoring system"
echo "  python crl_monitor.py       - Run CRL monitor only"
echo "  python tsl_monitor.py       - Run TSL monitor only"
echo "  python debug_crl.py          - Debug CRL parsing"
echo ""
echo "Metrics server will be available at: http://localhost:8000"
echo "Database file: /app/data/crlchecker.db"
echo ""
echo "Happy coding! 🎉"
