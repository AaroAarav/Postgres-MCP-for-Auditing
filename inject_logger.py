import os

with open('src/tools/workflows.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add import
if 'from src.tools.history import log_query' not in content:
    content = content.replace('import logging', 'import logging\\nfrom src.tools.history import log_query')

# 2. Add log_query to run_saved_query
if "log_query(f'run_saved_query({query_name})', sql)" not in content:
    old_run = '''                await cur.execute(sql, params_dict)
                results = await cur.fetchall()'''
    new_run = '''                await cur.execute(sql, params_dict)
                log_query(f"run_saved_query({query_name})", sql)
                results = await cur.fetchall()'''
    content = content.replace(old_run, new_run)

# 3. Add log_query to execute_dynamic_query
if 'log_query("execute_dynamic_query", sql)' not in content:
    old_dyn = '''                await cur.execute(sql)
                results = await cur.fetchall()'''
    new_dyn = '''                await cur.execute(sql)
                log_query("execute_dynamic_query", sql)
                results = await cur.fetchall()'''
    content = content.replace(old_dyn, new_dyn)

with open('src/tools/workflows.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated workflows.py")

# Now update diagnostics.py
with open('src/tools/diagnostics.py', 'r', encoding='utf-8') as f:
    content2 = f.read()

if 'from src.tools.history import log_query' not in content2:
    content2 = content2.replace('import logging', 'import logging\\nfrom src.tools.history import log_query')

if 'log_query("explain_query", explain_sql)' not in content2:
    old_exp = '''                await cur.execute(explain_sql)
                results = await cur.fetchone()'''
    new_exp = '''                await cur.execute(explain_sql)
                log_query("explain_query", sql_query)
                results = await cur.fetchone()'''
    content2 = content2.replace(old_exp, new_exp)

with open('src/tools/diagnostics.py', 'w', encoding='utf-8') as f:
    f.write(content2)

print("Updated diagnostics.py")

# Now update indexes.py
with open('src/tools/indexes.py', 'r', encoding='utf-8') as f:
    content3 = f.read()

if 'from src.tools.history import log_query' not in content3:
    content3 = content3.replace('import logging', 'import logging\\nfrom src.tools.history import log_query')

if 'log_query("suggest_indexes", sql_query)' not in content3:
    old_sug = '''                await cur.execute(explain_sql)
                results = await cur.fetchone()'''
    new_sug = '''                await cur.execute(explain_sql)
                log_query("suggest_indexes", sql_query)
                results = await cur.fetchone()'''
    content3 = content3.replace(old_sug, new_sug)

with open('src/tools/indexes.py', 'w', encoding='utf-8') as f:
    f.write(content3)

print("Updated indexes.py")
