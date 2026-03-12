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


def get_git_blame_line(path: Path, file_path: str, line_number: int) -> dict[str, str] | None:
    """Get git blame information for a specific line.

    Args:
        path: Path inside a git repository
        file_path: Relative path to the file
        line_number: Line number (1-based)

    Returns:
        Dictionary with blame info (commit, author, date, message) or None if error
    """
    try:
        # Use porcelain format for easier parsing
        result = subprocess.run(
            ["git", "blame", "--porcelain", "-L", f"{line_number},{line_number}", file_path],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=2,
            text=True,
        )

        if not result.stdout:
            return None

        # Parse porcelain format
        lines = result.stdout.strip().split("\n")
        if not lines:
            return None

        # First line: commit hash
        commit_hash = lines[0].split()[0]

        blame_info = {
            "commit": commit_hash[:8],  # Short hash
            "author": "",
            "date": "",
            "message": "",
        }

        for line in lines:
            if line.startswith("author "):
                blame_info["author"] = line[7:]
            elif line.startswith("author-time "):
                # Convert timestamp to readable date
                import datetime

                timestamp = int(line[12:])
                date = datetime.datetime.fromtimestamp(timestamp)
                blame_info["date"] = date.strftime("%Y-%m-%d")
            elif line.startswith("summary "):
                blame_info["message"] = line[8:]

        return blame_info
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_git_blame_file(path: Path, file_path: str) -> str | None:
    """Get git blame for an entire file.

    Args:
        path: Path inside a git repository
        file_path: Relative path to the file

    Returns:
        Blame output as string, or None if error
    """
    try:
        result = subprocess.run(
            ["git", "blame", "--date=short", file_path],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=5,
            text=True,
        )
        return result.stdout if result.stdout else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_git_branches(path: Path) -> dict[str, list[str]] | None:
    """Get list of local and remote git branches.

    Args:
        path: Path inside a git repository

    Returns:
        Dictionary with 'local' and 'remote' branch lists, or None if error
    """
    try:
        # Get local branches
        result = subprocess.run(
            ["git", "branch", "--format=%(refname:short)"],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=3,
            text=True,
        )
        local_branches = [b.strip() for b in result.stdout.strip().split("\n") if b.strip()]

        # Get remote branches
        result = subprocess.run(
            ["git", "branch", "-r", "--format=%(refname:short)"],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=3,
            text=True,
        )
        remote_branches = [
            b.strip()
            for b in result.stdout.strip().split("\n")
            if b.strip() and not b.strip().endswith("/HEAD")
        ]

        return {
            "local": local_branches,
            "remote": remote_branches,
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def git_checkout_branch(path: Path, branch_name: str) -> tuple[bool, str]:
    """Checkout a git branch.

    Args:
        path: Path inside a git repository
        branch_name: Name of the branch to checkout

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        subprocess.run(
            ["git", "checkout", branch_name],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=5,
            text=True,
        )
        return (True, f"Switched to branch '{branch_name}'")
    except subprocess.CalledProcessError as e:
        return (False, e.stderr.strip() if e.stderr else "Failed to checkout branch")
    except subprocess.TimeoutExpired:
        return (False, "Git checkout timed out")
    except FileNotFoundError:
        return (False, "Git command not found")


def git_checkout_remote_branch(path: Path, remote_branch: str) -> tuple[bool, str]:
    """Checkout a remote branch (creates local tracking branch).

    Args:
        path: Path inside a git repository
        remote_branch: Name of the remote branch (e.g., 'origin/feature-branch')

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Extract local branch name from remote branch
        # e.g., 'origin/feature-branch' -> 'feature-branch'
        if "/" in remote_branch:
            local_branch = remote_branch.split("/", 1)[1]
        else:
            return (False, "Invalid remote branch format")

        # Checkout and create tracking branch
        subprocess.run(
            ["git", "checkout", "-b", local_branch, remote_branch],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=5,
            text=True,
        )
        return (True, f"Created and switched to branch '{local_branch}' tracking '{remote_branch}'")
    except subprocess.CalledProcessError as e:
        # If branch already exists locally, just checkout
        if "already exists" in (e.stderr or ""):
            return git_checkout_branch(path, local_branch)
        return (False, e.stderr.strip() if e.stderr else "Failed to checkout remote branch")
    except subprocess.TimeoutExpired:
        return (False, "Git checkout timed out")
    except FileNotFoundError:
        return (False, "Git command not found")


def get_git_log(path: Path, max_count: int = 50, skip: int = 0) -> str | None:
    """Get git log with formatted output.

    Args:
        path: Path inside a git repository
        max_count: Maximum number of commits to show (default: 50)
        skip: Number of commits to skip (for pagination)

    Returns:
        Formatted git log output as string, or None if error
    """
    try:
        # Use a nice format with colors and graph
        format_str = "%C(yellow)%h%Creset %C(cyan)%ad%Creset %C(green)%an%Creset%n  %s%n"
        result = subprocess.run(
            [
                "git",
                "log",
                f"--max-count={max_count}",
                f"--skip={skip}",
                "--graph",
                f"--pretty=format:{format_str}",
                "--date=relative",
            ],
            cwd=str(path),
            capture_output=True,
            check=True,
            timeout=5,
            text=True,
        )
        return result.stdout if result.stdout else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
