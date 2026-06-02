import logging
from src.services.schema_intelligence import schema_manager, query_store
from src.db.connection import get_db_connection
from psycopg.rows import dict_row
from src.tools.formatters import format_results

logger = logging.getLogger(__name__)

async def smart_query(user_prompt: str) -> str:
    """
    Intelligent query routing tool.
    Use this tool FIRST whenever the user asks a question about their data that requires a query.
    It will attempt to find a semantically similar, previously generated, and successful query 
    in the QueryTemplateStore.
    
    If a match is found (and the schema is still valid), it will execute it directly and save tokens.
    If no match is found, it will instruct you to generate the SQL yourself.
    """
    try:
        db_id = await schema_manager.get_database_id()
        _, schema_hash = await schema_manager.fetch_schema()
        
        cached_sql = query_store.search_similar_query(db_id, user_prompt, schema_hash)
        
        if cached_sql:
            logger.info(f"Smart query cache hit for prompt: '{user_prompt}'")
            
            # Execute the cached SQL
            try:
                async with get_db_connection() as conn:
                    await conn.set_read_only(True)
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute(cached_sql)
                        results = await cur.fetchall()
                        formatted = format_results(results, "No results found for cached query.")
                        
                        return f"✅ Cache Hit: Reusing a semantically similar query.\n\nExecuted SQL:\n```sql\n{cached_sql}\n```\n\nResults:\n{formatted}"
            except Exception as db_e:
                # If execution fails, cache might be stale despite schema hash matching (e.g., deleted rows causing div by zero)
                logger.error(f"Failed to execute cached SQL: {db_e}")
                return f"❌ Cache Hit but Execution Failed: {db_e}. Please generate a new SQL query using `execute_dynamic_query`."
        
        # Cache miss
        return (
            f"❌ Cache Miss: No semantically similar query found for '{user_prompt}'.\n"
            "Please use `get_database_schema` to understand the database structure, "
            "then generate a SQL query to answer the user's question, and execute it "
            "using `execute_dynamic_query(sql, user_prompt, query_name, query_description)`."
        )
        
    except Exception as e:
        logger.error(f"Smart query error: {e}")
        return f"Error executing smart query: {e}. Please fallback to manual SQL generation via `execute_dynamic_query`."
