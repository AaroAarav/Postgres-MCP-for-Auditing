import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.db.connection import init_pool, close_pool
from src.tools.schema import get_database_schema
from src.tools.workflows import execute_dynamic_query, save_query

async def main():
    await init_pool()
    
    print("--- 1. Testing Schema Exploration ---")
    schema = await get_database_schema()
    print(schema[:500] + ("..." if len(schema) > 500 else ""))
    
    print("\\n--- 2. Testing Dynamic Query ---")
    # This should work
    res1 = await execute_dynamic_query("SELECT id, name FROM test_parent LIMIT 2")
    print("Valid Query:", res1)
    
    # This should fail due to safety checks
    res2 = await execute_dynamic_query("DELETE FROM test_parent WHERE id = 1")
    print("Dangerous Query:", res2)
    
    print("\\n--- 3. Testing Save Query ---")
    res3 = await save_query(
        name="test_get_parents", 
        sql="SELECT id, name FROM test_parent LIMIT 5",
        description="Just a test query to get parents."
    )
    print("Save Query:", res3)
    
    await close_pool()

asyncio.run(main())
