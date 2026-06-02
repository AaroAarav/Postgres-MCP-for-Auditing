import asyncio
import os
import json
import re
import ollama
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load environment variables from the .env file
load_dotenv()

async def run_dba_agent(user_prompt: str):
    print(f"🤖 User Request: {user_prompt}\n")
    
    # Guard against missing DATABASE_URL
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ Error: DATABASE_URL not found in environment or .env file.")
        return
    
    # Define how to connect to our local development MCP server
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "src/main.py", "--db", db_url],
        env=os.environ.copy()
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 1. Fetch available tools dynamically from pg-auditor
            tools_response = await session.list_tools()
            ollama_tools = []
            available_tool_names = set()
            
            for tool in tools_response.tools:
                available_tool_names.add(tool.name)
                ollama_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    }
                })

            # 2. Pre-fetch Only Saved Queries (Remove massive schema to save tokens)
            saved_queries_res = await session.call_tool("list_saved_queries", {})
            saved_queries_text = saved_queries_res.content[0].text if saved_queries_res.content else "No saved queries"

            # 3. Maintain conversational state
            sys_prompt = f"""You are an autonomous PostgreSQL Database Administrator. You have access to tools to diagnose and manage the database.

### INITIAL CONTEXT ###
Currently Saved Queries (These are NOT tools. To use them, you MUST call the `run_saved_query` tool and pass the name as the `query_name` parameter):
{saved_queries_text}
### END CONTEXT ###

CRITICAL RULES:
1. OVERRIDE: Even if the user asks you to "write a custom query", if their request matches any of the 'Currently Saved Queries', you MUST IGNORE their request to write a new one and immediately call `run_saved_query`. NEVER generate new SQL if it is already saved.
2. If the user's request requires querying data, you MUST call the `smart_query` tool FIRST. This tool will search for previously executed, semantically similar queries to save tokens.
3. If `smart_query` returns a Cache Hit and successfully executes, you are done. Stop calling tools and provide the final response.
4. If `smart_query` returns a Cache Miss, you MUST call the `get_database_schema` tool FIRST to learn the structure of the database. Do NOT guess column names (especially for JSONB fields like `parameters` in `mcp_audit_log`).
5. After retrieving the schema, write a custom query using `execute_dynamic_query`. You MUST provide the original `user_prompt`, a descriptive `query_name`, and `query_description`.
6. If a tool returns an "ACTION BLOCKED" message instructing you to use `run_saved_query`, you MUST call `run_saved_query` and NEVER attempt to call `execute_dynamic_query` again.
7. CRITICAL: Once you receive tabular data from ANY tool (like `run_saved_query` or `execute_dynamic_query`), you are completely DONE gathering data. You MUST IMMEDIATELY STOP calling tools and output your final plain-text response to the user. Do not call any more tools.
"""
            messages = [
                {
                    'role': 'system', 
                    'content': sys_prompt
                },
                {'role': 'user', 'content': user_prompt}
            ]
            client = ollama.AsyncClient(host="http://127.0.0.1:11434")
            
            total_in_tokens = 0
            total_out_tokens = 0
            max_turns = 15  # Prevent infinite loops if the model gets stuck
            
            for turn in range(max_turns):
                print(f"🧠 Thinking (Turn {turn + 1})...")
                
                response = await client.chat(
                    model='qwen2.5-coder:7b',
                    messages=messages,
                    tools=ollama_tools,
                )
                
                # Accumulate token usage metrics
                total_in_tokens += response.get('prompt_eval_count', 0)
                total_out_tokens += response.get('eval_count', 0)
                
                # Append the assistant's thinking/response to history
                messages.append(response.message)
                
                # Check for Native Tool Calls
                tool_calls = response.message.tool_calls or []
                
                # Fallback: Parse Markdown JSON if 3B parameter model outputs text instead of structured tools
                if not tool_calls and response.message.content:
                    # Look for ALL valid JSON objects wrapped in markdown code blocks
                    json_blocks = re.findall(r'```(?:json)?\s*(\{.*?\})\s*```', response.message.content, re.DOTALL)
                    
                    # If no markdown blocks, try a rough non-greedy match (which might fail on nested braces, but is a fallback)
                    if not json_blocks:
                        json_blocks = re.findall(r'(\{[\s\S]*?"(?:name|function)"\s*:\s*"[^"]+"[\s\S]*?\})', response.message.content)

                    for block in json_blocks:
                        try:
                            # Fix potentially truncated nested braces from rough regex
                            if block.count('{') > block.count('}'):
                                block += '}' * (block.count('{') - block.count('}'))
                            
                            parsed_tool = json.loads(block)
                            tool_name_extracted = parsed_tool.get("name") or parsed_tool.get("function")
                            if tool_name_extracted in available_tool_names:
                                # Standardize into a pseudo-tool call structure
                                class PseudoToolCall:
                                    def __init__(self, name, args):
                                        self.function = type('Sub', (object,), {
                                            "name": name,
                                            "arguments": args
                                        })()
                                tool_calls.append(PseudoToolCall(tool_name_extracted, parsed_tool.get("arguments", {})))
                        except Exception:
                            pass

                # If no tools were called, the agent has reached its final conclusion
                if not tool_calls:
                    print(f"💬 Agent Response:\n{response.message.content}\n")
                    break
                
                # 3. Execute any detected tool calls
                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = tool_call.function.arguments
                    
                    print(f"🛠️  Executing Tool: {tool_name}")
                    print(f"📋 Parameters: {tool_args}")
                    
                    # Call the tool on the local pg-auditor server
                    try:
                        result = await session.call_tool(tool_name, tool_args)
                        result_text = result.content[0].text
                        print(f"✅ Result: {result_text}\n")
                    except Exception as e:
                        result_text = f"Error executing tool: {str(e)}"
                        print(f"❌ {result_text}\n")
                    
                    # Feed the execution result back to the model's conversation history
                    messages.append({
                        'role': 'tool',
                        'name': tool_name,
                        'content': result_text
                    })
            
            # 4. Final step: Log the total aggregated token usage to PostgreSQL
            # 4. Final step: Log the total aggregated token usage to PostgreSQL
            if total_in_tokens > 0 or total_out_tokens > 0:
                try:
                    result = await session.call_tool(
                        "log_llm_usage", 
                        {
                            "prompt_tokens": total_in_tokens,
                            "completion_tokens": total_out_tokens,
                            "cost_usd": 0.0,
                            "task_description": user_prompt[:50]
                        }
                    )
                    # ADD THIS LINE to see what the server actually says:
                    print(f"Server Log Response: {result.content[0].text}")
                    
                except Exception as e:
                    print(f"⚠️ Warning: MCP Client crashed: {e}")

                    
if __name__ == "__main__":
    import sys
    # Fix for Windows async issues
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    prompt = "Check the database for slow queries."
    asyncio.run(run_dba_agent(input("Prompt: ")))