"""
Claude API integration - generates file changes based on prompts
"""
import os
import json
import logging
import re
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Initialize with explicit API key from environment
api_key = os.getenv("CLAUDE_API_KEY")
if not api_key:
    raise ValueError("CLAUDE_API_KEY not found in environment variables")
client = Anthropic(api_key=api_key)

def extract_json_from_response(response_text):
    """
    Extract JSON from Claude response with robust handling of escaped content.
    Uses multiple strategies to find and validate JSON blocks.
    """
    
    # Strategy 1: Try markdown code fences first
    json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    
    # Strategy 2: Use regex to find potential JSON objects
    # This pattern finds balanced braces but isn't perfect for nested structures
    json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
    matches = list(re.finditer(json_pattern, response_text, re.DOTALL))
    
    if matches:
        # Try each match in reverse (largest/last first) to find valid JSON
        for match in reversed(matches):
            try:
                candidate = match.group(0)
                json.loads(candidate)  # Validate it parses correctly
                return candidate
            except json.JSONDecodeError:
                continue
    
    # Strategy 3: Find first { and progressively extend until valid JSON is found
    json_start = response_text.find('{')
    if json_start != -1:
        # Try longer and longer substrings starting from the end
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
    Ask clarifying questions to understand the user's requirements.
    Returns: dict with questions asked and whether more info is needed
    """
    
    if conversation_history is None:
        conversation_history = []
    
    system_prompt = """You are an expert web developer helping students modify the Programming Party website.
Your job is to ask clarifying questions about the requested changes to ensure you understand exactly what needs to be done.

IMPORTANT: You are in the REQUIREMENTS GATHERING phase. Your goal is to ask questions, NOT to make assumptions.

The website is built with 11ty (Eleventy) with:
- Layout templates in src/_layouts/
- Page files in src/pages/
- CSS styling in src/assets/css/style.css

When a student makes a request, you should:
1. Identify what is unclear or ambiguous
2. Ask specific, targeted questions to clarify
3. Ask about:
   - Specific file locations or page names if not mentioned
   - Visual styling details (colors, sizes, positioning)
   - Content specifics (exact text, formatting)
   - Which files are affected
   - User expectations for the result
4. Be concise - ask 2-3 focused questions, not a wall of text
5. Only after you have clarity, indicate you're ready to implement

Return your response as JSON:
{
  "questions": ["Question 1?", "Question 2?"],
  "ready_to_implement": false,
  "summary": "What I understand so far..."
}

If you feel you have enough information to proceed:
{
  "questions": [],
  "ready_to_implement": true,
  "summary": "Complete understanding of what needs to be done"
}"""

    messages = conversation_history.copy()
    
    if not messages:
        # First message from user
        messages.append({"role": "user", "content": f"""Here is the current state of the website:

{website_context}

---

Student request: {prompt}

Ask clarifying questions to understand exactly what changes are needed. Do NOT make assumptions."""})
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=messages
        )
        
        response_text = response.content[0].text.strip()
        json_text = extract_json_from_response(response_text)
        requirements = json.loads(json_text)
        
        logger.info(f"Gathering requirements - Ready: {requirements.get('ready_to_implement', False)}")
        return requirements
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse requirements response as JSON: {e}")
        logger.error(f"Response was: {response_text[:500]}")
        return {
            "questions": ["I need clarification - can you provide more specific details about your request?"],
            "ready_to_implement": False,
            "summary": "Unable to understand request"
        }
    except Exception as e:
        logger.error(f"Error gathering requirements: {e}")
        return {
            "questions": ["I encountered an error. Can you rephrase your request?"],
            "ready_to_implement": False,
            "summary": "Error occurred"
        }

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
   - Return ONLY the JSON block, no explanations or markdown code blocks

When a student makes a request, you should:
1. Read the complete file contents provided
2. Understand what changes are needed
3. Return the COMPLETE modified file with ALL original content preserved
4. Be conservative - make minimal changes to achieve the request"""

    user_prompt = f"""Here is the current state of the Programming Party website:

{website_context}

---

Student request: {prompt}

Please analyze this request and provide the file changes needed to implement it. Return ONLY the JSON object with file changes - no explanations, no markdown code blocks."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # Extract text from response
        response_text = response.content[0].text.strip()
        
        # Extract JSON from response (handles multiple formats)
        json_text = extract_json_from_response(response_text)
        
        # Parse JSON
        file_changes = json.loads(json_text)
        
        logger.info(f"Claude generated changes for {len(file_changes.get('files', []))} files")
        return file_changes
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Claude response as JSON: {e}")
        logger.error(f"Response was: {response_text[:500]}")
        return None
    except Exception as e:
        logger.error(f"Error calling Claude: {e}")
        return None
