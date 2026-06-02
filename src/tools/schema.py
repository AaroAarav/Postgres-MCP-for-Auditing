import logging
from src.services.schema_intelligence import schema_manager

logger = logging.getLogger(__name__)

async def get_database_schema() -> str:
    """
    Returns the schema of the database, including all tables, columns, and their data types.
    Use this to understand the structure of the user's data before generating custom queries.
    This schema is cached and will be returned instantly unless a refresh is triggered.
    """
    schema_text, _ = await schema_manager.fetch_schema()
    return schema_text
