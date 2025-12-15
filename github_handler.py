"""
GitHub/Git operations - apply changes and commit to repo
"""
import os
import logging
from git import Repo
from git.exc import GitCommandError

logger = logging.getLogger(__name__)

repo = None

def init_repo():
    """Initialize or clone the repository"""
    global repo
    
    repo_path = os.getenv("REPO_LOCAL_PATH", "./website_repo")
    github_token = os.getenv("GITHUB_TOKEN")
    github_owner = os.getenv("GITHUB_REPO_OWNER")
    github_name = os.getenv("GITHUB_REPO_NAME")
    
    if not all([github_token, github_owner, github_name]):
        raise ValueError("Missing GitHub configuration")
    
    # Clone repo if it doesn't exist
    if not os.path.exists(repo_path):
        logger.info(f"Cloning repository to {repo_path}")
        repo_url = f"https://x-access-token:{github_token}@github.com/{github_owner}/{github_name}.git"
        repo = Repo.clone_from(repo_url, repo_path)
    else:
        repo = Repo(repo_path)
        # Pull latest
        try:
            repo.remotes.origin.pull()
            logger.info("Pulled latest changes from origin")
        except GitCommandError as e:
            logger.warning(f"Could not pull: {e}")
    
    # Configure git user
    config_reader = repo.config_reader()
    if not config_reader.has_option("user", "email"):
        repo.config_writer().set_value("user", "email", os.getenv("GITHUB_USER_EMAIL", "bot@programmingparty.plu.edu")).release()
        repo.config_writer().set_value("user", "name", os.getenv("GITHUB_USER_NAME", "Programming Party Bot")).release()

def apply_changes_and_commit(file_changes: dict, prompt: str) -> str:
    """
    Apply file changes and commit to the repository
    Returns: commit hash
    """
    global repo
    
    if not repo:
        raise RuntimeError("Repository not initialized")
    
    try:
        # Pull latest to avoid conflicts
        repo.remotes.origin.pull()
        logger.info("Pulled latest changes before applying modifications")
        
        # Apply each file change
        files_modified = []
        for file_change in file_changes.get("files", []):
            file_path = file_change.get("path")
            content = file_change.get("content")
            
            if not file_path or content is None:
                logger.warning(f"Invalid file change: {file_change}")
                continue
            
            full_path = os.path.join(repo.working_dir, file_path)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Write file
            with open(full_path, "w") as f:
                f.write(content)
            
            # Stage file
            repo.index.add([file_path])
            files_modified.append(file_path)
            logger.info(f"Modified: {file_path}")
        
        if not files_modified:
            raise ValueError("No files were modified")
        
        # Commit changes
        commit_message = f"Student request: {prompt}"
        commit = repo.index.commit(commit_message)
        logger.info(f"Committed changes: {commit.hexsha[:7]}")
        
        # Push to main
        origin = repo.remote("origin")
        github_token = os.getenv("GITHUB_TOKEN")
        github_owner = os.getenv("GITHUB_REPO_OWNER")
        github_name = os.getenv("GITHUB_REPO_NAME")
        
        try:
            # Try standard push first
            origin.push()
        except GitCommandError:
            # If standard push fails, use git command directly with token in URL
            if github_token:
                repo_url = f"https://x-access-token:{github_token}@github.com/{github_owner}/{github_name}.git"
                repo.git.push(repo_url, "HEAD:main")
            else:
                raise
        
        logger.info("Pushed changes to origin/main")
        
        return commit.hexsha
        
    except GitCommandError as e:
        logger.error(f"Git error: {e}")
        raise Exception(f"Failed to commit changes: {e}")
    except Exception as e:
        logger.error(f"Error applying changes: {e}")
        raise

def rollback_commit(commit_hash: str) -> bool:
    """
    Rollback a specific commit
    """
    global repo
    
    if not repo:
        raise RuntimeError("Repository not initialized")
    
    try:
        repo.git.revert(commit_hash, no_edit=True)
        repo.remotes.origin.push()
        logger.info(f"Rolled back commit {commit_hash}")
        return True
    except Exception as e:
        logger.error(f"Failed to rollback: {e}")
        return False
