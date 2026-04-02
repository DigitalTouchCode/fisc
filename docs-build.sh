#!/bin/bash

# FiscGuy Documentation Build Script
# This script builds the documentation for deployment with Apple Pro fonts

echo "🏗️  Building FiscGuy Documentation..."
echo "🍎 Using Apple Pro fonts (SF Pro Display & SF Mono)"
echo "📁 Output directory: site/"
echo ""

# Activate virtual environment and build docs
source venv/bin/activate && mkdocs build

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Documentation built successfully!"
    echo "📂 Built files are in the 'site/' directory"
    echo "🍎 Apple Pro fonts optimized for macOS"
    echo "🌐 Ready to deploy to GitHub Pages or any static hosting"
    echo ""
    echo "To deploy to GitHub Pages:"
    echo "  mkdocs gh-deploy"
else
    echo ""
    echo "❌ Build failed! Check the error messages above."
    exit 1
fi
