# Postgres MCP for Auditing

A production-grade Model Context Protocol (MCP) server that transforms Claude (or any MCP-compatible client) into an autonomous PostgreSQL Database Administrator.

## Features

This server exposes a powerful suite of database administration and auditing tools through MCP:

### 🔍 Diagnostics
- **ping_database**: Check database connectivity and basic health.
- **slow_queries**: Retrieve the most time-consuming queries using `pg_stat_statements`.
- **active_sessions**: View currently running queries and active connections.
- **cache_hit_rate**: Analyze database cache efficiency.
- **blocking_lock_tree**: Discover complex lock dependencies and blockages.
- **table_bloat_report**: Identify dead tuples and space wastage in tables.
- **high_variance_queries**: Find queries that are usually fast but occasionally very slow.
- **queries_by_io**: List queries causing the most disk reads.
- **temp_spill_queries**: Identify queries writing to temporary files.
- **query_regression_report**: Automatically compare performance against a baseline snapshot.
- **explain_query**: Securely run EXPLAIN on provided SQL.
- **explain_summary**: Distill complex EXPLAIN JSON into plain-language bullet points.
- **latency_percentiles**: View standard deviation alongside min/mean/max latency.
- **log_llm_usage**: Internal metric tracking for auditing usage.

### 📈 Index Analysis
- **missing_index_candidates**: Find tables that could benefit from indexing based on sequential scan stats.
- **unused_indexes**: Identify indexes that consume space but are rarely used.
- **duplicate_indexes**: Detect redundant indexes that can be safely removed.
- **suggest_indexes**: Get intelligent index suggestions based on query patterns and EXPLAIN plans.
- **bloated_indexes**: Estimate dead space within indexes.
- **unindexed_foreign_keys**: Compare foreign key constraints with existing indexes to flag cascading delete risks.
- **index_usage_stats**: Get detailed read/hit statistics per index.
- **index_health_summary**: Provides a rolled-up schema score summarizing index health.

### 🧠 Dynamic Analysis & Workflows
- **get_database_schema**: Allows the LLM to learn the database structure (tables, columns, types, constraints).
- **execute_dynamic_query**: Allows the LLM to run custom, generated SQL (safely restricted to read-only `SELECT` statements).
- **save_query**: The LLM can permanently cache successful queries to `saved_queries.yaml` for zero-shot future use.
- **list_saved_queries / run_saved_query**: Re-use parameterized queries to drastically cut down on token costs and hallucinations.
- **list_saved_workflows / run_workflow**: Chain multiple diagnostics tools into a single, automated server-side report (e.g., `weekly_health_review`).

### 🛠️ Maintenance & Safety
- **vacuum_table**: Execute VACUUM safely to reclaim storage and update visibility maps.
- **analyze_table**: Update table statistics for the query planner.
- **reindex_index**: Rebuild corrupted or bloated indexes.

### 🚦 Session Control
- **cancel_query**: Gently cancel a long-running or rogue query.
- **terminate_session**: Forcefully disconnect a stuck or problematic session.

### 🛡️ Security & Auditing Design
All state-modifying tools (like `vacuum_table`, `cancel_query`, `terminate_session`) enforce a strict **Confirmation Pattern**. If an LLM attempts to execute them, the server defaults to a dry run, forcing the model to read a warning, and requires `confirm=True` on a subsequent call to execute. 
Additionally, all executed actions are permanently recorded in an `mcp_audit_log` table for compliance and traceability.

---

## 🚀 Installation & Setup

### Prerequisites
- Python 3.12 or higher.
- A PostgreSQL 13+ database.
- The `pg_stat_statements` extension must be enabled in your PostgreSQL database for full diagnostic capabilities.

### Option 1: Run instantly with `uvx` (Recommended)
You don't need to clone the repository or manually manage virtual environments. Just run it using `uvx` (the `uv` package manager's executor).

```bash
uvx pg-auditor --db "postgresql://user:pass@localhost:5432/mydb"
```

### Option 2: Docker
Run the server completely containerized:

```bash
docker build -t pg-auditor .
docker run -i pg-auditor --db "postgresql://user:pass@host.docker.internal:5432/mydb"
```

### Option 3: Local Installation
If you prefer to run it from source:
```bash
git clone https://github.com/AaroAarav/Postgres-MCP-for-Auditing.git
cd Postgres-MCP-for-Auditing
pip install uv
uv sync
uv run pg-auditor --db "postgresql://user:pass@localhost:5432/mydb"
```

---

## 🔌 Connecting to Claude Desktop

To give Claude Desktop access to this server and enable its PostgreSQL DBA capabilities, add the following configuration to your `claude_desktop_config.json`:

**MacOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "pg-auditor": {
      "command": "uvx",
      "args": [
        "pg-auditor",
        "--db",
        "postgresql://user:pass@localhost:5432/mydb"
      ]
    }
  }
}
```

*Note: Replace the `--db` argument with your actual PostgreSQL connection string.*

## 🔒 Database User Permissions
The user specified in your connection string should ideally have the following privileges for full functionality:
- `pg_monitor` role (or superuser) to read system statistics and views.
- Permission to execute `pg_cancel_backend` and `pg_terminate_backend` if session control is needed.

## 🤝 Contributing
Contributions are welcome! Please open an issue or submit a Pull Request to help improve the tool.