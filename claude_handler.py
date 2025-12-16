"""
Claude API integration - generates file changes based on prompts
"""
import os
import json
import logging
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Initialize with explicit API key from environment
api_key = os.getenv("CLAUDE_API_KEY")
if not api_key:
    raise ValueError("CLAUDE_API_KEY not found in environment variables")
client = Anthropic(api_key=api_key)

async def get_file_changes(prompt: str, website_context: str) -> dict:
    """
    Send prompt to Claude and get file changes
    Returns: dict with list of file changes
    """
    
    system_prompt = """You are an expert web developer helping students modify the Programming Party website.

The website is built with 11ty (Eleventy) and includes:
- HTML/Nunjucks templates in src/pages/ (MUST use this directory)
- CSS styling in src/assets/css/style.css
- JSON data files in src/_data/
- Configuration in .eleventy.js

IMPORTANT: Page files (*.md, *.njk) MUST go in src/pages/, NOT in src/ root!
Examples:
- ✓ CORRECT: src/pages/about.md
- ✗ WRONG: src/about.md

When a student makes a request, you should:
1. Analyze the request carefully
2. Identify which files need to be changed
3. Return ONLY valid changes in JSON format with correct paths
4. Maintain the existing code style and structure
5. Include relevant comments for clarity
6. ALWAYS put pages/templates in src/pages/ directory

CRITICAL: Return your response ONLY as a valid JSON object:
- Escape ALL newlines as \\n (not actual line breaks)
- Escape ALL backslashes as \\\\
- Escape ALL quotes as \\"
- No markdown, no code blocks, no explanations

Example format:
{
  "files": [
    {"path": "src/assets/css/style.css", "content": "body {\\n  color: red;\\n}"},
    {"path": "src/pages/about.md", "content": "# About\\nContent here"}
  ]
}"""

    user_prompt = f"""Here is the current state of the Programming Party website:

{website_context}

---

Student request: {prompt}

Please analyze this request and provide the file changes needed to implement it. Return the complete new content for any files that need to be modified."""

    try:
        response = client.messages.create(
            model="claude-opus-4.5",
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # Extract JSON from response
        response_text = response.content[0].text.strip()
        
        # Try to parse as JSON
        if response_text.startswith("```"):
            # Remove markdown code blocks if present
            response_text = response_text.replace("```json", "").replace("```", "").strip()
        
        try:
            file_changes = json.loads(response_text)
        except json.JSONDecodeError:
            # If standard parsing fails, try fixing common issues
            # Replace actual newlines with \\n in the content strings
            import re
            # This is a hacky fix but necessary for Claude's output
            response_text = re.sub(r'(?<!\\)"content":\s*"', '"content": "', response_text)
            file_changes = json.loads(response_text)
        
        logger.info(f"Claude generated changes for {len(file_changes.get('files', []))} files")
        return file_changes
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        logger.error(f"Response was: {response_text[:500]}")
        return None
    except Exception as e:
        logger.error(f"Error calling Claude: {e}")
        return None
