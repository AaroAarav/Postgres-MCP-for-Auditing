import asyncio
import sys
import psycopg
import os
from dotenv import load_dotenv

# Load database URL from your .env file
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:Aarokek@localhost:5432/testdb")

# Windows async fix
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def seed():
    print(f"Connecting to database: {DATABASE_URL.split('@')[-1]}...")
    
    try:
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                
                print("1. Setting up pg_stat_statements...")
                try:
                    await cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
                except Exception as e:
                    print(f"  [!] Note: pg_stat_statements extension failed: {e}")
                    print("  (You may need to add it to shared_preload_libraries in postgresql.conf. The script will continue anyway.)")

                print("2. Creating test_bloat table...")
                await cur.execute("DROP TABLE IF EXISTS test_bloat;")
                await cur.execute("CREATE TABLE test_bloat (id serial PRIMARY KEY, data text);")

                print("3. Inserting 100,000 rows (this takes a few seconds)...")
                await cur.execute("""
                    INSERT INTO test_bloat (data) 
                    SELECT md5(random()::text) FROM generate_series(1, 100000);
                """)

                print("4. Creating table bloat (updating 50% and deleting 20% of rows)...")
                # Updates and deletes leave "dead tuples" behind until a VACUUM runs
                await cur.execute("UPDATE test_bloat SET data = md5(random()::text) WHERE id % 2 = 0;")
                await cur.execute("DELETE FROM test_bloat WHERE id % 5 = 0;")

                print("5. Generating slow queries...")
                # We use pg_sleep to artificially make these queries take >0.5 seconds
                await cur.execute("SELECT pg_sleep(0.8), count(*) FROM test_bloat;")
                await cur.execute("SELECT pg_sleep(0.6), data FROM test_bloat LIMIT 10;")
                await cur.execute("SELECT pg_sleep(0.5), id FROM test_bloat WHERE id = -1;")

                print("6. Generating cache hits...")
                for _ in range(10):
                    await cur.execute("SELECT count(*) FROM test_bloat WHERE id < 50000;")

        print("\n✅ Database seeded successfully! You are ready to test.")
        
    except Exception as e:
        print(f"\n❌ Seeding failed: {e}")

if __name__ == "__main__":
    asyncio.run(seed())