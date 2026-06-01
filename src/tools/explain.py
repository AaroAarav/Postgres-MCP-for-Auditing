import logging
from psycopg.rows import dict_row
from src.db.connection import get_db_connection
from src.tools.formatters import format_results

logger = logging.getLogger(__name__)
from src.tools.history import log_query
import json

async def explain_query(sql_query: str) -> str:
    """Runs EXPLAIN on a query you provide and returns the execution plan. You must provide an actual, valid SQL query string (e.g. 'SELECT * FROM users'). Do not pass placeholders like '<your_sql_query_here>'."""
    try:
        async with get_db_connection() as conn:
            await conn.set_read_only(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                explain_sql = f"EXPLAIN (FORMAT JSON) {sql_query}"
                await cur.execute(explain_sql)
                log_query("explain_query", sql_query)
                results = await cur.fetchone()
                if results and 'QUERY PLAN' in results:
                    import json
                    return json.dumps(results['QUERY PLAN'], indent=2)
                return "Failed to generate query plan."
    except Exception as e:
        return f"Database error while explaining query: {e}"

async def explain_summary(sql_query: str) -> str:
    """Takes a SQL query, runs EXPLAIN, and returns a plain-language description of the bottleneck. You must provide an actual, valid SQL query string (e.g. 'SELECT * FROM users'). Do not pass placeholders or raw JSON."""
    try:
        async with get_db_connection() as conn:
            await conn.set_read_only(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                explain_sql = f"EXPLAIN (FORMAT JSON) {sql_query}"
                await cur.execute(explain_sql)
                log_query("explain_summary", sql_query)
                results = await cur.fetchone()
                
                if not results or 'QUERY PLAN' not in results:
                    return "Failed to generate query plan."
                    
                plan_data = results['QUERY PLAN']
                
                if isinstance(plan_data, list):
                    plan_data = plan_data[0]
                
                plan = plan_data.get('Plan', {})
                
                def find_bottlenecks(node):
                    bottlenecks = []
                    if node.get('Node Type') == 'Seq Scan':
                        bottlenecks.append(f"Sequential Scan on {node.get('Relation Name', 'unknown')} (cost: {node.get('Total Cost', 0)})")
                    elif 'Join' in node.get('Node Type', ''):
                        bottlenecks.append(f"{node.get('Node Type')} (cost: {node.get('Total Cost', 0)})")
                    
                    if 'Plans' in node:
                        for subplan in node['Plans']:
                            bottlenecks.extend(find_bottlenecks(subplan))
                    return bottlenecks
                    
                bottlenecks = find_bottlenecks(plan)
                if not bottlenecks:
                    return "Plan seems straightforward with no obvious Seq Scans or major joins."
                
                summary = "Potential bottlenecks found in plan:\n"
                for b in set(bottlenecks):
                    summary += f"- {b}\n"
                return summary
    except Exception as e:
        return f"Error summarizing plan: {e}"