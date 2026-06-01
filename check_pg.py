import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.db.connection import get_db_connection, init_pool, close_pool

async def main():
    await init_pool()
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute('SELECT * FROM pg_stat_statements LIMIT 1')
            res = [desc.name for desc in cur.description]
            print(res)
            
            await cur.execute('SELECT * FROM pg_stat_activity LIMIT 1')
            res2 = [desc.name for desc in cur.description]
            print(res2)
    await close_pool()

asyncio.run(main())
