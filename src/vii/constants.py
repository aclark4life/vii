"""Constants and configuration values for the vii application.

This module centralizes magic numbers and configuration constants
to improve maintainability and make tuning easier.
"""

# ==============================================================================
# SUBPROCESS TIMEOUTS (seconds)
# ==============================================================================

# Quick operations (checking status, getting metadata)
TIMEOUT_QUICK = 1  # For: which, git rev-parse, git branch --show-current

# Standard git operations (local operations)
TIMEOUT_STANDARD = 2  # For: git status, git blame (short)

# Medium operations (diffs, log queries)
TIMEOUT_MEDIUM = 5  # For: git diff, git log, git show, git checkout, git add

# Network operations (push/pull)
TIMEOUT_NETWORK = 60  # For: git push, git pull

# Interactive operations (editor, commit message)
TIMEOUT_INTERACTIVE = 300  # For: git commit (opens editor)

# Long-running operations (complex git operations)
TIMEOUT_LONG = 10  # For: git show with large patches


# ==============================================================================
# FILE READING AND CACHING
# ==============================================================================

# Maximum file size to read (bytes) - prevents loading huge files
FILE_MAX_SIZE = 100_000  # 100 KB

# Maximum lines to read from a file - prevents excessive rendering
FILE_MAX_LINES = 2000

# LRU cache size for rendered file content
RENDERED_CACHE_MAX_SIZE = 30

# Image preview maximum dimensions
IMAGE_PREVIEW_MAX_WIDTH = 80
IMAGE_PREVIEW_MAX_HEIGHT = 40


# ==============================================================================
# GIT LOG PAGINATION
# ==============================================================================

# Number of commits to show per page in git log
GIT_LOG_PAGE_SIZE = 50


# ==============================================================================
# UI CONSTANTS
# ==============================================================================

# Default sidebar width in columns
DEFAULT_SIDEBAR_WIDTH = 40

# Minimum sidebar width to prevent it becoming unusable
MIN_SIDEBAR_WIDTH = 20

# Maximum sidebar width as percentage of screen
MAX_SIDEBAR_WIDTH_PERCENT = 80


# ==============================================================================
# SEARCH CONSTANTS
# ==============================================================================

# Context lines to show around search matches
SEARCH_CONTEXT_LINES = 3


# ==============================================================================
# SYNTAX HIGHLIGHTING
# ==============================================================================

# Default theme for syntax highlighting
DEFAULT_SYNTAX_THEME = "monokai"

# Fallback themes to try if default unavailable
FALLBACK_SYNTAX_THEMES = ["default", "emacs", "vim"]
