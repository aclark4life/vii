"""Tree-sitter based syntax highlighting for vii.

This module provides fast syntax highlighting using tree-sitter parsers.
Falls back to Pygments for unsupported languages.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text

if TYPE_CHECKING:
    pass

# Map file extensions to tree-sitter language names
EXTENSION_TO_LANGUAGE = {
    # Python
    ".py": "python",
    ".pyw": "python",
    ".pyi": "python",
    # JavaScript/TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".mjs": "javascript",
    ".cjs": "javascript",
    # Web
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".json": "json",
    # Systems
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".rs": "rust",
    ".go": "go",
    # Shell
    ".sh": "bash",
    ".bash": "bash",
    # Config
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    # Other
    ".rb": "ruby",
    ".java": "java",
    ".lua": "lua",
    ".php": "php",
    ".sql": "sql",
    ".md": "markdown",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".R": "r",
}

# Map tree-sitter node types to Rich styles (based on common themes)
# These work well with both dark and light themes
NODE_STYLES = {
    # Keywords (tree-sitter uses the actual keyword text as the type)
    "def": "bold magenta",
    "class": "bold magenta",
    "if": "bold magenta",
    "else": "bold magenta",
    "elif": "bold magenta",
    "for": "bold magenta",
    "while": "bold magenta",
    "return": "bold magenta",
    "import": "bold magenta",
    "from": "bold magenta",
    "as": "bold magenta",
    "with": "bold magenta",
    "try": "bold magenta",
    "except": "bold magenta",
    "finally": "bold magenta",
    "raise": "bold magenta",
    "pass": "bold magenta",
    "break": "bold magenta",
    "continue": "bold magenta",
    "in": "bold magenta",
    "not": "bold magenta",
    "and": "bold magenta",
    "or": "bold magenta",
    "is": "bold magenta",
    "lambda": "bold magenta",
    "yield": "bold magenta",
    "async": "bold magenta",
    "await": "bold magenta",
    "assert": "bold magenta",
    "global": "bold magenta",
    "nonlocal": "bold magenta",
    "del": "bold magenta",
    # JavaScript/TypeScript keywords
    "const": "bold magenta",
    "let": "bold magenta",
    "var": "bold magenta",
    "function": "bold magenta",
    "export": "bold magenta",
    "default": "bold magenta",
    "switch": "bold magenta",
    "case": "bold magenta",
    "typeof": "bold magenta",
    "instanceof": "bold magenta",
    "new": "bold magenta",
    "this": "bold magenta",
    "throw": "bold magenta",
    "catch": "bold magenta",
    # Rust keywords
    "fn": "bold magenta",
    "pub": "bold magenta",
    "mod": "bold magenta",
    "use": "bold magenta",
    "impl": "bold magenta",
    "trait": "bold magenta",
    "struct": "bold magenta",
    "enum": "bold magenta",
    "match": "bold magenta",
    "mut": "bold magenta",
    "ref": "bold magenta",
    "self": "bold magenta",
    "Self": "bold magenta",
    "where": "bold magenta",
    # Go keywords
    "func": "bold magenta",
    "package": "bold magenta",
    "type": "bold magenta",
    "interface": "bold magenta",
    "range": "bold magenta",
    "go": "bold magenta",
    "defer": "bold magenta",
    "select": "bold magenta",
    "chan": "bold magenta",
    # Types
    "type_identifier": "bold cyan",
    "primitive_type": "bold cyan",
    # Literals
    "string": "green",
    "string_content": "green",
    "string_fragment": "green",
    "escape_sequence": "bold green",
    "integer": "yellow",
    "float": "yellow",
    "number": "yellow",
    "true": "bold yellow",
    "false": "bold yellow",
    "True": "bold yellow",
    "False": "bold yellow",
    "None": "bold yellow",
    "null": "bold yellow",
    "nil": "bold yellow",
    # Comments
    "comment": "dim italic",
    "line_comment": "dim italic",
    "block_comment": "dim italic",
    # Decorators
    "decorator": "bold yellow",
    "@": "bold yellow",
}


def get_language_for_file(path: Path) -> str | None:
    """Get the tree-sitter language name for a file."""
    suffix = path.suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix)


def highlight_with_tree_sitter(
    content: str,
    language: str,
    line_numbers: bool = True,
) -> Text | None:
    """Highlight code using tree-sitter.

    Returns a Rich Text object with syntax highlighting, or None if parsing fails.
    """
    try:
        from tree_sitter_languages import get_parser
    except ImportError:
        return None

    try:
        parser = get_parser(language)
    except Exception:
        return None  # Language not supported

    # Parse the code
    try:
        tree = parser.parse(bytes(content, "utf8"))
    except Exception:
        return None

    # Collect ALL highlights in a single tree traversal
    highlights: list[tuple[int, int, str]] = []  # (byte_start, byte_end, style)
    _collect_all_highlights(tree.root_node, content, highlights)

    # Sort highlights by position
    highlights.sort(key=lambda x: x[0])

    # Convert byte positions to character positions
    content_bytes = content.encode("utf8")
    char_highlights = []
    for byte_start, byte_end, style in highlights:
        byte_start = min(byte_start, len(content_bytes))
        byte_end = min(byte_end, len(content_bytes))
        char_start = len(content_bytes[:byte_start].decode("utf8", errors="replace"))
        char_end = len(content_bytes[:byte_end].decode("utf8", errors="replace"))
        char_highlights.append((char_start, char_end, style))

    # Build text with line numbers
    text = Text()
    lines = content.split("\n")
    line_num_width = len(str(len(lines))) + 1 if line_numbers else 0

    # Create a style map for each character position
    # This is more efficient than checking ranges for each char
    style_map: list[str | None] = [None] * len(content)
    for char_start, char_end, style in char_highlights:
        for i in range(char_start, min(char_end, len(content))):
            if style_map[i] is None:  # First style wins
                style_map[i] = style

    # Build the output efficiently using chunks
    current_line = 0
    if line_numbers:
        text.append(f"{1:>{line_num_width}} │ ", style="dim")

    # Group consecutive characters with the same style
    i = 0
    while i < len(content):
        char = content[i]
        if char == "\n":
            text.append("\n")
            current_line += 1
            if line_numbers and i < len(content) - 1:
                text.append(f"{current_line + 1:>{line_num_width}} │ ", style="dim")
            i += 1
        else:
            # Find run of characters with same style (not including newlines)
            style = style_map[i]
            j = i + 1
            while j < len(content) and content[j] != "\n" and style_map[j] == style:
                j += 1
            text.append(content[i:j], style=style)
            i = j

    return text


# Node types that should highlight their entire span (not just leaves)
WHOLE_NODE_TYPES = {"string", "comment", "line_comment", "block_comment"}


def _collect_all_highlights(node, content: str, highlights: list[tuple[int, int, str]]) -> None:
    """Collect all highlights from the tree in a single traversal."""
    style = NODE_STYLES.get(node.type)

    if style and (node.child_count == 0 or node.type in WHOLE_NODE_TYPES):
        highlights.append((node.start_byte, node.end_byte, style))
        if node.type in WHOLE_NODE_TYPES:
            return  # Don't recurse into children

    for child in node.children:
        _collect_all_highlights(child, content, highlights)
