import time
import logging
from psycopg import sql
from src.db.connection import get_db_connection
from src.db.audit import log_audit_event

logger = logging.getLogger(__name__)

async def vacuum_table(table_name: str, full: bool = False, confirm: bool = False) -> str:
    """
    Runs VACUUM on a specific table to reclaim storage occupied by dead tuples.
    WARNING: full=True will lock the table exclusively. Use with caution.
    Requires confirm=True to execute.
    """
    mode = "VACUUM FULL" if full else "VACUUM"
    
    if not confirm:
        return (
            f"⚠️ DRY RUN: You are about to execute `{mode} {table_name};`.\n"
            f"This will reclaim dead tuples. "
            f"{'It WILL LOCK the table exclusively.' if full else 'It will not lock out concurrent reads/writes.'}\n"
            f"To proceed, call this tool again with confirm=True."
        )

    start_time = time.time()
    try:
        async with get_db_connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                query = sql.SQL(f"{mode} {{table}}").format(table=sql.Identifier(table_name))
                await cur.execute(query)
                
                duration = (time.time() - start_time) * 1000
                await log_audit_event(
                    tool_name="vacuum_table",
                    parameters={"table_name": table_name, "full": full},
                    status="SUCCESS",
                    duration_ms=duration
                )
                return f"✅ Successfully executed `{mode}` on '{table_name}' in {duration:.2f}ms."
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        error_msg = str(e)
        await log_audit_event(
            tool_name="vacuum_table",
            parameters={"table_name": table_name, "full": full},
            status="FAILED",
            duration_ms=duration,
            error_message=error_msg
        )
        logger.error(f"Error during VACUUM: {error_msg}")
        return f"❌ Database error: {error_msg}"


async def analyze_table(table_name: str, confirm: bool = False) -> str:
    """
    Runs ANALYZE on a specific table to update statistics used by the query planner.
    Requires confirm=True to execute.
    """
    if not confirm:
        return (
            f"⚠️ DRY RUN: You are about to execute `ANALYZE {table_name};`.\n"
            f"This updates table statistics to help the query planner. It is safe and fast.\n"
            f"To proceed, call this tool again with confirm=True."
        )

    start_time = time.time()
    try:
        async with get_db_connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                query = sql.SQL("ANALYZE {table}").format(table=sql.Identifier(table_name))
                await cur.execute(query)
                
                duration = (time.time() - start_time) * 1000
                await log_audit_event("analyze_table", {"table_name": table_name}, "SUCCESS", duration)
                return f"✅ Successfully executed ANALYZE on '{table_name}' in {duration:.2f}ms."
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        await log_audit_event("analyze_table", {"table_name": table_name}, "FAILED", duration, str(e))
        return f"❌ Database error: {str(e)}"


async def reindex_index(index_name: str, concurrently: bool = True, confirm: bool = False) -> str:
    """
    Rebuilds a specific index. 
    Use concurrently=True (default) to rebuild without locking out concurrent writes.
    Requires confirm=True to execute.
    """
    mode = "REINDEX INDEX CONCURRENTLY" if concurrently else "REINDEX INDEX"
    
    if not confirm:
        return (
            f"⚠️ DRY RUN: You are about to execute `{mode} {index_name};`.\n"
            f"This will completely rebuild the index from scratch.\n"
            f"To proceed, call this tool again with confirm=True."
        )

    start_time = time.time()
    try:
        async with get_db_connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                query = sql.SQL(f"{mode} {{idx}}").format(idx=sql.Identifier(index_name))
                await cur.execute(query)
                
                duration = (time.time() - start_time) * 1000
                await log_audit_event(
                    "reindex_index", 
                    {"index_name": index_name, "concurrently": concurrently}, 
                    "SUCCESS", 
                    duration
                )
                return f"✅ Successfully executed `{mode}` on '{index_name}' in {duration:.2f}ms."
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        await log_audit_event(
            "reindex_index", 
            {"index_name": index_name, "concurrently": concurrently}, 
            "FAILED", 
            duration, 
            str(e)
        )
        return f"❌ Database error: {str(e)}"