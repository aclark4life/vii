"""Git state management for the vii application.

This module provides a centralized GitState dataclass that encapsulates
all git-related state, making it easier to manage and reason about.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple


class GitLogEntry(NamedTuple):
    """Represents a single git log entry with structured data.

    This structure uses machine-readable data from git log
    to avoid brittle parsing of formatted output.
    """

    hash: str  # Full commit hash
    short_hash: str  # Abbreviated hash (7 chars)
    author: str  # Author name
    date: str  # Date string
    message: str  # Commit message (first line)
    start_line: int  # Start line in display output
    end_line: int  # End line in display output


@dataclass
class GitState:
    """Encapsulates all git-related state for the application.

    This class centralizes git state that was previously scattered across
    the main Vii class, improving cohesion and maintainability.
    """

    # Repository info
    root: Path | None = None
    branch: str | None = None
    status: dict[str, int] = field(default_factory=dict)
    file_status: dict[str, str] = field(default_factory=dict)

    # Log state
    log_viewing: bool = False
    log_output: str = ""  # Pretty formatted display output
    log_entries: list[GitLogEntry] = field(default_factory=list)  # Structured entry data
    log_highlighted_entry: int = -1
    log_page: int = 0
    log_page_size: int = 50
    log_search_query: str = ""
    log_search_matches: list[int] = field(default_factory=list)
    log_current_match_index: int = -1

    # Commit viewing
    commit_viewing: bool = False
    commit_hash: str = ""

    # Blame state
    blame_viewing: bool = False
    blame_output: str = ""
    blame_highlighted_line: int = -1
    blame_file_path: Path | None = None
    blame_search_query: str = ""
    blame_search_matches: list[int] = field(default_factory=list)
    blame_current_match_index: int = -1

    def reset_log(self) -> None:
        """Reset log viewing state to default values."""
        self.log_viewing = False
        self.log_output = ""
        self.log_entries = []
        self.log_highlighted_entry = -1
        self.log_page = 0
        self.log_search_query = ""
        self.log_search_matches = []
        self.log_current_match_index = -1
        self.commit_viewing = False
        self.commit_hash = ""

    def reset_blame(self) -> None:
        """Reset blame viewing state to default values."""
        self.blame_viewing = False
        self.blame_output = ""
        self.blame_highlighted_line = -1
        self.blame_file_path = None
        self.blame_search_query = ""
        self.blame_search_matches = []
        self.blame_current_match_index = -1

    def reset_repository_info(self) -> None:
        """Reset repository information to default values."""
        self.root = None
        self.branch = None
        self.status = {}
        self.file_status = {}

    def is_in_repo(self) -> bool:
        """Check if currently in a git repository."""
        return self.branch is not None and self.root is not None
