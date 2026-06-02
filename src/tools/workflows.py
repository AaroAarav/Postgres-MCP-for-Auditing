import yaml
import os
import json
import re
from src.db.connection import get_db_connection
from src.tools.formatters import format_results
from psycopg.rows import dict_row
import logging
from src.tools.history import log_query

logger = logging.getLogger(__name__)

def load_yaml(filename: str):
    path = os.path.join(os.getcwd(), filename)
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or []

SAVED_QUERIES = load_yaml("saved_queries.yaml")
WORKFLOWS = load_yaml("workflows.yaml")

async def list_saved_queries() -> str:
    """Returns metadata of all available predefined queries."""
    if not SAVED_QUERIES:
        return "No saved queries found."
    
    result = []
    for q in SAVED_QUERIES:
        info = f"- **{q['name']}**: {q.get('description', '')}"
        if 'params' in q and q['params']:
            params_info = ", ".join([f"{p['name']} ({p.get('type', 'any')})" for p in q['params']])
            info += f" (Params: {params_info})"
        result.append(info)
    return "Available Saved Queries:\n" + "\n".join(result)

async def run_saved_query(query_name: str, params_json: str = "{}") -> str:
    """Executes a predefined query by name. Pass params as a JSON string."""
    query_def = next((q for q in SAVED_QUERIES if q['name'] == query_name), None)
    if not query_def:
        return f"Saved query '{query_name}' not found."
    
    try:
        params_dict = json.loads(params_json)
    except Exception as e:
        return f"Failed to parse params JSON: {e}"
    
    # Apply defaults
    if 'params' in query_def:
        for p in query_def['params']:
            if p['name'] not in params_dict and 'default' in p:
                params_dict[p['name']] = p['default']

    sql = query_def['sql']
    
    # Simple named parameter replacement for psycopg using regex
    # Replace :param_name with %(param_name)s
    # Use negative lookbehind to avoid replacing PostgreSQL casts like ::numeric
    sql = re.sub(r'(?<!:):([a-zA-Z_]\w*)', r'%(\1)s', sql)
    
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params_dict)
                log_query(f"run_saved_query({query_name})", sql)
                results = await cur.fetchall()
                return format_results(results, f"No results for query '{query_name}'.")
    except Exception as e:
        return f"Database error: {e}"

async def list_saved_workflows() -> str:
    """Returns metadata of all available workflows."""
    if not WORKFLOWS:
        return "No saved workflows found."
    
    result = []
    for w in WORKFLOWS:
        result.append(f"- **{w['name']}**: {w.get('description', '')} ({len(w.get('steps', []))} steps)")
    return "Available Workflows:\n" + "\n".join(result)

async def run_workflow(workflow_name: str) -> str:
    """Sequentially calls multiple tools/queries as defined in the workflow YAML and aggregates the results."""
    workflow_def = next((w for w in WORKFLOWS if w['name'] == workflow_name), None)
    if not workflow_def:
        return f"Workflow '{workflow_name}' not found."
    
    # Dynamically import tools to call them
    import src.tools.diagnostics as diag
    import src.tools.indexes as idx
    import inspect
    
    def get_tool_func(tool_name):
        if hasattr(diag, tool_name):
            return getattr(diag, tool_name)
        if hasattr(idx, tool_name):
            return getattr(idx, tool_name)
        return None

    results = [f"# Workflow Report: {workflow_name}", f"*{workflow_def.get('description', '')}*\n"]
    
    for step in workflow_def.get('steps', []):
        if 'tool' in step:
            tool_name = step['tool']
            func = get_tool_func(tool_name)
            if not func:
                results.append(f"## Step: {tool_name}\nError: Tool not found.\n")
                continue
            
            params = step.get('params', {})
            try:
                # Handle async and non-async tools if any
                if inspect.iscoroutinefunction(func):
                    res = await func(**params)
                else:
                    res = func(**params)
                results.append(f"## {tool_name}\n{res}\n")
            except Exception as e:
                results.append(f"## {tool_name}\nError running tool: {e}\n")
                
        elif 'query' in step:
            query_name = step['query']
            params = step.get('params', {})
            try:
                res = await run_saved_query(query_name, json.dumps(params))
                results.append(f"## Query: {query_name}\n{res}\n")
            except Exception as e:
                results.append(f"## Query: {query_name}\nError running query: {e}\n")
                
    return "\n".join(results)

async def execute_dynamic_query(sql: str, query_name: str, query_description: str) -> str:
    """
    Executes a custom SQL query generated by the LLM and automatically saves it for future use on success.
    Strictly limited to SELECT statements to ensure safety.
    
    You MUST provide a clear, concise `query_name` (e.g. 'find_bloated_tables') 
    and a `query_description` explaining what the query does.
    """
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
        return "Error: For safety, dynamic queries are strictly restricted to SELECT or WITH ... SELECT statements."
    
    # Very basic naive check for dangerous keywords (a real app would use a parser or strict permissions)
    dangerous_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "GRANT", "REVOKE", "EXECUTE"]
    for keyword in dangerous_keywords:
        if re.search(fr"\b{keyword}\b", sql_upper):
            return f"Error: Dangerous keyword '{keyword}' detected. Dynamic queries are read-only."
            
    try:
        async with get_db_connection() as conn:
            # Enforce read-only mode for this transaction just in case
            await conn.set_read_only(True)
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql)
                log_query("execute_dynamic_query", sql)
                results = await cur.fetchall()
                
                # Auto-save successfully executed query
                try:
                    await save_query(query_name, sql, query_description)
                except Exception as e:
                    logger.warning(f"Failed to auto-save query: {e}")
                    
                return format_results(results, "No results found for dynamic query.")
    except Exception as e:
        logger.error(f"Dynamic query failed: {e}")
        return f"Database error: {e}"

async def save_query(name: str, sql: str, description: str = "") -> str:
    """
    Saves a dynamic query into saved_queries.yaml so it can be reused later without regenerating it.
    """
    # Validate it does not already exist
    if any(q['name'] == name for q in SAVED_QUERIES):
        return f"Error: A saved query with the name '{name}' already exists."
        
    new_query = {
        "name": name,
        "description": description,
        "sql": sql
    }
    
    SAVED_QUERIES.append(new_query)
    
    try:
        path = os.path.join(os.getcwd(), "saved_queries.yaml")
        # Dump back to yaml
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(SAVED_QUERIES, f, default_flow_style=False, sort_keys=False)
        return f"✅ Successfully saved query '{name}' to saved_queries.yaml. It can now be executed via run_saved_query."
    except Exception as e:
        # Revert memory append if disk fails
        SAVED_QUERIES.pop()
        return f"Error saving query to disk: {e}"
