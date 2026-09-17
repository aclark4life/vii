"""File content loading and syntax highlighting for vii."""

from __future__ import annotations

from pathlib import Path

from .constants import FILE_MAX_LINES, FILE_MAX_SIZE

# Common image file extensions
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".ico",
    ".tiff",
    ".tif",
}


def is_image_file(path: Path) -> bool:
    """Check if a file is a supported image type.

    Args:
        path: Path to the file

    Returns:
        True if the file is a supported image type.
    """
    return path.suffix.lower() in IMAGE_EXTENSIONS


def render_image_preview(path: Path, size: int = 30) -> tuple[str, None] | tuple[None, str]:
    """Render an image file for terminal preview using Pillow.

    Renders the image as a grid of ANSI truecolor half-block ("▀") characters,
    using the foreground color for the top pixel and the background color for
    the bottom pixel of each terminal cell.

    Args:
        path: Path to the image file
        size: Fixed size in terminal columns (width)

    Returns:
        A tuple of (rendered string, None) on success, or (None, error_message) on failure.
    """
    try:
        from PIL import Image
    except ImportError:
        return None, "Missing dependency: Pillow"

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            orig_width, orig_height = img.size
            if orig_width == 0 or orig_height == 0:
                return None, "Invalid image dimensions"

            new_width = max(size, 1)
            # Terminal character cells are roughly twice as tall as wide, and we
            # pack two source rows into each cell (top/bottom half-block), so
            # the effective vertical scale factor is 0.5.
            new_height = max(int(orig_height / orig_width * new_width * 0.5), 1)
            # Round up to an even number of rows so each pair has a bottom pixel.
            if new_height % 2:
                new_height += 1

            img = img.resize((new_width, new_height))
            pixels = list(img.getdata())

            lines = []
            for y in range(0, new_height, 2):
                parts = []
                for x in range(new_width):
                    top = pixels[y * new_width + x]
                    bottom_index = (y + 1) * new_width + x
                    bottom = pixels[bottom_index] if bottom_index < len(pixels) else (0, 0, 0)
                    parts.append(
                        f"\x1b[38;2;{top[0]};{top[1]};{top[2]}m"
                        f"\x1b[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m\u2580"
                    )
                lines.append("".join(parts) + "\x1b[0m")

            return "\n".join(lines), None
    except FileNotFoundError:
        return None, f"File not found: {path}"
    except PermissionError:
        return None, f"Permission denied: {path}"
    except Exception as e:
        return None, f"Error: {e}"


def read_file_content(path: Path, max_size: int = FILE_MAX_SIZE, max_lines: int = FILE_MAX_LINES) -> str:
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
