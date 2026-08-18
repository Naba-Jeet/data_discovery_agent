import os
from dotenv import load_dotenv

load_dotenv()

# OLLAMA_MODEL=qwen2.5-coder:3b
# OLLAMA_BASE_URL=http://ollama:11434
# MCP Server
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:7001")

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")

# App
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", 7000))

MEMORY_DSN = os.getenv(
    "MEMORY_DSN",
    "postgresql://admin:admin123@localhost:5433/data_discovery"
)