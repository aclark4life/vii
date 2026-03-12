"""Git utilities for vii."""

import subprocess
from pathlib import Path


def is_git_repo(path: Path) -> bool:
    """Check if the given path is inside a git repository.
    
    Args:
        path: Path to check
        
    Returns:
        True if path is in a git repository, False otherwise
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=1,
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_git_branch(path: Path) -> str | None:
    """Get the current git branch for the given path.
    
    Args:
        path: Path inside a git repository
        
    Returns:
        Branch name if in a git repo, None otherwise
    """
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=1,
            text=True,
        )
        branch = result.stdout.strip()
        return branch if branch else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_git_status_summary(path: Path) -> dict[str, int]:
    """Get a summary of git status (modified, added, deleted files).

    Args:
        path: Path inside a git repository

    Returns:
        Dictionary with counts of modified, added, deleted, untracked files
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=2,
            text=True,
        )

        status = {
            "modified": 0,
            "added": 0,
            "deleted": 0,
            "untracked": 0,
        }

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Git status --porcelain format: XY filename
            # X = index status, Y = working tree status
            if len(line) >= 2:
                index_status = line[0]
                work_status = line[1]

                # Check both index and working tree status
                if "?" in (index_status, work_status):
                    status["untracked"] += 1
                elif "A" in (index_status, work_status):
                    status["added"] += 1
                elif "D" in (index_status, work_status):
                    status["deleted"] += 1
                elif "M" in (index_status, work_status):
                    status["modified"] += 1

        return status
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {"modified": 0, "added": 0, "deleted": 0, "untracked": 0}


def get_git_file_status(path: Path) -> dict[str, str]:
    """Get git status for individual files.

    Args:
        path: Path inside a git repository

    Returns:
        Dictionary mapping file paths to their git status codes
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=2,
            text=True,
        )

        file_status = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            if len(line) >= 3:
                status_code = line[:2]
                filename = line[3:].strip()
                # Remove quotes if present
                if filename.startswith('"') and filename.endswith('"'):
                    filename = filename[1:-1]
                file_status[filename] = status_code

        return file_status
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {}


def get_git_diff(path: Path, file_path: str) -> str | None:
    """Get git diff for a specific file.

    Args:
        path: Path inside a git repository
        file_path: Relative path to the file

    Returns:
        Diff output as string, or None if error
    """
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD", file_path],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=3,
            text=True,
        )
        return result.stdout if result.stdout else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None

