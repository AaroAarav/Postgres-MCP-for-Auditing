import logging
from psycopg.rows import dict_row
from src.db.connection import get_db_connection
from src.tools.formatters import format_results

logger = logging.getLogger(__name__)
# Global snapshot for query regression
_pg_stat_statements_snapshot = {}

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

async def high_variance_queries(limit: int = 10) -> str:
    """Finds queries that are usually fast but occasionally very slow (high variance)."""
    query = """
        SELECT substring(query, 1, 100) AS query_preview, calls,
               round(mean_exec_time::numeric, 2) AS mean_time_ms,
               round(max_exec_time::numeric, 2) AS max_time_ms,
               round(stddev_exec_time::numeric, 2) AS stddev_time_ms
        FROM pg_stat_statements
        WHERE calls > 10 AND stddev_exec_time > mean_exec_time
        ORDER BY stddev_exec_time DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No high variance queries found.")
    except Exception as e:
        return f"Database error: {e}"

async def queries_by_io(limit: int = 10) -> str:
    """Lists queries causing the most disk reads. Useful when the database is I/O bound."""
    query = """
        SELECT substring(query, 1, 100) AS query_preview, calls,
               shared_blks_read, shared_blks_hit,
               round((shared_blks_read * 8) / 1024.0, 2) AS read_mb
        FROM pg_stat_statements
        WHERE shared_blks_read > 0
        ORDER BY shared_blks_read DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No high I/O queries found.")
    except Exception as e:
        return f"Database error: {e}"

async def temp_spill_queries(limit: int = 10) -> str:
    """Lists queries writing to temp files on disk - a sign that work_mem is too low."""
    query = """
        SELECT substring(query, 1, 100) AS query_preview, calls,
               temp_blks_written, temp_blks_read,
               round((temp_blks_written * 8) / 1024.0, 2) AS temp_write_mb
        FROM pg_stat_statements
        WHERE temp_blks_written > 0
        ORDER BY temp_blks_written DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No queries spilling to temp found.")
    except Exception as e:
        return f"Database error: {e}"

async def query_regression_report(limit: int = 10) -> str:
    """Compares current pg_stat_statements to the last snapshot and shows queries that got slower."""
    global _pg_stat_statements_snapshot
    query = """
        SELECT queryid, substring(query, 1, 100) AS query_preview, calls,
               mean_exec_time
        FROM pg_stat_statements;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                current_stats = await cur.fetchall()
        
        if not _pg_stat_statements_snapshot:
            _pg_stat_statements_snapshot = {row['queryid']: row for row in current_stats}
            return "No previous snapshot found. Took a new baseline snapshot of pg_stat_statements."
        
        regressions = []
        for row in current_stats:
            qid = row['queryid']
            if qid in _pg_stat_statements_snapshot:
                old_row = _pg_stat_statements_snapshot[qid]
                old_mean = old_row['mean_exec_time']
                new_mean = row['mean_exec_time']
                
                if new_mean > old_mean * 1.2 and (new_mean - old_mean) > 5:
                    regressions.append({
                        "query_preview": row['query_preview'],
                        "old_mean_time_ms": round(old_mean, 2),
                        "new_mean_time_ms": round(new_mean, 2),
                        "increase_ms": round(new_mean - old_mean, 2)
                    })
        
        _pg_stat_statements_snapshot = {row['queryid']: row for row in current_stats}
        
        if not regressions:
            return "No query regressions found since the last snapshot. Updated baseline snapshot."
        
        regressions.sort(key=lambda x: x['increase_ms'], reverse=True)
        return format_results(regressions[:limit], "No query regressions found.")
    except Exception as e:
        return f"Database error: {e}"

async def latency_percentiles() -> str:
    """Returns minimum, average, maximum, and standard deviation of execution times (as a substitute for percentiles)."""
    query = """
        SELECT substring(query, 1, 100) AS query_preview, calls,
               round(min_exec_time::numeric, 2) AS min_time_ms,
               round(mean_exec_time::numeric, 2) AS mean_time_ms,
               round(max_exec_time::numeric, 2) AS max_time_ms,
               round(stddev_exec_time::numeric, 2) AS stddev_time_ms
        FROM pg_stat_statements
        WHERE calls > 5
        ORDER BY max_exec_time DESC LIMIT 15;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                results = await cur.fetchall()
                return format_results(results, "No latency statistics available.")
    except Exception as e:
        return f"Database error: {e}"