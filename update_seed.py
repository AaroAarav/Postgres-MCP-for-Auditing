import os

with open('seed.py', 'r', encoding='utf-8') as f:
    content = f.read()

injection = '''
                print("7. Creating unindexed foreign keys...")
                await cur.execute("DROP TABLE IF EXISTS test_child;")
                await cur.execute("DROP TABLE IF EXISTS test_parent CASCADE;")
                await cur.execute("CREATE TABLE test_parent (id serial PRIMARY KEY, name text);")
                await cur.execute("CREATE TABLE test_child (id serial PRIMARY KEY, parent_id int REFERENCES test_parent(id) ON DELETE CASCADE);")
                await cur.execute("INSERT INTO test_parent (name) VALUES ('parent1'), ('parent2');")
                await cur.execute("INSERT INTO test_child (parent_id) VALUES (1), (2), (1);")
                
                print("8. Creating another bloated index table...")
                await cur.execute("DROP TABLE IF EXISTS bloat_table;")
                await cur.execute("CREATE TABLE bloat_table (id serial PRIMARY KEY, value text);")
                await cur.execute("CREATE INDEX idx_bloat_value ON bloat_table(value);")
                await cur.execute("INSERT INTO bloat_table (value) SELECT md5(random()::text) FROM generate_series(1, 50000);")
                await cur.execute("UPDATE bloat_table SET value = md5(random()::text) WHERE id % 2 = 0;")
'''
content = content.replace('print("\\n✅ Database seeded successfully! You are ready to test.")', injection + '\n        print("\\n✅ Database seeded successfully! You are ready to test.")')

with open('seed.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('seed.py updated!')
