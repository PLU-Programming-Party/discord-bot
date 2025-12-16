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
- Layout templates in src/_layouts/
- Page files in src/pages/ (MUST use this directory, not src/ root!)
- CSS styling in src/assets/css/style.css
- Configuration in .eleventy.js

CRITICAL RULES - READ CAREFULLY:

1. **COMPLETE FILE CONTENT**: You will receive the COMPLETE content of each file below. When you modify a file, return the ENTIRE new content from start to finish. Do NOT truncate, summarize, or return only the changed lines. The entire content you return will be written exactly as-is to the file.

2. **File Paths**: 
   - Page files MUST be in src/pages/ (e.g., src/pages/about.md)
   - CSS MUST be at src/assets/css/style.css (do NOT split into multiple CSS files)
   - Layouts MUST be in src/_layouts/ (do NOT move them)

3. **Preservation**: When modifying a file, PRESERVE all existing content and functionality that isn't being changed. For example:
   - When modifying CSS, keep all existing classes and styles
   - When modifying HTML, keep all existing structure and elements
   - Do NOT remove sections or simplify code

4. **Return Format**: Return ONLY valid JSON with complete file contents:
{
  "files": [
    {
      "path": "src/assets/css/style.css",
      "content": "/* COMPLETE CSS from start to end including all existing styles */"
    },
    {
      "path": "src/pages/about.md",
      "content": "---\\nlayout: base\\n...\\nCOMPLETE FILE CONTENT"
    }
  ]
}

5. **String Formatting in JSON**:
   - Escape newlines as \\n (not actual line breaks)
   - Escape backslashes as \\\\
   - Escape quotes as \\"
   - No markdown code blocks, no explanations, JSON ONLY

When a student makes a request, you should:
1. Read the complete file contents provided
2. Understand what changes are needed
3. Return the COMPLETE modified file with ALL original content preserved
4. Be conservative - make minimal changes to achieve the request"""

    user_prompt = f"""Here is the current state of the Programming Party website:

{website_context}

---

Student request: {prompt}

Please analyze this request and provide the file changes needed to implement it. Return the complete new content for any files that need to be modified."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
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
