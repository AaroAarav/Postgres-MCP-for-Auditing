import os
import re

with open('src/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add get_database_schema import
schema_import = '''
from src.tools.schema import get_database_schema
'''
content = content.replace('from src.tools.diagnostics import (', schema_import + 'from src.tools.diagnostics import (')

# Add execute_dynamic_query and save_query to workflows import
wf_import_old = 'list_saved_queries, run_saved_query, list_saved_workflows, run_workflow'
wf_import_new = 'list_saved_queries, run_saved_query, list_saved_workflows, run_workflow, execute_dynamic_query, save_query'
content = content.replace(wf_import_old, wf_import_new)

# Register get_database_schema tool
schema_tool = '''
# Register Schema Tools
mcp.tool()(get_database_schema)
'''
content = content.replace('# Register Workflow Tools', schema_tool + '\\n# Register Workflow Tools')

# Register dynamic query tools
wf_tools = '''
mcp.tool()(execute_dynamic_query)
mcp.tool()(save_query)
'''
content = content.replace('mcp.tool()(run_workflow)', 'mcp.tool()(run_workflow)\\n' + wf_tools)

with open('src/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('main.py updated successfully!')
