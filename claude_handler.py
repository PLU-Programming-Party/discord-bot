"""
Claude API integration with tool use - generates file changes based on prompts
"""
import os
import json
import asyncio
import logging
import re
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Initialize with explicit API key from environment
api_key = os.getenv("CLAUDE_API_KEY")
if not api_key:
    raise ValueError("CLAUDE_API_KEY not found in environment variables")
client = Anthropic(api_key=api_key)

# Use Opus for better reasoning
MODEL = "claude-opus-4-20250514"

# Define tools for Claude to use
TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file from the website repository. Use this to understand current file structure and content before making changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path relative to the repository root (e.g., 'src/pages/about.md', 'src/_layouts/base.njk')"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "list_directory",
        "description": "List files and directories in a given path. Use this to explore the project structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path relative to the repository root (e.g., 'src/pages', 'src/_layouts')"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write or modify a file in the website repository. Always provide the COMPLETE file content - partial updates are not supported.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path relative to the repository root"
                },
                "content": {
                    "type": "string",
                    "description": "The COMPLETE content to write to the file"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "ask_user",
        "description": "Ask the user a clarifying question when something is ambiguous. Only use this for genuine ambiguity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user"
                }
            },
            "required": ["question"]
        }
    },
    {
        "name": "complete",
        "description": "Signal that the task is complete. Use this when all changes have been written successfully.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "A brief summary of what was accomplished"
                },
                "files_changed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths that were modified"
                }
            },
            "required": ["summary", "files_changed"]
        }
    }
]

# Tool execution functions
def execute_read_file(repo_path: str, file_path: str) -> str:
    """Read a file from the repository"""
    full_path = os.path.join(repo_path, file_path)
    try:
        if not os.path.exists(full_path):
            return f"Error: File '{file_path}' does not exist"
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

def execute_list_directory(repo_path: str, dir_path: str) -> str:
    """List contents of a directory"""
    full_path = os.path.join(repo_path, dir_path) if dir_path else repo_path
    try:
        if not os.path.exists(full_path):
            return f"Error: Directory '{dir_path}' does not exist"
        entries = os.listdir(full_path)
        result = []
        for entry in sorted(entries):
            entry_path = os.path.join(full_path, entry)
            if os.path.isdir(entry_path):
                result.append(f"📁 {entry}/")
            else:
                result.append(f"📄 {entry}")
        return "\n".join(result) if result else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {str(e)}"

def execute_write_file(repo_path: str, file_path: str, content: str) -> str:
    """Write content to a file"""
    full_path = os.path.join(repo_path, file_path)
    try:
        # Create directories if needed
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Successfully wrote {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


class AgentSession:
    """Manages a multi-turn agent session with Claude"""
    
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.messages = []
        self.files_changed = []
        self.is_complete = False
        self.completion_summary = None
        self.pending_question = None
        self.max_iterations = 20  # Safety limit
        
    def get_system_prompt(self):
        return """You are an expert web developer helping students modify the Programming Party website.

The website is built with 11ty (Eleventy) and includes:
- Layout templates in src/_layouts/
- Page files in src/pages/
- CSS styling in src/assets/css/style.css

You have tools to explore the codebase and make changes. Use them to:
1. First understand the current state by reading relevant files
2. Plan your changes
3. Write the complete modified files
4. Signal completion when done

IMPORTANT RULES:
- Always read files before modifying them to understand current content
- When writing files, include the COMPLETE content - partial updates don't work
- Preserve existing functionality when making changes
- If something is ambiguous, ask the user ONE focused question
- Be efficient - don't read every file, just the relevant ones
- When modifying navigation, also update src/_layouts/base.njk

After making all changes, use the 'complete' tool to finish."""

    async def process_tool_call(self, tool_name: str, tool_input: dict) -> tuple[str, bool]:
        """
        Process a tool call and return (result, should_continue)
        Returns should_continue=False if we need to wait for user input or task is complete
        """
        logger.info(f"Tool call: {tool_name}")
        
        if tool_name == "read_file":
            result = execute_read_file(self.repo_path, tool_input["path"])
            return result, True
            
        elif tool_name == "list_directory":
            result = execute_list_directory(self.repo_path, tool_input.get("path", ""))
            return result, True
            
        elif tool_name == "write_file":
            result = execute_write_file(self.repo_path, tool_input["path"], tool_input["content"])
            if "Successfully wrote" in result:
                self.files_changed.append(tool_input["path"])
            return result, True
            
        elif tool_name == "ask_user":
            self.pending_question = tool_input["question"]
            return "Question sent to user. Waiting for response.", False
            
        elif tool_name == "complete":
            self.is_complete = True
            self.completion_summary = tool_input.get("summary", "Changes complete")
            return "Task marked as complete.", False
            
        else:
            return f"Unknown tool: {tool_name}", True

    async def run_agent_loop(self, initial_prompt: str = None):
        """
        Run the agent loop until completion, question, or max iterations
        Returns: (status, message)
        - ("complete", summary) - Task finished
        - ("question", question) - Need user input
        - ("error", message) - Something went wrong
        """
        
        # Add initial user message if provided
        if initial_prompt:
            self.messages.append({"role": "user", "content": initial_prompt})
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"Agent iteration {iteration}")
            
            try:
                # Call Claude with tools
                response = await asyncio.to_thread(
                    client.messages.create,
                    model=MODEL,
                    max_tokens=8192,
                    system=self.get_system_prompt(),
                    tools=TOOLS,
                    messages=self.messages
                )
                
                # Check stop reason
                if response.stop_reason == "end_turn":
                    # Claude finished without using tools - extract any text response
                    text_content = ""
                    for block in response.content:
                        if hasattr(block, 'text'):
                            text_content += block.text
                    
                    if self.files_changed:
                        return ("complete", f"Changes made to: {', '.join(self.files_changed)}")
                    else:
                        return ("complete", text_content or "Task completed (no files changed)")
                
                elif response.stop_reason == "tool_use":
                    # Process tool calls
                    assistant_content = response.content
                    self.messages.append({"role": "assistant", "content": assistant_content})
                    
                    tool_results = []
                    should_continue = True
                    
                    for block in assistant_content:
                        if block.type == "tool_use":
                            result, continue_loop = await self.process_tool_call(
                                block.name, 
                                block.input
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result
                            })
                            if not continue_loop:
                                should_continue = False
                    
                    # Add tool results to messages
                    self.messages.append({"role": "user", "content": tool_results})
                    
                    # Check if we need to pause
                    if self.is_complete:
                        return ("complete", self.completion_summary)
                    
                    if self.pending_question:
                        return ("question", self.pending_question)
                    
                    if not should_continue:
                        break
                        
                else:
                    logger.warning(f"Unexpected stop reason: {response.stop_reason}")
                    break
                    
            except Exception as e:
                logger.error(f"Error in agent loop: {e}")
                return ("error", str(e))
        
        return ("error", "Max iterations reached")

    def add_user_response(self, response: str):
        """Add a user's response to a question"""
        self.messages.append({"role": "user", "content": response})
        self.pending_question = None


# Legacy functions for compatibility (simplified wrappers)
def extract_json_from_response(response_text):
    """Extract JSON from Claude response - kept for compatibility"""
    json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    
    json_start = response_text.find('{')
    if json_start != -1:
        for end_pos in range(len(response_text), json_start, -1):
            candidate = response_text[json_start:end_pos]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    
    return response_text.strip()


async def gather_requirements(prompt: str, website_context: str, conversation_history: list = None) -> dict:
    """
    Legacy function - now just returns ready to implement since agent handles clarification
    """
    return {
        "questions": [],
        "ready_to_implement": True,
        "summary": prompt
    }


async def get_file_changes(prompt: str, website_context: str) -> dict:
    """
    Legacy function - kept for compatibility but agent-based approach is preferred
    """
    system_prompt = """You are an expert web developer. Return ONLY valid JSON with file changes.
    
Format:
{
  "files": [
    {"path": "src/pages/example.md", "content": "complete file content..."}
  ]
}"""

    try:
        response = await asyncio.to_thread(
            client.messages.create,
            model=MODEL,
            max_tokens=16384,
            system=system_prompt,
            messages=[{"role": "user", "content": f"{website_context}\n\n---\n\nRequest: {prompt}"}]
        )
        
        response_text = response.content[0].text.strip()
        json_text = extract_json_from_response(response_text)
        file_changes = json.loads(json_text)
        
        if isinstance(file_changes, dict) and 'path' in file_changes and 'content' in file_changes:
            file_changes = {'files': [file_changes]}
        
        logger.info(f"Claude generated changes for {len(file_changes.get('files', []))} files")
        return file_changes
        
    except Exception as e:
        logger.error(f"Error calling Claude: {e}")
        return None
