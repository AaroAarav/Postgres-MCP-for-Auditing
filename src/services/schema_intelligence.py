import sqlite3
import json
import hashlib
import time
import math
import logging
from typing import Dict, Any, Optional, List, Tuple
from psycopg.rows import dict_row

from src.db.connection import get_db_connection
import ollama

logger = logging.getLogger(__name__)

class QueryTemplateStore:
    def __init__(self, db_path: str = "query_memory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    database_id TEXT NOT NULL,
                    schema_hash TEXT NOT NULL,
                    original_prompt TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    generated_sql TEXT NOT NULL,
                    execution_count INTEGER DEFAULT 1,
                    last_used_at REAL,
                    created_at REAL
                )
            """)
            conn.commit()

    def get_embedding(self, text: str) -> List[float]:
        try:
            response = ollama.embeddings(model="nomic-embed-text", prompt=text)
            return response["embedding"]
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return []

    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot_product = sum(a * b for a, b in zip(v1, v2))
        magnitude1 = math.sqrt(sum(a * a for a in v1))
        magnitude2 = math.sqrt(sum(a * a for a in v2))
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        return dot_product / (magnitude1 * magnitude2)

    def store_query(self, database_id: str, schema_hash: str, original_prompt: str, generated_sql: str):
        embedding = self.get_embedding(original_prompt)
        if not embedding:
            logger.warning("No embedding generated, skipping query cache.")
            return

        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO query_memory 
                (database_id, schema_hash, original_prompt, embedding, generated_sql, last_used_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (database_id, schema_hash, original_prompt, json.dumps(embedding), generated_sql, now, now))
            conn.commit()

    def search_similar_query(self, database_id: str, prompt: str, schema_hash: str, threshold: float = 0.85) -> Optional[str]:
        prompt_embedding = self.get_embedding(prompt)
        if not prompt_embedding:
            return None

        best_match_sql = None
        best_similarity = 0.0
        best_match_id = None

        with sqlite3.connect(self.db_path) as conn:
            # We only look for queries from the same DB and same schema hash to ensure safety
            cursor = conn.execute("""
                SELECT id, embedding, generated_sql 
                FROM query_memory 
                WHERE database_id = ? AND schema_hash = ?
            """, (database_id, schema_hash))
            
            for row in cursor:
                row_id, emb_json, sql = row
                stored_embedding = json.loads(emb_json)
                
                similarity = self._cosine_similarity(prompt_embedding, stored_embedding)
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_sql = sql
                    best_match_id = row_id

            if best_similarity >= threshold and best_match_id is not None:
                logger.info(f"Cache hit with similarity {best_similarity:.2f}")
                # Update usage stats
                conn.execute("""
                    UPDATE query_memory 
                    SET execution_count = execution_count + 1, last_used_at = ? 
                    WHERE id = ?
                """, (time.time(), best_match_id))
                conn.commit()
                return best_match_sql
                
        return None

class SchemaManager:
    def __init__(self):
        self._cached_schema_text: Optional[str] = None
        self._cached_schema_hash: Optional[str] = None
        self._cached_database_id: Optional[str] = None
        self._last_refresh: float = 0
        self.ttl_seconds = 300 # 5 minutes cache

    async def get_database_id(self) -> str:
        if self._cached_database_id:
            return self._cached_database_id
            
        try:
            async with get_db_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT current_database();")
                    db_name = (await cur.fetchone())[0]
                    self._cached_database_id = db_name
                    return db_name
        except Exception as e:
            logger.error(f"Failed to get database ID: {e}")
            return "unknown_db"

    async def fetch_schema(self, force_refresh: bool = False) -> Tuple[str, str]:
        """Returns the schema text and its hash. Uses cache if valid."""
        now = time.time()
        if not force_refresh and self._cached_schema_text and self._cached_schema_hash:
            if (now - self._last_refresh) < self.ttl_seconds:
                return self._cached_schema_text, self._cached_schema_hash

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
                        self._cached_schema_text = "No tables found in the public schema."
                        self._cached_schema_hash = hashlib.md5(b"empty").hexdigest()
                        self._last_refresh = now
                        return self._cached_schema_text, self._cached_schema_hash

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
                    
                    self._cached_schema_text = output
                    self._cached_schema_hash = hashlib.md5(output.encode('utf-8')).hexdigest()
                    self._last_refresh = now
                    
                    return self._cached_schema_text, self._cached_schema_hash
                    
        except Exception as e:
            logger.error(f"Failed to fetch schema: {e}")
            return f"Database error: {e}", ""

# Global singletons
query_store = QueryTemplateStore()
schema_manager = SchemaManager()
