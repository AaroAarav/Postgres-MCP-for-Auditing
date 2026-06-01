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

            # 2. Maintain conversational state
            messages = [
                {
                    'role': 'system', 
                    'content': 'You are an autonomous PostgreSQL Database Administrator. You have access to tools to diagnose and manage the database. You MUST use these tools to answer the user\'s request. After you have gathered enough information from the tools, you MUST ALWAYS provide a final, comprehensive response in natural language explaining your findings.'
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
                    model='qwen2.5-coder:3b',
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
                    # This new regex looks for ANY valid JSON object {} in the text, with or without markdown
                    json_match = re.search(r'(\{[\s\S]*"(?:name|function)"\s*:\s*"[^"]+"[\s\S]*\})', response.message.content)
                    if json_match:
                        try:
                            parsed_tool = json.loads(json_match.group(1))
                            tool_name_extracted = parsed_tool.get("name") or parsed_tool.get("function")
                            if tool_name_extracted in available_tool_names:
                                # Standardize into a pseudo-tool call structure
                                class PseudoToolCall:
                                    def __init__(self, name, args):
                                        self.function = type('Sub', (object,), {
                                            "name": name,
                                            "arguments": args
                                        })()
                                tool_calls = [PseudoToolCall(tool_name_extracted, parsed_tool.get("arguments", {}))]
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