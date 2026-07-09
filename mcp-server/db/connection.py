import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.getenv("CLIENT_PG_HOST", "localhost"),
            port=int(os.getenv("CLIENT_PG_PORT", 5432)),
            user=os.getenv("CLIENT_PG_USER", "postgres"),
            password=os.getenv("CLIENT_PG_PASSWORD", "postgres"),
            database=os.getenv("CLIENT_PG_DB", "Adventureworks"),
            min_size=2,
            max_size=10
        )
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None