import asyncio
import json
from mcp.client.sse import sse_client
from mcp import ClientSession

async def test():
    async with sse_client("http://localhost:8001/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            question = "Show top 5 customers by total order amount. Use only select to write queries. use customers and salesorderheader table only join on customerid"

            # Step 1: NL → SQL
            print("Step 1: Generating SQL...")
            nl_result = await session.call_tool(
                "tool_nl_to_sql",
                {"schema_name": "sales", "question": question}
            )
            nl_data = json.loads(nl_result.content[0].text)
            generated_sql = nl_data["generated_sql"].replace(";", "") 
            print("Generated SQL:\n", generated_sql)

            # Step 2: Execute SQL
            print("\nStep 2: Executing SQL...")
            exec_result = await session.call_tool(
                "tool_query_remote_postgres",
                {"sql": generated_sql, "limit": 5}
            )
            for c in exec_result.content:
                if hasattr(c, "text"):
                    try:
                        rows = json.loads(c.text)
                        print("Results:")
                        print(json.dumps(rows, indent=2))
                    except json.JSONDecodeError:
                        print("Raw output:", c.text)

asyncio.run(test())