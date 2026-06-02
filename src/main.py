import asyncio
import logging
import sys
import psycopg
from contextlib import asynccontextmanager
from fastmcp import FastMCP
from src.db.audit import initialize_audit_schema
from src.db.connection import get_db_connection
from src.tools.sessions import cancel_query, terminate_session
from src.db.connection import get_db_connection, init_pool, close_pool
from src.db.audit import initialize_audit_schema
import argparse
import os
from src.config.settings import settings

# Import isolated tool modules

from src.tools.schema import get_database_schema
from src.tools.history import get_recent_queries
from src.tools.health import ping_database, active_sessions, cache_hit_rate, table_bloat_report, blocking_lock_tree
from src.tools.performance import slow_queries, high_variance_queries, queries_by_io, temp_spill_queries, query_regression_report, latency_percentiles
from src.tools.explain import explain_query, explain_summary
from src.db.audit import log_llm_usage

from src.tools.workflows import (
    list_saved_queries, run_saved_query, list_saved_workflows, run_workflow, execute_dynamic_query, save_query
)
from src.tools.smart_query import smart_query
from src.services.schema_intelligence import schema_manager
from src.tools.indexes import (
    missing_index_candidates, unused_indexes, duplicate_indexes, suggest_indexes, bloated_indexes, unindexed_foreign_keys, index_usage_stats, index_health_summary
)
from src.tools.maintenance import (
    vacuum_table, analyze_table, reindex_index
)

# --- WINDOWS ASYNC FIX FOR PSYCOPG3 ---
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# --------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def server_lifespan(server: FastMCP):
    """Validates the database environment before the MCP server fully starts."""
    logger.info("Bootstrapping PG Auditor with Production Hardening...")
    
    try:
        # 1. Initialize the global connection pool FIRST
        await init_pool()
        
        # 2. Verify and create the Audit Schema
        await initialize_audit_schema()
        
        # 3. Run Validation Checks
        async with get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SHOW server_version_num;")
                version_num = int((await cur.fetchone())[0])
                version_str = f"PostgreSQL {version_num // 10000}.{(version_num % 10000) // 100}"
                
                if version_num < 130000:
                    logger.warning(f"⚠️ Unsupported PostgreSQL version ({version_str}). Minimum recommended is PG 13.")
                else:
                    logger.info(f"✅ Connected to {version_str}")

                await cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements';")
                if not await cur.fetchone():
                    logger.warning("⚠️ 'pg_stat_statements' extension is missing.")
                else:
                    logger.info("✅ 'pg_stat_statements' extension detected.")

                await cur.execute("""
                    SELECT current_user, 
                           (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) as is_superuser,
                           pg_has_role(current_user, 'pg_monitor', 'MEMBER') as is_monitor
                """)
                user_info = await cur.fetchone()
                if not (user_info[1] or user_info[2]):
                    logger.warning(f"⚠️ User '{user_info[0]}' lacks superuser or pg_monitor roles.")
                else:
                    logger.info(f"✅ User '{user_info[0]}' has sufficient privileges.")
                    
        # 4. Pre-warm Schema Cache
        try:
            logger.info("Fetching and caching database schema...")
            await schema_manager.fetch_schema(force_refresh=True)
            logger.info("✅ Schema Intelligence Layer ready.")
        except Exception as e:
            logger.warning(f"⚠️ Failed to pre-warm schema cache: {e}")
            
    except psycopg.OperationalError as e:
        logger.error(f"🚨 CRITICAL: Database connection failed during startup: {e}")
    except Exception as e:
        logger.error(f"🚨 Startup validation failed: {e}")
        
    # Yield control to FastMCP to run the server
    yield
    
    # 4. Cleanup on shutdown
    logger.info("Shutting down pg-auditor...")
    await close_pool()

# Initialize FastMCP Server
mcp = FastMCP("pg-auditor", lifespan=server_lifespan)

# Register Diagnostics Tools
mcp.tool()(ping_database)
mcp.tool()(slow_queries)
mcp.tool()(active_sessions)
mcp.tool()(cache_hit_rate)
mcp.tool()(blocking_lock_tree)
mcp.tool()(table_bloat_report)
mcp.tool()(log_llm_usage)
mcp.tool()(high_variance_queries)
mcp.tool()(queries_by_io)
mcp.tool()(temp_spill_queries)
mcp.tool()(query_regression_report)
mcp.tool()(explain_query)
mcp.tool()(explain_summary)
mcp.tool()(latency_percentiles)


# Register Index Tools
mcp.tool()(missing_index_candidates)
mcp.tool()(unused_indexes)
mcp.tool()(duplicate_indexes)
mcp.tool()(suggest_indexes)
mcp.tool()(bloated_indexes)
mcp.tool()(unindexed_foreign_keys)
mcp.tool()(index_usage_stats)
mcp.tool()(index_health_summary)



# Register Schema Tools
mcp.tool()(get_database_schema)

# Register Workflow Tools
mcp.tool()(list_saved_queries)
mcp.tool()(run_saved_query)
mcp.tool()(list_saved_workflows)
mcp.tool()(run_workflow)
mcp.tool()(smart_query)
mcp.tool()(execute_dynamic_query)
mcp.tool()(save_query)
mcp.tool()(get_recent_queries)



# Register Maintenance Tools
mcp.tool()(vacuum_table)
mcp.tool()(analyze_table)
mcp.tool()(reindex_index)


mcp.tool()(cancel_query)
mcp.tool()(terminate_session)



# ... (keep all your existing imports, lifespan, and tool registrations exactly as they are) ...

def main():
    """Entry point for the MCP server with CLI argument parsing."""
    parser = argparse.ArgumentParser(description="PostgreSQL DBA Auditor MCP Server")
    parser.add_argument(
        "--db", 
        type=str, 
        help="PostgreSQL connection string (overrides DATABASE_URL env var)"
    )
    
    # FastMCP uses standard args too, so we parse known args to not break its internal CLI
    args, unknown = parser.parse_known_args()

    # Override the database URL if provided via CLI
    if args.db:
        settings.database_url = args.db
        os.environ["DATABASE_URL"] = args.db
        logger.info("Using database URL provided via --db CLI argument.")

    # Pass control to FastMCP
    mcp.run()

if __name__ == "__main__":
    main()