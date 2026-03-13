"""File content loading and syntax highlighting for vii."""

from __future__ import annotations

from pathlib import Path


def read_file_content(path: Path, max_size: int = 100000, max_lines: int = 2000) -> str:
    """Read file content, handling binary files and size limits.

    Args:
        path: Path to the file to read
        max_size: Maximum file size in bytes (default 100KB)
        max_lines: Maximum number of lines to read (default 2000)

    Returns:
        The file content as a string, or an error message.
    """
    try:
        # Check file size first
        file_size = path.stat().st_size
        if file_size > max_size:
            return f"[dim]File too large to preview ({file_size:,} bytes)[/dim]"

        # Try to read as text
        content = path.read_text(encoding="utf-8")

        # Check line count - truncate if too many lines
        lines = content.split("\n")
        if len(lines) > max_lines:
            truncated = "\n".join(lines[:max_lines])
            # Add plain text truncation marker (will be styled in display)
            return f"{truncated}\n\n... truncated ({len(lines):,} total lines)"

        return content
    except UnicodeDecodeError:
        return "[dim]Binary file - cannot preview[/dim]"
    except PermissionError:
        return "[dim]Permission denied[/dim]"
    except Exception as e:
        return f"[dim]Cannot read file: {e}[/dim]"


# Map Textual themes to Pygments/Rich syntax themes
THEME_MAP = {
    # Dark themes
    "textual-dark": "github-dark",
    "atom-one-dark": "one-dark",
    "nord": "nord",
    "gruvbox": "gruvbox-dark",
    "tokyo-night": "material",
    "monokai": "monokai",
    "dracula": "dracula",
    "catppuccin-mocha": "native",
    "catppuccin-frappe": "native",
    "catppuccin-macchiato": "native",
    "flexoki": "zenburn",
    "textual-ansi": "native",
    "solarized-dark": "solarized-dark",
    "rose-pine": "zenburn",
    "rose-pine-moon": "zenburn",
    # Light themes
    "textual-light": "friendly",
    "atom-one-light": "friendly",
    "solarized-light": "solarized-light",
    "catppuccin-latte": "friendly",
    "rose-pine-dawn": "friendly",
}


def get_syntax_theme(app_theme: str, is_dark: bool = True) -> str:
    """Get the appropriate syntax highlighting theme based on the app theme.

    Args:
        app_theme: The current Textual theme name
        is_dark: Whether the theme is dark (fallback if theme not in map)

    Returns:
        A Pygments theme name.
    """
    if app_theme in THEME_MAP:
        return THEME_MAP[app_theme]
    return "one-dark" if is_dark else "friendly"


# Map file extensions to Pygments lexer names
EXTENSION_TO_LEXER = {
    # Python
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    # Shell
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    # Config files
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".ini": "ini",
    ".cfg": "ini",
    ".conf": "ini",
    # Markup
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "rst",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".css": "css",
    # JavaScript / TypeScript
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    # C family
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    # Other languages
    ".rs": "rust",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".php": "php",
    ".sql": "sql",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    # Data formats
    ".csv": "text",
    ".tsv": "text",
    # Misc
    ".dockerfile": "docker",
    ".makefile": "make",
    ".tex": "latex",
    ".vim": "vim",
}

# Map special filenames to lexers
FILENAME_TO_LEXER = {
    "Dockerfile": "docker",
    "Makefile": "make",
    "justfile": "make",
    "Justfile": "make",
    ".justfile": "make",
    "CMakeLists.txt": "cmake",
    ".bashrc": "bash",
    ".bash_profile": "bash",
    ".zshrc": "zsh",
    ".gitignore": "ini",
    ".editorconfig": "ini",
}


def get_syntax_lexer(path: Path) -> str | None:
    """Get the Pygments lexer name for a file based on extension or filename.

    Args:
        path: Path to the file

    Returns:
        A Pygments lexer name, or None if unknown.
    """
    if path.name in FILENAME_TO_LEXER:
        return FILENAME_TO_LEXER[path.name]

    suffix = path.suffix.lower()
    return EXTENSION_TO_LEXER.get(suffix)
