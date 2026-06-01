import time
import logging
from psycopg.rows import dict_row
from src.db.connection import get_db_connection
from src.db.audit import log_audit_event

logger = logging.getLogger(__name__)

async def _is_self_target(cur, target_pid: int) -> bool:
    """Helper to prevent the MCP server from terminating its own connection."""
    await cur.execute("SELECT pg_backend_pid();")
    current_pid = (await cur.fetchone())["pg_backend_pid"]
    return current_pid == target_pid

async def cancel_query(pid: int, confirm: bool = False) -> str:
    """
    Cancels the currently running query for a specific session PID, but leaves the session connected.
    Use this first for runaway queries before attempting to terminate the whole session.
    Requires confirm=True to execute.
    """
    if not confirm:
        return (
            f"⚠️ DRY RUN: You are about to CANCEL the query running on PID {pid}.\n"
            f"This is a gentle interruption. The user's database connection will remain active.\n"
            f"To proceed, call this tool again with confirm=True."
        )

    start_time = time.time()
    try:
        async with get_db_connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                
                # Guardrail: Prevent self-termination
                if await _is_self_target(cur, pid):
                    return "❌ ACTION BLOCKED: You cannot cancel the query of the active MCP server connection."
                
                await cur.execute("SELECT pg_cancel_backend(%s) AS success;", (pid,))
                result = await cur.fetchone()
                duration = (time.time() - start_time) * 1000
                
                if result and result["success"]:
                    await log_audit_event("cancel_query", {"pid": pid}, "SUCCESS", duration)
                    return f"✅ Successfully sent cancel signal to query on PID {pid}."
                else:
                    await log_audit_event("cancel_query", {"pid": pid}, "FAILED_NOT_FOUND", duration)
                    return f"❌ Failed to cancel query. PID {pid} might not exist or isn't running a query."
                    
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        await log_audit_event("cancel_query", {"pid": pid}, "FAILED", duration, str(e))
        logger.error(f"Error canceling query on PID {pid}: {e}")
        return f"❌ Database error: {str(e)}"


async def terminate_session(pid: int, confirm: bool = False) -> str:
    """
    Forcefully terminates a database session/connection by its PID.
    Use this ONLY if cancel_query fails or if the session is 'idle in transaction' and blocking others.
    Requires confirm=True to execute.
    """
    if not confirm:
        return (
            f"⚠️ DRY RUN: You are about to TERMINATE the entire session for PID {pid}.\n"
            f"This will forcefully disconnect the client. Use only as a last resort.\n"
            f"To proceed, call this tool again with confirm=True."
        )

    start_time = time.time()
    try:
        async with get_db_connection() as conn:
            await conn.set_autocommit(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                
                # Guardrail: Prevent self-termination
                if await _is_self_target(cur, pid):
                    return "❌ ACTION BLOCKED: You cannot terminate the active MCP server connection. That would kill me!"
                
                await cur.execute("SELECT pg_terminate_backend(%s) AS success;", (pid,))
                result = await cur.fetchone()
                duration = (time.time() - start_time) * 1000
                
                if result and result["success"]:
                    await log_audit_event("terminate_session", {"pid": pid}, "SUCCESS", duration)
                    return f"✅ Successfully terminated session for PID {pid}."
                else:
                    await log_audit_event("terminate_session", {"pid": pid}, "FAILED_NOT_FOUND", duration)
                    return f"❌ Failed to terminate session. PID {pid} might not exist or you lack privileges."
                    
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        await log_audit_event("terminate_session", {"pid": pid}, "FAILED", duration, str(e))
        logger.error(f"Error terminating session on PID {pid}: {e}")
        return f"❌ Database error: {str(e)}"