import logging
from src.db.connection import get_db_connection
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

async def get_database_schema() -> str:
    """
    Returns the schema of the database, including all tables, columns, and their data types.
    Use this to understand the structure of the user's data before generating custom queries.
    """
    query = """
        SELECT 
            t.table_name,
            c.column_name,
            c.data_type,
            c.character_maximum_length,
            tc.constraint_type
        FROM information_schema.tables t
        JOIN information_schema.columns c ON t.table_name = c.table_name
        LEFT JOIN information_schema.key_column_usage kcu 
            ON c.table_name = kcu.table_name AND c.column_name = kcu.column_name
        LEFT JOIN information_schema.table_constraints tc 
            ON kcu.constraint_name = tc.constraint_name AND t.table_name = tc.table_name
        WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name, c.ordinal_position;
    """
    try:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query)
                results = await cur.fetchall()
                
                if not results:
                    return "No tables found in the public schema."

                # Group by table to make the output highly readable for the LLM
                schema_dict = {}
                for row in results:
                    t_name = row['table_name']
                    if t_name not in schema_dict:
                        schema_dict[t_name] = []
                    
                    col_info = f"- {row['column_name']} ({row['data_type']})"
                    if row['constraint_type']:
                        col_info += f" [{row['constraint_type']}]"
                    schema_dict[t_name].append(col_info)
                
                output = "Database Schema:\n"
                for table, columns in schema_dict.items():
                    output += f"\nTable: {table}\n"
                    output += "\n".join(columns) + "\n"
                
                return output
                
    except Exception as e:
        logger.error(f"Failed to fetch schema: {e}")
        return f"Database error: {e}"
