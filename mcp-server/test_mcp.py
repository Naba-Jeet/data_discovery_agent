import asyncio
from mcp.client.sse import sse_client
from mcp import ClientSession

async def test():
    async with sse_client("http://localhost:8001/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List all available tools
            tools = await session.list_tools()
            print("Available tools:")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description}")

asyncio.run(test())