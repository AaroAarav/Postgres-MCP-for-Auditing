import asyncio
import sys
import logging
import io

# Ensure tools can be imported
sys.path.append('.') 

# Import all tools
from src.tools.health import ping_database, active_sessions, cache_hit_rate, table_bloat_report, blocking_lock_tree
from src.tools.performance import slow_queries, high_variance_queries, queries_by_io, temp_spill_queries, query_regression_report, latency_percentiles
from src.tools.indexes import missing_index_candidates, unused_indexes, duplicate_indexes, bloated_indexes, unindexed_foreign_keys, index_usage_stats, index_health_summary
from src.tools.schema import get_database_schema
from src.tools.workflows import list_saved_queries, list_saved_workflows
from src.db.connection import init_pool, close_pool

logging.basicConfig(level=logging.ERROR)

async def test_tools():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    print("==================================================")
    print("🧪 AUTOMATED TOOL TESTING")
    print("==================================================\n")
    
    # Initialize connection pool
    await init_pool()
    try:
        # List of all parameter-less tools that can be safely run without specific arguments
        tools_to_test = [
            ("ping_database", ping_database),
            ("active_sessions", active_sessions),
            ("cache_hit_rate", cache_hit_rate),
            ("table_bloat_report", table_bloat_report),
            ("blocking_lock_tree", blocking_lock_tree),
            ("slow_queries", slow_queries),
            ("high_variance_queries", high_variance_queries),
            ("queries_by_io", queries_by_io),
            ("temp_spill_queries", temp_spill_queries),
            ("query_regression_report", query_regression_report),
            ("latency_percentiles", latency_percentiles),
            ("missing_index_candidates", missing_index_candidates),
            ("unused_indexes", unused_indexes),
            ("duplicate_indexes", duplicate_indexes),
            ("bloated_indexes", bloated_indexes),
            ("unindexed_foreign_keys", unindexed_foreign_keys),
            ("index_usage_stats", index_usage_stats),
            ("index_health_summary", index_health_summary),
            ("get_database_schema", get_database_schema),
            ("list_saved_queries", list_saved_queries),
            ("list_saved_workflows", list_saved_workflows)
        ]
        
        passed = 0
        failed = 0
        
        for name, func in tools_to_test:
            print(f"▶️ Testing: {name}()")
            try:
                result = await func()
                if isinstance(result, str) and "Database error:" in result:
                    print(f"   ❌ FAILED (Database Error): {result.strip()}")
                    failed += 1
                else:
                    print(f"   ✅ PASSED. Output length: {len(str(result))} chars")
                    passed += 1
            except Exception as e:
                print(f"   ❌ FAILED (Crash): {e}")
                failed += 1
    finally:
        await close_pool()
        
    print("\n==================================================")
    print(f"🎉 TEST SUMMARY: {passed} Passed, {failed} Failed")
    print("==================================================")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(test_tools())
