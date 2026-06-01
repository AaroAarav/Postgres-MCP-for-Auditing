import logging
import psycopg
from psycopg.rows import dict_row
from src.db.connection import get_db_connection
from src.tools.formatters import format_results
import time
import json
from src.db.audit import log_audit_event

logger = logging.getLogger(__name__)

async def ping_database() -> str:
    """Pings the PostgreSQL database to verify connectivity."""
    try:
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT version();")
                version = await cur.fetchone()
                if version:
                    return f"Connection successful! Database version: {version[0]}"
                return "Connection successful, but no version data returned."
    except Exception as e:
        logger.error(f"Ping failed: {e}")
        return f"Database connection failed: {e}"

async def slow_queries(limit: int = 10) -> str:
    """Returns the slowest queries from pg_stat_statements. Use this to identify performance bottlenecks."""
    query = """
        SELECT substring(query, 1, 100) AS query_preview, calls, 
               round(total_exec_time::numeric, 2) AS total_time_ms,
               round(mean_exec_time::numeric, 2) AS mean_time_ms, rows
        FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No slow queries found. (Ensure pg_stat_statements is enabled)")
    except Exception as e:
        return f"Database error: {e}"

async def active_sessions() -> str:
    """Returns current active database sessions and their running queries."""
    query = """
        SELECT pid, usename, application_name, state,
               substring(query, 1, 60) as query_preview,
               extract(epoch from (now() - query_start))::int as duration_sec
        FROM pg_stat_activity
        WHERE state != 'idle' AND pid != pg_backend_pid();
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                results = await cur.fetchall()
                return format_results(results, "No active sessions running queries at the moment.")
    except Exception as e:
        return f"Database error: {e}"

async def cache_hit_rate() -> str:
    """Returns the PostgreSQL buffer cache hit rate. Values below 95% may indicate memory starvation."""
    query = """
        SELECT sum(heap_blks_read) as heap_read, sum(heap_blks_hit) as heap_hit,
               CASE WHEN sum(heap_blks_hit) + sum(heap_blks_read) > 0
                    THEN round(sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read))::numeric * 100, 2)
                    ELSE 0 END as hit_rate_pct
        FROM pg_statio_user_tables;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                results = await cur.fetchall()
                return format_results(results)
    except Exception as e:
        return f"Database error: {e}"

async def blocking_lock_tree() -> str:
    """Returns a tree of blocked and blocking PIDs. Use this to diagnose deadlocks and stuck queries."""
    query = """
        SELECT blocked_locks.pid AS blocked_pid, blocked_activity.usename AS blocked_user,
               blocking_locks.pid AS blocking_pid, blocking_activity.usename AS blocking_user,
               substring(blocked_activity.query, 1, 50) AS blocked_query,
               substring(blocking_activity.query, 1, 50) AS blocking_query
        FROM pg_catalog.pg_locks blocked_locks
        JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
        JOIN pg_catalog.pg_locks blocking_locks 
            ON blocking_locks.locktype = blocked_locks.locktype
            AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
            AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
            AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
            AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
            AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
            AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
            AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
            AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
            AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
            AND blocking_locks.pid != blocked_locks.pid
        JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
        WHERE NOT blocked_locks.granted;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                results = await cur.fetchall()
                return format_results(results, "No blocking locks detected.")
    except Exception as e:
        return f"Database error: {e}"

async def log_llm_usage(
    prompt_tokens: int, 
    completion_tokens: int, 
    cost_usd: float, 
    task_description: str
) -> str:
    """Logs the LLM API token usage to the audit table."""
    start_time = time.time()
    try:
        # Wrap the dictionary in json.dumps() so Postgres accepts it into the JSONB column
        parameters = json.dumps({
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "estimated_cost_usd": cost_usd,
            "task": task_description
        })
        
        duration = (time.time() - start_time) * 1000
        await log_audit_event("log_llm_usage", parameters, "SUCCESS", duration)
        
        return f"✅ Logged {prompt_tokens + completion_tokens} tokens to audit log."
    except Exception as e:
        return f"❌ Failed to log usage: {str(e)}"

async def table_bloat_report(limit: int = 10) -> str:
    """Returns tables with the highest percentage of dead tuples (bloat). Use this to see if VACUUM is needed."""
    query = """
        SELECT relname AS table_name, n_live_tup AS live_tuples, n_dead_tup AS dead_tuples,
               CASE WHEN n_live_tup + n_dead_tup > 0
                    THEN round((n_dead_tup::numeric / (n_live_tup + n_dead_tup)) * 100, 2)
                    ELSE 0 END AS dead_tuple_pct
        FROM pg_stat_user_tables ORDER BY dead_tuple_pct DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No table statistics found.")
    except Exception as e:
        return f"Database error: {e}"