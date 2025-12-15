"""
Load website context for Claude to understand the project structure
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def get_website_context() -> str:
    """
    Load the website repository structure and key files for Claude context
    Returns a string with the full context
    """
    repo_path = os.getenv("REPO_LOCAL_PATH", "./website_repo")
    
    if not os.path.exists(repo_path):
        return "Website repository not found. Initialize with init_repo() first."
    
    context = "# Website Repository Structure\n\n"
    
    # Add directory structure
    context += "## Project Structure\n\n"
    context += "```\n"
    context += _get_tree_structure(repo_path, max_depth=3)
    context += "\n```\n\n"
    
    # Add key configuration files
    key_files = [
        ".eleventy.js",
        "package.json",
        "src/_data/projects.json",
        "src/_data/people.json",
        "src/assets/css/style.css",
        "src/index.njk",
        "src/projects.njk",
        "src/people.njk",
        "src/about.md"
    ]
    
    context += "## Key Files Content\n\n"
    
    for file_rel_path in key_files:
        file_path = os.path.join(repo_path, file_rel_path)
        if os.path.exists(file_path):
            context += f"### {file_rel_path}\n\n"
            try:
                with open(file_path, "r") as f:
                    content = f.read()
                    if len(content) > 2000:
                        content = content[:2000] + "\n... (truncated)"
                    context += f"```\n{content}\n```\n\n"
            except Exception as e:
                logger.warning(f"Could not read {file_rel_path}: {e}")
                context += f"(Could not read file)\n\n"
        else:
            context += f"### {file_rel_path}\n\n(File not found)\n\n"
    
    # Add information about what can be modified
    context += "\n## Modification Guidelines\n\n"
    context += "- You can modify any file in the `src/` directory\n"
    context += "- CSS changes go in `src/assets/css/style.css`\n"
    context += "- Template files: `src/index.njk`, `src/projects.njk`, `src/people.njk`, `src/about.md`\n"
    context += "- Data files: `src/_data/projects.json`, `src/_data/people.json`\n"
    context += "- The site is built with Eleventy (11ty) static site generator\n"
    context += "- Changes are automatically deployed via GitHub Actions\n"
    
    return context

def _get_tree_structure(path: str, prefix: str = "", max_depth: int = 3, current_depth: int = 0) -> str:
    """
    Generate a tree structure representation of the directory
    """
    if current_depth >= max_depth:
        return ""
    
    tree = ""
    
    try:
        items = sorted(os.listdir(path))
        # Filter out node_modules and hidden directories
        items = [i for i in items if not i.startswith('.') and i != "node_modules" and i != "_site"]
        
        for i, item in enumerate(items):
            item_path = os.path.join(path, item)
            is_last = i == len(items) - 1
            current_prefix = "└── " if is_last else "├── "
            tree += f"{prefix}{current_prefix}{item}\n"
            
            if os.path.isdir(item_path) and current_depth < max_depth - 1:
                next_prefix = prefix + ("    " if is_last else "│   ")
                tree += _get_tree_structure(item_path, next_prefix, max_depth, current_depth + 1)
    
    except PermissionError:
        tree += f"{prefix}(Permission denied)\n"
    
    return tree
