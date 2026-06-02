import asyncio
from agent import run_dba_agent
import sys
import io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

async def main():
    print("==================================================")
    print("TEST 1: Generate Query (Should use Schema Context & Auto-Save)")
    print("==================================================")
    prompt = "Write a SQL query to find the names of all databases and their encoding from the pg_database table. Call it 'db_encodings'."
    await run_dba_agent(prompt)
    
    print("\n\n==================================================")
    print("TEST 2: Exact Same Request (Should use Injected Saved Query Context)")
    print("==================================================")
    await run_dba_agent(prompt)

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
