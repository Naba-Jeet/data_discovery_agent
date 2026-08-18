import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DQ_DSN = (
    f"postgresql://{os.getenv('DQ_DB_USER')}:{os.getenv('DQ_DB_PASSWORD')}"
    f"@{os.getenv('DQ_DB_HOST')}:{os.getenv('DQ_DB_PORT')}/{os.getenv('DQ_DB_NAME')}"
)


async def get_dq_conn() -> asyncpg.Connection:
    return await asyncpg.connect(DQ_DSN)