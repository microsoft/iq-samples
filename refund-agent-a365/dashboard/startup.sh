#!/bin/bash
set -e

# Build frontend if not already built
if [ ! -d "frontend/dist" ]; then
    echo "Building frontend..."
    cd frontend
    npm install
    npm run build
    cd ..
fi

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Start the backend (serves frontend static files too)
python -m uvicorn main:app --host 0.0.0.0 --port 8000
