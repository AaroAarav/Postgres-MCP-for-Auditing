from collections import deque
import json
from datetime import datetime, timezone

# Thread-safe ring buffer for the last 50 queries executed by the MCP server tools
# Each entry is a dict: {"timestamp": str, "tool": str, "query": str}
_recent_queries_log = deque(maxlen=50)

def log_query(tool_name: str, sql_query: str):
    """
    Appends a query to the in-memory round logger.
    """
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
        "query": sql_query.strip()
    }
    _recent_queries_log.append(entry)

async def get_recent_queries() -> str:
    """
    Returns the most recent SQL queries executed by the LLM through the MCP server.
    Use this to see what you just ran before calling explain_query or suggest_indexes.
    """
    if not _recent_queries_log:
        return "No queries have been executed yet in this session."
    
    # Return from newest to oldest
    log_list = list(_recent_queries_log)
    log_list.reverse()
    
    return "Recent Queries Executed by MCP:\n\n" + json.dumps(log_list, indent=2)
