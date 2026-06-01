import json
import time
import logging
from typing import Any, Dict, Optional
from src.db.connection import get_db_connection

logger = logging.getLogger(__name__)

async def initialize_audit_schema() -> None:
    """Creates the audit log table if it does not already exist."""
    schema_sql = """
        CREATE TABLE IF NOT EXISTS mcp_audit_log (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            db_user TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            parameters JSONB NOT NULL,
            status TEXT NOT NULL,
            duration_ms NUMERIC NOT NULL,
            error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_mcp_audit_log_time ON mcp_audit_log(timestamp DESC);
    """
    try:
        async with get_db_connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                await cur.execute(schema_sql)
                logger.info("✅ Audit log schema verified.")
    except Exception as e:
        logger.error(f"🚨 Failed to initialize audit schema: {e}")

async def log_audit_event(
    tool_name: str,
    parameters: Dict[str, Any],
    status: str,
    duration_ms: float,
    error_message: Optional[str] = None
) -> None:
    """Asynchronously writes a tool execution record to the audit log."""
    query = """
        INSERT INTO mcp_audit_log (db_user, tool_name, parameters, status, duration_ms, error_message)
        VALUES (current_user, %s, %s, %s, %s, %s);
    """
    try:
        async with get_db_connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor() as cur:
                await cur.execute(
                    query,
                    (
                        tool_name,
                        json.dumps(parameters),
                        status,
                        round(duration_ms, 2),
                        error_message
                    )
                )
    except Exception as e:
        # We log to stderr if auditing fails, but we don't crash the application
        logger.error(f"CRITICAL: Failed to write to audit log: {e}")

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