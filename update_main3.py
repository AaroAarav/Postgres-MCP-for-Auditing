import os

with open('src/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add import
if 'from src.tools.history import get_recent_queries' not in content:
    content = content.replace('from src.tools.schema import get_database_schema', 'from src.tools.schema import get_database_schema\\nfrom src.tools.history import get_recent_queries')

# 2. Add tool registration
reg_str = 'mcp.tool()(get_recent_queries)'
if reg_str not in content:
    # We will put it right below save_query
    content = content.replace('mcp.tool()(save_query)', 'mcp.tool()(save_query)\\nmcp.tool()(get_recent_queries)')

with open('src/main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated main.py")
