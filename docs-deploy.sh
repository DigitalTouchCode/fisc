#!/bin/bash

# FiscGuy Documentation Deployment Script
# Deploys documentation to GitHub Pages

echo "Deploying FiscGuy Documentation to GitHub Pages..."
echo "Using Apple Pro fonts"
echo ""

# Check if we're on the right branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "release" ]; then
    echo "   Warning: You're on branch '$CURRENT_BRANCH', not 'release'"
    echo "   Consider switching to release branch first"
    echo ""
fi

# Build the documentation
echo "📦 Building documentation..."
source venv/bin/activate && mkdocs build

if [ $? -ne 0 ]; then
    echo "Build failed! Please fix the errors above."
    exit 1
fi

# Deploy to GitHub Pages
echo "Deploying to GitHub Pages..."
source venv/bin/activate && mkdocs gh-deploy --force

if [ $? -eq 0 ]; then
    echo ""
    echo "Documentation deployed successfully!"
    echo "Live at: https://digitaltouchcode.github.io/fisc/"
    echo ""
    echo "Note: It may take a few minutes for changes to appear."
else
    echo ""
    echo "Deployment failed! Check the error messages above."
    exit 1
fi
