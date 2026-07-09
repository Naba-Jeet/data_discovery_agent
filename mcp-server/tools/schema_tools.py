import json
from db.connection import get_pool

async def get_schema_metadata(schema_name: str) -> str:
    """
    Fetches all tables, columns, types, and constraints
    for a given schema from the remote PostgreSQL.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Get tables
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = $1
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """, schema_name)

        if not tables:
            return json.dumps({"error": f"No tables found in schema: {schema_name}"})

        schema_info = {}

        for table in tables:
            table_name = table["table_name"]

            # Get columns
            columns = await conn.fetch("""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = $1
                AND table_name = $2
                ORDER BY ordinal_position;
            """, schema_name, table_name)

            # Get row count
            count = await conn.fetchval(
                f'SELECT COUNT(*) FROM "{schema_name}"."{table_name}"'
            )

            schema_info[table_name] = {
                "row_count": count,
                "columns": [
                    {
                        "name": col["column_name"],
                        "type": col["data_type"],
                        "nullable": col["is_nullable"] == "YES",
                        "default": col["column_default"]
                    }
                    for col in columns
                ]
            }

        print(json.dumps(schema_info, indent=2))
        return json.dumps(schema_info, indent=2)