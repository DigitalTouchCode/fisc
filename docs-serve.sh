#!/bin/bash

# FiscGuy Documentation Server
# This script starts the MkDocs development server with Apple Pro fonts

echo "🚀 Starting FiscGuy Documentation Server..."
echo "📖 Documentation will be available at: http://127.0.0.1:8001"
echo "🍎 Featuring Apple Pro fonts (SF Pro Display & SF Mono)"
echo "🔄 Auto-reload is enabled - changes will be reflected automatically"
echo ""
echo "To stop the server, press Ctrl+C"
echo ""

# Activate virtual environment and serve docs
source venv/bin/activate && mkdocs serve --dev-addr=127.0.0.1:8001
