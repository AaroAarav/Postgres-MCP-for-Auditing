import logging
from psycopg.rows import dict_row
from src.db.connection import get_db_connection
from src.tools.formatters import format_results

logger = logging.getLogger(__name__)

async def missing_index_candidates(limit: int = 10) -> str:
    """Identifies tables that might need indexes by finding those with high sequential scans."""
    query = """
        SELECT relname AS table_name, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch,
               CASE WHEN seq_scan > 0 THEN round(seq_tup_read::numeric / seq_scan, 2) ELSE 0 END AS avg_tuples_per_seq_scan
        FROM pg_stat_user_tables WHERE seq_scan > 0 ORDER BY seq_tup_read DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No high sequential scan tables found.")
    except Exception as e:
        return f"Database error: {e}"

async def unused_indexes(limit: int = 10) -> str:
    """Finds indexes that have never been used to satisfy queries. Excludes unique/primary keys."""
    query = """
        SELECT s.schemaname, s.relname AS table_name, s.indexrelname AS index_name, s.idx_scan,
               pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size_pretty
        FROM pg_stat_user_indexes s JOIN pg_index i ON s.indexrelid = i.indexrelid
        WHERE s.idx_scan = 0 AND i.indisunique IS FALSE AND i.indisprimary IS FALSE
        ORDER BY pg_relation_size(s.indexrelid) DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No completely unused non-unique indexes found.")
    except Exception as e:
        return f"Database error: {e}"

async def duplicate_indexes() -> str:
    """Identifies redundant or duplicate indexes on the same table that index the exact same columns."""
    query = """
        SELECT indrelid::regclass::text AS table_name, array_agg(indexrelid::regclass::text) AS duplicated_indexes,
               indkey::text AS column_signatures
        FROM pg_index GROUP BY indrelid, indkey HAVING count(*) > 1;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                results = await cur.fetchall()
                for row in results:
                    row['duplicated_indexes'] = ", ".join(row['duplicated_indexes'])
                return format_results(results, "No duplicate indexes detected.")
    except Exception as e:
        return f"Database error: {e}"

async def suggest_indexes(sql_query: str) -> str:
    """Analyzes a specific SQL query by running EXPLAIN. Returns execution plan to recommend indexes."""
    try:
        async with get_db_connection() as conn:
            await conn.set_read_only(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                explain_sql = f"EXPLAIN (FORMAT JSON) {sql_query}"
                await cur.execute(explain_sql)
                results = await cur.fetchone()
                if results and 'QUERY PLAN' in results:
                    import json
                    plan_json = json.dumps(results['QUERY PLAN'], indent=2)
                    return f"Query Plan:\n```json\n{plan_json}\n```\n\nAnalyze this plan for Seq Scans to suggest indexes."
                return "Failed to generate query plan."
    except Exception as e:
        return f"Database error while explaining query: {e}"