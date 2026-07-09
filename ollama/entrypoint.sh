#!/bin/bash

# Start Ollama server in background
ollama serve &
OLLAMA_PID=$!

# Wait for server to be ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 1
done
echo "Ollama is up."

# Pull model from env var (default: qwen2.5:3b)
MODEL=${OLLAMA_MODEL:-qwen2.5:3b}
echo "Pulling model: $MODEL"
ollama pull $MODEL
echo "Model $MODEL ready."

# Keep server running
wait $OLLAMA_PID