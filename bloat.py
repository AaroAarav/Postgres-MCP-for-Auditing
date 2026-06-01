import asyncio
import sys
import psycopg
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:Aarokek@localhost:5432/testdb")

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def force_bloat():
    print("Forcing table bloat...")
    try:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                # 1. Disable autovacuum on this specific table so it doesn't ruin our test
                await cur.execute("ALTER TABLE test_bloat SET (autovacuum_enabled = false);")
                
                # 2. Insert 50,000 new rows
                print("Inserting rows...")
                await cur.execute("INSERT INTO test_bloat (data) SELECT md5(random()::text) FROM generate_series(1, 50000);")
                
                # 3. Update ALL of them (creates 50,000 dead tuples)
                print("Updating rows...")
                await cur.execute("UPDATE test_bloat SET data = md5(random()::text);")
                
                # 4. Delete half of them (creates another 25,000 dead tuples)
                print("Deleting rows...")
                await cur.execute("DELETE FROM test_bloat WHERE id % 2 = 0;")
                
                # 5. Force a stats update so the pg_stat_user_tables view sees it instantly
                await cur.execute("ANALYZE test_bloat;")
                
        print("✅ Bloat successfully generated! Go test it in Claude Desktop.")
    except Exception as e:
        print(f"❌ Failed to generate bloat: {e}")

if __name__ == "__main__":
    asyncio.run(force_bloat())