import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.db.connection import init_pool, close_pool
from src.tools.workflows import execute_dynamic_query
from src.tools.history import get_recent_queries

async def main():
    await init_pool()
    
    print("--- 1. Testing execution ---")
    await execute_dynamic_query("SELECT id, name FROM test_parent LIMIT 1")
    await execute_dynamic_query("SELECT id, data FROM test_bloat LIMIT 1")
    
    print("\\n--- 2. Fetching history ---")
    history = await get_recent_queries()
    print(history)
    
    await close_pool()

asyncio.run(main())
