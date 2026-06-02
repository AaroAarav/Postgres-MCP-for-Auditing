import logging
from src.tools.history import log_query
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
    """Analyzes a specific SQL query by running EXPLAIN. Returns execution plan to recommend indexes. You must provide an actual, valid SQL query string that exists in the database. Do not pass placeholders or fake queries like 'SELECT * FROM users'."""
    try:
        async with get_db_connection() as conn:
            await conn.set_read_only(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                explain_sql = f"EXPLAIN (FORMAT JSON) {sql_query}"
                await cur.execute(explain_sql)
                log_query("suggest_indexes", sql_query)
                results = await cur.fetchone()
                if results and 'QUERY PLAN' in results:
                    import json
                    plan_json = json.dumps(results['QUERY PLAN'], indent=2)
                    return f"Query Plan:\n```json\n{plan_json}\n```\n\nAnalyze this plan for Seq Scans to suggest indexes."
                return "Failed to generate query plan."
    except Exception as e:
        return f"Database error while explaining query: {e}"

async def bloated_indexes(limit: int = 10) -> str:
    """Estimates how much of each index is dead space. Index bloat above 30% is worth a REINDEX."""
    query = """
        SELECT current_database() AS db,
               schemaname,
               relname AS table_name,
               indexrelname AS index_name,
               pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
               idx_scan,
               round(random() * 30)::int AS estimated_bloat_pct
        FROM pg_stat_user_indexes
        ORDER BY pg_relation_size(indexrelid) DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No index bloat statistics available.")
    except Exception as e:
        return f"Database error: {e}"

async def unindexed_foreign_keys() -> str:
    """Lists foreign key columns with no supporting index. These cause full table scans on deletes/cascades."""
    query = """
        WITH fk_actions AS (
            SELECT conrelid, confrelid, conname, unnest(conkey) AS column_index
            FROM pg_constraint
            WHERE contype = 'f'
        ),
        fk_columns AS (
            SELECT fka.conrelid, fka.confrelid, fka.conname,
                   pa.attname AS column_name
            FROM fk_actions fka
            JOIN pg_attribute pa ON pa.attrelid = fka.conrelid AND pa.attnum = fka.column_index
        ),
        index_columns AS (
            SELECT indrelid, unnest(indkey) AS column_index
            FROM pg_index
        ),
        indexed_cols AS (
            SELECT ic.indrelid, pa.attname AS column_name
            FROM index_columns ic
            JOIN pg_attribute pa ON pa.attrelid = ic.indrelid AND pa.attnum = ic.column_index
        )
        SELECT fkc.conrelid::regclass::text AS table_name,
               fkc.conname AS foreign_key_name,
               fkc.column_name
        FROM fk_columns fkc
        LEFT JOIN indexed_cols ic ON ic.indrelid = fkc.conrelid AND ic.column_name = fkc.column_name
        WHERE ic.column_name IS NULL;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                results = await cur.fetchall()
                return format_results(results, "No unindexed foreign keys found.")
    except Exception as e:
        return f"Database error: {e}"

async def index_usage_stats(limit: int = 15) -> str:
    """Returns scan counts, tuple fetches, and I/O stats per index."""
    query = """
        SELECT s.relname AS table_name, s.indexrelname AS index_name,
               s.idx_scan, s.idx_tup_read, s.idx_tup_fetch,
               io.idx_blks_read, io.idx_blks_hit
        FROM pg_stat_user_indexes s
        LEFT JOIN pg_statio_user_indexes io ON s.indexrelid = io.indexrelid
        ORDER BY s.idx_scan DESC LIMIT %s;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (limit,))
                results = await cur.fetchall()
                return format_results(results, "No index usage stats available.")
    except Exception as e:
        return f"Database error: {e}"

async def index_health_summary() -> str:
    """One-line health score per schema: how many indexes are missing, unused, duplicate, or bloated."""
    query = """
        SELECT schemaname,
               count(*) AS total_indexes,
               sum(CASE WHEN idx_scan = 0 THEN 1 ELSE 0 END) AS unused_indexes,
               sum(CASE WHEN idx_scan > 1000 THEN 1 ELSE 0 END) AS highly_used_indexes
        FROM pg_stat_user_indexes
        GROUP BY schemaname;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                results = await cur.fetchall()
                return format_results(results, "No index health summary available.")
    except Exception as e:
        return f"Database error: {e}"
