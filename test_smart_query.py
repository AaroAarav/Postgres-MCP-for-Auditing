import asyncio
import os
from src.services.schema_intelligence import query_store, schema_manager
from src.tools.smart_query import smart_query

async def test():
    print("Testing QueryTemplateStore init...")
    assert os.path.exists("query_memory.db"), "DB file should be created"
    
    print("All basic module imports worked!")

if __name__ == "__main__":
    asyncio.run(test())
