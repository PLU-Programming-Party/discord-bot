import re
import json

def extract_json_from_response_v2(response_text):
    """
    Extract JSON from Claude response with better handling of escaped content
    """
    
    # Strategy 1: Try markdown code fences first
    json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    
    # Strategy 2: Find JSON with regex pattern that's more robust
    # Look for complete JSON objects
    json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
    matches = list(re.finditer(json_pattern, response_text, re.DOTALL))
    
    if matches:
        # Try each match to find valid JSON
        for match in reversed(matches):  # Start from the last/largest match
            try:
                candidate = match.group(0)
                json.loads(candidate)  # Validate it's proper JSON
                return candidate
            except json.JSONDecodeError:
                continue
    
    # Strategy 3: Simpler approach - find first { and try to parse progressively
    json_start = response_text.find('{')
    if json_start != -1:
        # Try progressively longer substrings until one parses
        for end_pos in range(len(response_text), json_start, -1):
            candidate = response_text[json_start:end_pos]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    
    return response_text.strip()

# Test with the broken response
test_response = """{
  "files": [
    {
      "path": "src/pages/index.md",
      "content": "---\\nlayout: base\\ntitle: Home\\npermalink: /\\n---\\n\\n<div class=\\"welcome-section\\">\\n    <div class=\\"welcome-content\\">\\n        <div class=\\"welcome-image\\">\\n            <img src=\\"https://www.plu.edu/computer-science/wp-content/uploads/sites/551/2020/03/jeff-caley.jpg\\" alt=\\"Dr. Caley\\" class=\\"caley-photo\\">\\n            <div class=\\"speech-bubble\\">Welcome to the party! 🎉</div>\\n        </div>\\n    </div>\\n</div>"
    }
  ]
}"""

result = extract_json_from_response_v2(test_response)
print("Extracted:", result[:100])
try:
    parsed = json.loads(result)
    print("JSON is valid!")
except Exception as e:
    print("JSON parse error:", e)
