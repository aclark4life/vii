"""Main application entry point for vii."""

import os
import re
import subprocess
import sys
from pathlib import Path

from rich.console import Group
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import DirectoryTree, Footer, Header, Input, Static
from textual.worker import Worker, WorkerState

from vii.commands import ConfigCommandProvider, GitCommandProvider
from vii.config import Config
from vii.content import (
    get_syntax_lexer,
    get_syntax_theme,
    is_image_file,
    read_file_content,
    render_image_preview,
)
from vii.git_handlers import GitHandlersMixin
from vii.git_utils import (
    get_git_branch,
    get_git_file_status,
    get_git_root,
    get_git_status_summary,
    is_git_repo,
)
from vii.tree_sitter_highlight import get_language_for_file, highlight_with_tree_sitter
from vii.widgets import GitDirectoryTree, VerticalSplitter


class Vii(GitHandlersMixin, App):
    """vii - Terminal file browser."""

    TITLE = "🤖 vii"
    COMMANDS = App.COMMANDS | {ConfigCommandProvider, GitCommandProvider}

    # Reactive variable for sidebar width (in columns)
    sidebar_width: reactive[int] = reactive(30)
    # Note: sub_title is inherited from App and used by Header widget

    CSS = """
    Screen {
        layout: horizontal;
    }

    #sidebar {
        height: 100%;
    }

    #main-content {
        width: 1fr;
        height: 100%;
    }

    DirectoryTree {
        width: 100%;
        height: 100%;
        border: solid $panel;
    }

    DirectoryTree:focus {
        border: solid $accent;
    }

    .info-text {
        color: $text-muted;
        text-style: italic;
    }

    #content-scroll {
        width: 100%;
        height: 100%;
        border: solid $panel;
        overflow-x: auto;
    }

    #content-scroll:focus {
        border: solid $accent;
    }

    #content-display {
        padding: 1 2;
        width: auto;
    }

    #content-search-container {
        dock: bottom;
        height: auto;
        display: none;
    }

    #content-search-container.visible {
        display: block;
    }

    #sidebar-search-container {
        dock: bottom;
        height: auto;
        display: none;
    }

    #sidebar-search-container.visible {
        display: block;
    }

    .search-input {
        width: 100%;
    }

    .search-match {
        background: $warning;
        color: $text;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
        Binding("tab", "focus_next", "Tab", show=False),
        Binding("shift+tab", "focus_previous", "Shift+Tab", show=False),
        # Command palette
        Binding("ctrl+p", "command_palette", "palette"),
        # Vi-style navigation (shown in footer)
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("h", "cursor_left", "Collapse"),
        Binding("g", "scroll_home", "Top"),
        Binding("G", "scroll_end", "Bottom"),
        Binding("d", "page_down", "Page Down"),
        Binding("u", "page_up", "Page Up"),
        Binding("e", "edit_file", "Edit"),
        Binding("s", "open_shell", "Shell"),
        # Git bindings
        Binding("b", "git_blame", "Blame"),
        # Arrow keys still work but hidden from footer
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("left", "cursor_left", "Left", show=False),
        Binding("right", "cursor_right", "Right", show=False),
        # Page navigation for content panel
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
    ]

    def __init__(self, start_path: Path | None = None):
        super().__init__()
        # Register "random" as a theme option
        self._register_random_theme()
        # Load configuration (theme is applied in on_mount)
        self._config = Config.load()
        self.start_path = start_path or Path.cwd()
        self.editor_command = self._detect_editor()
        self.is_terminal_editor = self._is_terminal_editor()
        # Content search state
        self.search_query = ""
        self.search_matches: list[int] = []  # Line numbers with matches
        self.current_match_index = -1
        self.original_content = ""  # Content without highlighting
        # Sidebar search state
        self.sidebar_search_query = ""
        self.sidebar_search_matches: list = []  # Tree nodes with matches
        self.sidebar_current_match_index = -1
        # Git state
        self.git_root: Path | None = None
        self.git_branch: str | None = None
        self.git_status: dict[str, int] = {}
        self.git_file_status: dict[str, str] = {}
        # Git log pagination
        self.git_log_page: int = 0
        self.git_log_page_size: int = 50
        # Content update debounce timer
        self._content_update_timer = None
        # Cache for rendered file content (LRU-style, max 30 files)
        self._rendered_cache: dict[Path, tuple[str, object]] = {}
        self._cache_max_size = 30
        # Track currently displayed path to avoid redundant updates
        self._displayed_path: Path | None = None
        # Track directory listing entries for click handling (list of paths in display order)
        self._dir_listing_entries: list[Path] = []
        # Track highlighted entry in directory listing (-1 = none)
        self._dir_listing_highlighted: int = -1
        self.git_log_viewing: bool = False
        self.git_log_output: str = ""  # Store log output for re-rendering
        self.git_log_entries: list[
            tuple[int, int]
        ] = []  # List of (start_line, end_line) for each entry
        self.git_log_highlighted_entry: int = -1  # Currently highlighted entry index (-1 = none)
        self.git_commit_viewing: bool = False  # True when viewing a specific commit
        self.git_commit_hash: str = ""  # Currently viewed commit hash
        self.git_blame_viewing: bool = False
        self.git_blame_output: str = ""  # Store blame output for re-rendering
        self.git_blame_highlighted_line: int = -1  # Currently highlighted line (-1 = none)
        self._update_git_info()

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
    ) -> None:
        """Show a notification, limiting to 3 visible at a time.

        Removes oldest notifications to keep max 3 on screen.
        """
        from textual.widgets._toast import Toast

        # Find existing toasts and remove oldest if we have 3+
        toasts = list(self.screen.query(Toast))
        while len(toasts) >= 3:
            oldest = toasts.pop(0)
            oldest.remove()

        # Call parent notify
        super().notify(message, title=title, severity=severity, timeout=timeout)

    def set_sidebar_width(self, width: int, save: bool = True) -> None:
        """Set the sidebar width, with bounds checking.

        Args:
            width: The desired width in columns.
            save: Whether to save the width to config (default True).
        """
        # Get screen width and set minimum/maximum bounds
        screen_width = self.size.width
        min_width = 10
        max_width = screen_width - 15  # Leave at least 15 columns for content

        # Clamp width to bounds
        new_width = max(min_width, min(width, max_width))
        self.sidebar_width = new_width

        # Save to config
        if save:
            self._config.sidebar_width = new_width
            self._config.save()

    def watch_sidebar_width(self, width: int) -> None:
        """React to sidebar width changes."""
        try:
            # Find sidebar by iterating (query_one with type can return None)
            widgets = self.query("*")
            if widgets is not None:
                for widget in widgets:
                    if widget.id == "sidebar":
                        widget.styles.width = f"{width}"
                        return
        except Exception:
            pass
        # Fallback: use walk_children (works in Textual 8.x)
        try:
            for widget in self.walk_children():
                if widget.id == "sidebar":
                    widget.styles.width = f"{width}"
                    return
        except Exception:
            pass  # Widget may not be mounted yet

    def _get_tree(self) -> DirectoryTree | None:
        """Get the directory tree widget (query_one with type can return None)."""
        try:
            # Try query_one first (works in some Textual versions)
            result = self.query_one(DirectoryTree)
            if result is not None:
                return result
        except Exception:
            pass
        try:
            # Fallback: iterate widgets
            widgets = self.query("*")
            if widgets is not None:
                for widget in widgets:
                    if isinstance(widget, DirectoryTree):
                        return widget
        except Exception:
            pass
        # Fallback: use walk_children (works in Textual 8.x)
        try:
            for widget in self.walk_children():
                if isinstance(widget, DirectoryTree):
                    return widget
        except Exception:
            pass
        return None

    def _get_scroll_container(self) -> ScrollableContainer | None:
        """Get the content scroll container widget."""
        try:
            result = self.query_one("#content-scroll", ScrollableContainer)
            if result is not None:
                return result
        except Exception:
            pass
        try:
            widgets = self.query("*")
            if widgets is not None:
                for widget in widgets:
                    if widget.id == "content-scroll":
                        return widget
        except Exception:
            pass
        # Fallback: use walk_children (works in Textual 8.x)
        try:
            for widget in self.walk_children():
                if widget.id == "content-scroll":
                    return widget
        except Exception:
            pass
        return None

    def _get_content_display(self) -> Static | None:
        """Get the content display widget."""
        try:
            result = self.query_one("#content-display", Static)
            if result is not None:
                return result
        except Exception:
            pass
        try:
            widgets = self.query("*")
            if widgets is not None:
                for widget in widgets:
                    if widget.id == "content-display":
                        return widget
        except Exception:
            pass
        # Fallback: use walk_children (works in Textual 8.x)
        try:
            for widget in self.walk_children():
                if widget.id == "content-display":
                    return widget
        except Exception:
            pass
        return None

    def _detect_editor(self) -> list[str]:
        """Detect the user's preferred editor."""
        # Check common environment variables
        editor = None
        for env_var in ["VISUAL", "EDITOR"]:
            editor = os.environ.get(env_var)
            if editor:
                break

        if not editor:
            # Try common GUI editors first, then terminal editors
            for cmd in ["code", "subl", "atom", "vim", "nvim", "nano"]:
                try:
                    subprocess.run(
                        ["which", cmd],
                        capture_output=True,
                        check=True,
                    )
                    editor = cmd
                    break
                except subprocess.CalledProcessError:
                    continue

        return [editor] if editor else ["open"]

    def _is_terminal_editor(self) -> bool:
        """Check if the detected editor is a terminal-based editor."""
        if not self.editor_command:
            return False

        terminal_editors = {
            "vim",
            "nvim",
            "vi",
            "nano",
            "emacs",
            "micro",
            "helix",
            "hx",
            "joe",
            "ne",
            "ed",
            "ex",
        }

        editor_name = Path(self.editor_command[0]).name
        return editor_name in terminal_editors

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()

        with Vertical(id="sidebar"):
            tree = GitDirectoryTree(str(self.start_path))
            tree.git_file_status = self.git_file_status
            yield tree
            with Horizontal(id="sidebar-search-container"):
                yield Input(
                    placeholder="Search files...",
                    id="sidebar-search-input",
                    classes="search-input",
                )

        yield VerticalSplitter(id="splitter")

        with Vertical(id="main-content"):
            with ScrollableContainer(id="content-scroll", can_focus=True):
                yield Static(
                    "📁 Navigate with j/k to see folder/file icons\n\n"
                    "Press Tab to switch focus between panels.\n"
                    "Use Page Up/Down or mouse wheel to scroll content.\n"
                    "Press / to search in file content.\n"
                    "Drag the splitter to resize panels.",
                    id="content-display",
                )
            with Horizontal(id="content-search-container"):
                yield Input(
                    placeholder="Search in file...",
                    id="content-search-input",
                    classes="search-input",
                )

        yield Footer()

    def on_mount(self) -> None:
        """Set initial sidebar width when app mounts."""
        # Subscribe to theme changes first
        self.theme_changed_signal.subscribe(self, self._on_theme_changed)

        # Apply saved theme (must be done after mount for Textual to apply it)
        if self._config.theme == "random":
            self._apply_random_theme()
        elif self._config.theme:
            self.theme = self._config.theme

        # Use saved sidebar width or default to 1/3 of screen
        if self._config.sidebar_width is not None:
            initial_width = self._config.sidebar_width
        else:
            initial_width = max(20, self.size.width // 3)
        self.sidebar_width = initial_width

        # Update header with git info
        self._update_header()

    def _get_current_directory(self) -> Path:
        """Get the current directory based on the tree cursor position."""
        try:
            tree = self._get_tree()
            if tree and tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                # If it's a file, get its parent directory
                if path.is_file():
                    return path.parent
                # If it's a directory, use it
                return path
        except Exception:
            pass
        # Fallback to start path
        return self.start_path

    def _update_git_info(self, path: Path | None = None) -> None:
        """Update git repository information for the current directory.

        Args:
            path: Optional path to check. If None, uses current directory from tree cursor.
        """
        if path is None:
            path = self._get_current_directory()

        if is_git_repo(path):
            # Get and store the git root
            self.git_root = get_git_root(path)
            self.git_branch = get_git_branch(path)
            self.git_status = get_git_status_summary(path)
            self.git_file_status = get_git_file_status(path)

            # Update the tree's git status
            try:
                tree = self.query_one(GitDirectoryTree)
                tree.git_file_status = self.git_file_status
                tree.refresh()
            except Exception:
                pass  # Tree may not be mounted yet
        else:
            self.git_root = None
            self.git_branch = None
            self.git_status = {}
            self.git_file_status = {}

        # Update the header to reflect new git info
        self._update_header()

    def _update_header(self) -> None:
        """Update the header with current git information."""
        if self.git_branch:
            # Build status indicators using emojis/symbols
            status_parts = []
            if self.git_status.get("modified", 0) > 0:
                status_parts.append(f"~{self.git_status['modified']}")
            if self.git_status.get("added", 0) > 0:
                status_parts.append(f"+{self.git_status['added']}")
            if self.git_status.get("deleted", 0) > 0:
                status_parts.append(f"-{self.git_status['deleted']}")
            if self.git_status.get("untracked", 0) > 0:
                status_parts.append(f"?{self.git_status['untracked']}")

            status_str = " ".join(status_parts) if status_parts else "✓"
            self.sub_title = f"📂 {self.start_path} 🌿 {self.git_branch} {status_str}"
        else:
            self.sub_title = f"📂 {self.start_path}"

    def _register_random_theme(self) -> None:
        """Register a 'random' pseudo-theme in the theme list."""
        from textual.theme import Theme

        # Create a placeholder theme - it won't actually be used
        # because we intercept it in _on_theme_changed
        random_theme = Theme(
            name="random",
            primary="#888888",
            dark=True,
        )
        self.register_theme(random_theme)

    def _on_theme_changed(self, theme: object) -> None:
        """React to theme changes by updating the content display.

        Args:
            theme: The new Theme object (from theme_changed_signal).
        """
        # If "random" was selected from theme picker, apply a random real theme
        if self.theme == "random":
            self._apply_random_theme()
            # Save "random" to config so it picks a new theme on each startup
            self._config.theme = "random"
            self._config.save()
            return

        # Don't overwrite config if it's set to "random" (we're just applying a random theme)
        if self._config.theme != "random":
            self._config.theme = self.theme
            self._config.save()

        # Re-render the content with the new syntax theme
        self._update_content_display()

    def _navigate_to_directory(self, directory: Path) -> None:
        """Navigate to a different directory by reloading the tree."""
        try:
            # Remove the old tree
            old_tree = self._get_tree()
            if old_tree:
                old_tree.remove()

            # Update the start path
            self.start_path = directory

            # Update git info and header
            self._update_git_info()
            self._update_header()

            # Create and mount a new tree with the new directory
            sidebar = self.query_one("#sidebar", Vertical)
            new_tree = GitDirectoryTree(str(directory))
            new_tree.git_file_status = self.git_file_status
            sidebar.mount(new_tree, before=0)  # Mount at the beginning
            new_tree.focus()

            # Update content display
            self.call_after_refresh(self._update_content_display)
        except Exception as e:
            self.notify(f"Cannot navigate to directory: {e}", severity="error")

    def _reload_tree(self) -> None:
        """Reload the directory tree to reflect file system changes."""
        try:
            # Save the current cursor position and expanded nodes
            old_tree = self._get_tree()
            if not old_tree:
                return
            cursor_path = None
            if old_tree.cursor_node and old_tree.cursor_node.data:
                cursor_path = old_tree.cursor_node.data.path

            # Collect all expanded node paths
            expanded_paths = set()

            def collect_expanded(node):
                """Recursively collect expanded node paths."""
                if node.is_expanded and node.data and hasattr(node.data, "path"):
                    expanded_paths.add(node.data.path)
                for child in node.children:
                    collect_expanded(child)

            collect_expanded(old_tree.root)

            # Also ensure all parent directories of cursor are in expanded_paths
            if cursor_path:
                current = cursor_path.parent
                while current != self.start_path and current != current.parent:
                    expanded_paths.add(current)
                    current = current.parent

            # Remove the old tree
            old_tree.remove()

            # Create and mount a new tree with the same directory
            sidebar = self.query_one("#sidebar", Vertical)
            new_tree = GitDirectoryTree(str(self.start_path))
            new_tree.git_file_status = self.git_file_status
            sidebar.mount(new_tree, before=0)  # Mount at the beginning

            # Restore expanded state and cursor position
            def restore_tree_state():
                """Restore the expanded nodes and cursor position."""

                # Build path from root to cursor
                path_to_cursor = []
                if cursor_path:
                    current = cursor_path
                    while current != self.start_path and current != current.parent:
                        path_to_cursor.insert(0, current)
                        current = current.parent

                # Index to track which path we're expanding
                expand_index = [0]

                def expand_next_level():
                    """Expand the next level in the path to cursor."""
                    if expand_index[0] >= len(path_to_cursor):
                        # Done expanding path to cursor, now restore other expanded nodes
                        restore_other_expanded()
                        return

                    target_path = path_to_cursor[expand_index[0]]

                    # Find and expand this node
                    def find_and_expand(node):
                        if node.data and hasattr(node.data, "path"):
                            if node.data.path == target_path:
                                if not node.is_expanded and node.allow_expand:
                                    node.expand()
                                return True
                        for child in node.children:
                            if find_and_expand(child):
                                return True
                        return False

                    if find_and_expand(new_tree.root):
                        expand_index[0] += 1
                        # Schedule next expansion with a small delay to allow children to load
                        self.set_timer(0.05, expand_next_level)
                    else:
                        # Node not found, skip to next
                        expand_index[0] += 1
                        self.set_timer(0.05, expand_next_level)

                def restore_other_expanded():
                    """Restore other expanded nodes and move cursor."""
                    # Expand other previously expanded nodes
                    sorted_paths = sorted(expanded_paths, key=lambda p: len(p.parts))

                    def find_node_by_path(target_path):
                        """Find a node by its path."""

                        def search(node):
                            if node.data and hasattr(node.data, "path"):
                                if node.data.path == target_path:
                                    return node
                            for child in node.children:
                                result = search(child)
                                if result:
                                    return result
                            return None

                        return search(new_tree.root)

                    for path_to_expand in sorted_paths:
                        # Skip paths already in the cursor path
                        if path_to_expand in path_to_cursor:
                            continue
                        node = find_node_by_path(path_to_expand)
                        if node and not node.is_expanded and node.allow_expand:
                            node.expand()

                    # Finally, move cursor to the saved position
                    if cursor_path:
                        cursor_node = find_node_by_path(cursor_path)
                        if cursor_node:
                            new_tree.move_cursor(cursor_node)
                            new_tree.scroll_to_node(cursor_node)

                    new_tree.focus()
                    self._update_content_display()

                # Start the expansion process
                if path_to_cursor:
                    expand_next_level()
                else:
                    restore_other_expanded()

            # Call after refresh to ensure tree is fully loaded
            self.call_after_refresh(restore_tree_state)

        except Exception as e:
            self.notify(f"Cannot reload tree: {e}", severity="error")

    def _schedule_content_update(self) -> None:
        """Schedule a debounced content update.

        Uses a single timer to minimize overhead during rapid navigation.
        Content only loads after user stops for 100ms.
        """
        # Cancel any pending timer
        if self._content_update_timer is not None:
            self._content_update_timer.stop()
            self._content_update_timer = None

        # Single timer - load content after navigation stops
        self._content_update_timer = self.set_timer(0.1, self._do_content_update)

    def _render_directory_listing(self, path: Path, highlight_index: int = -1) -> Text:
        """Render a directory listing for display in the content panel.

        Args:
            path: Path to the directory to list.
            highlight_index: Index of entry to highlight (-1 for none).

        Returns:
            Rich Text object with formatted directory listing.
        """
        # Get terminal width to pad highlighted lines
        scroll_container = self._get_scroll_container()
        width = max(scroll_container.size.width - 4, 80) if scroll_container else 80

        text = Text()
        text.append(f"📁 {path.name}/\n\n", style="bold")

        # Clear directory listing entries for click handling
        self._dir_listing_entries = []

        try:
            # Get directory contents
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))

            if not entries:
                text.append("(empty directory)", style="dim")
                return text

            # Separate directories and files
            dirs = [e for e in entries if e.is_dir() and not e.name.startswith(".")]
            files = [e for e in entries if e.is_file() and not e.name.startswith(".")]
            hidden = [e for e in entries if e.name.startswith(".")]

            entry_index = 0

            # List directories first
            for d in dirs:
                status_indicator = self._get_git_status_indicator(d)
                line_content = f"{status_indicator}📁 {d.name}/"

                if entry_index == highlight_index:
                    # Highlighted entry - pad to full width
                    padded_line = line_content.ljust(width)
                    text.append(padded_line + "\n", style="reverse")
                else:
                    text.append(status_indicator)
                    text.append("📁 ", style="bold")
                    text.append(f"{d.name}/\n", style="cyan")

                self._dir_listing_entries.append(d)
                entry_index += 1

            # Then files
            for f in files:
                status_indicator = self._get_git_status_indicator(f)
                line_content = f"{status_indicator}📄 {f.name}"

                if entry_index == highlight_index:
                    # Highlighted entry - pad to full width
                    padded_line = line_content.ljust(width)
                    text.append(padded_line + "\n", style="reverse")
                else:
                    text.append(status_indicator)
                    text.append("📄 ")
                    text.append(f"{f.name}\n")

                self._dir_listing_entries.append(f)
                entry_index += 1

            # Summary of hidden files
            if hidden:
                text.append(f"\n({len(hidden)} hidden items)", style="dim")

            # Add navigation footer if there are entries
            if self._dir_listing_entries:
                text.append("\n")
                text.append("Navigation: ", style="dim")
                text.append("j/k", style="bold cyan")
                text.append(" = Up/Down  ", style="dim")
                text.append("Enter", style="bold cyan")
                text.append(" = Open  ", style="dim")
                text.append("ESC", style="bold cyan")
                text.append(" = Back to sidebar", style="dim")

        except PermissionError:
            text.append("(permission denied)", style="red")
        except Exception as e:
            text.append(f"(error: {e})", style="red")

        return text

    def _render_dir_listing_with_highlight(self) -> None:
        """Re-render the directory listing with the current highlight."""
        if not self._displayed_path or not self._displayed_path.is_dir():
            return

        content_display = self._get_content_display()
        if content_display:
            content_display.update(
                self._render_directory_listing(self._displayed_path, self._dir_listing_highlighted)
            )

    def _scroll_to_dir_entry(self) -> None:
        """Scroll to keep the highlighted directory entry visible."""
        if self._dir_listing_highlighted < 0 or not self._dir_listing_entries:
            return

        scroll_container = self._get_scroll_container()
        if not scroll_container:
            return

        # Add 2 for the header lines (title + empty line)
        target_y = self._dir_listing_highlighted + 2

        # Scroll to keep target visible
        visible_height = scroll_container.size.height
        current_scroll = scroll_container.scroll_y

        if target_y < current_scroll:
            scroll_container.scroll_to(y=target_y, animate=False)
        elif target_y >= current_scroll + visible_height - 1:
            scroll_container.scroll_to(y=target_y - visible_height + 2, animate=False)

    def _get_git_status_indicator(self, path: Path) -> str:
        """Get git status indicator for a path.

        Args:
            path: Path to check.

        Returns:
            Status indicator string (e.g., "~ " for modified).
        """
        try:
            rel_path = str(path.relative_to(self.start_path))
            if rel_path in self.git_file_status:
                status_code = self.git_file_status[rel_path]
                if "M" in status_code:
                    return "~ "
                elif "A" in status_code:
                    return "+ "
                elif "D" in status_code:
                    return "- "
                elif "?" in status_code:
                    return "? "
        except (ValueError, AttributeError):
            pass
        return "  "

    def _do_content_update(self) -> None:
        """Load and display content after navigation stops (100ms debounce)."""
        self._content_update_timer = None

        # Reset search state
        self.search_matches = []
        self.current_match_index = -1
        self.git_log_viewing = False
        self.git_log_output = ""
        self.git_log_entries = []
        self.git_log_highlighted_entry = -1
        self.git_commit_viewing = False
        self.git_commit_hash = ""
        self.git_blame_viewing = False
        self.git_log_page = 0

        try:
            tree = self._get_tree()
            if not tree or not tree.cursor_node or not tree.cursor_node.data:
                return

            path = tree.cursor_node.data.path

            # Check if we've entered a different git repo (or left one)
            current_dir = path.parent if path.is_file() else path
            new_git_root = get_git_root(current_dir)
            if new_git_root != self.git_root:
                # Git repo changed - update git info
                self._update_git_info(current_dir)

            # Skip if already displaying this path
            if path == self._displayed_path:
                return

            content_display = self._get_content_display()
            scroll_container = self._get_scroll_container()
            if not content_display or not scroll_container:
                return

            if path.is_dir():
                self._dir_listing_highlighted = 0 if path.iterdir() else -1
                content_display.update(
                    self._render_directory_listing(path, self._dir_listing_highlighted)
                )
                self.original_content = ""
                self._displayed_path = path
                scroll_container.scroll_home(animate=False)
                return

            # Use cached content if available (includes syntax highlighting)
            if path in self._rendered_cache:
                content, rendered = self._rendered_cache[path]
                self.original_content = content
                if rendered:
                    content_display.update(rendered)
                else:
                    content_display.update(f"[bold]📄 {path.name}[/bold]\n\n{content}")
                scroll_container.scroll_home(animate=False)
                self._displayed_path = path
                return

            # Not cached - start background worker for syntax highlighting
            # Worker will update display when done
            self._load_file_content(path)
        except Exception:
            pass

    @work(exclusive=True, thread=True)
    def _load_file_content(self, path: Path) -> dict:
        """Load file content in a background thread. Returns data for the UI to display.

        This does all the expensive work (file I/O, syntax highlighting) off the main thread.
        """
        # Check if this is an image file
        if is_image_file(path):
            image_str, error = render_image_preview(path)
            if image_str is not None:
                # Get image info for header
                try:
                    from PIL import Image

                    with Image.open(path) as img:
                        width, height = img.size
                        img_format = img.format or path.suffix.upper().lstrip(".")
                        header = Text(
                            f"🖼️ {path.name} ({width}x{height} {img_format})\n\n", style="bold"
                        )
                except Exception:
                    header = Text(f"🖼️ {path.name}\n\n", style="bold")

                # Convert ANSI string to Rich Text (no_wrap to prevent responsive resizing)
                image_text = Text.from_ansi(image_str, no_wrap=True)
                rendered_content = Group(header, image_text)
                return {
                    "path": path,
                    "content": f"[Image: {path.name}]",
                    "rendered_content": rendered_content,
                }
            else:
                # Image rendering failed, show error message
                return {
                    "path": path,
                    "content": f"[dim]Cannot preview image: {error}[/dim]",
                    "rendered_content": None,
                }

        # Read file content (I/O operation)
        content = read_file_content(path)

        # Check if content was truncated
        truncation_msg = None
        if "\n\n... truncated (" in content:
            # Split off truncation message for separate styling
            parts = content.rsplit("\n\n... truncated (", 1)
            content = parts[0]
            truncation_msg = Text(f"\n\n... truncated ({parts[1]}", style="dim")

        # Pre-render the syntax highlighting in the worker thread
        # This is the expensive part that would otherwise block the UI
        rendered_content = None

        if not content.startswith("[dim]"):
            # Try tree-sitter first (much faster)
            ts_language = get_language_for_file(path)
            if ts_language:
                highlighted = highlight_with_tree_sitter(content, ts_language, line_numbers=True)
                if highlighted:
                    header = Text(f"📄 {path.name}\n\n", style="bold")
                    if truncation_msg:
                        rendered_content = Group(header, highlighted, truncation_msg)
                    else:
                        rendered_content = Group(header, highlighted)

            # Fall back to Pygments if tree-sitter didn't work
            if rendered_content is None:
                lexer = get_syntax_lexer(path)
                theme = get_syntax_theme(self.theme)
                if lexer:
                    syntax = Syntax(content, lexer, theme=theme, line_numbers=True)
                    header = Text(f"📄 {path.name}\n\n", style="bold")
                    if truncation_msg:
                        rendered_content = Group(header, syntax, truncation_msg)
                    else:
                        rendered_content = Group(header, syntax)

        # Build the result
        result = {
            "path": path,
            "content": content,
            "rendered_content": rendered_content,
        }
        return result

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker completion to update the UI with loaded content."""
        if event.state == WorkerState.SUCCESS and event.worker.name == "_load_file_content":
            result = event.worker.result
            if result is None:
                return

            try:
                path = result["path"]
                content = result["content"]
                rendered_content = result["rendered_content"]

                # Cache the rendered content for instant access later
                # Evict oldest entries if cache is full
                if len(self._rendered_cache) >= self._cache_max_size:
                    oldest = next(iter(self._rendered_cache))
                    del self._rendered_cache[oldest]
                self._rendered_cache[path] = (content, rendered_content)

                # Verify we're still on the same file (user may have navigated away)
                tree = self._get_tree()
                if not tree or not (tree.cursor_node and tree.cursor_node.data):
                    return
                current_path = tree.cursor_node.data.path
                if current_path != path:
                    return  # User navigated to a different file, discard result

                # Update state
                self.original_content = content
                self.search_matches = []
                self.current_match_index = -1
                self.git_log_viewing = False
                self.git_log_output = ""
                self.git_log_entries = []
                self.git_log_highlighted_entry = -1
                self.git_commit_viewing = False
                self.git_commit_hash = ""
                self.git_blame_viewing = False
                self.git_log_page = 0

                # Update display - content is already rendered, just swap it in
                content_display = self._get_content_display()
                scroll_container = self._get_scroll_container()

                if content_display:
                    if rendered_content is not None:
                        content_display.update(rendered_content)
                    else:
                        # Plain text display
                        content_display.update(f"[bold]📄 {path.name}[/bold]\n\n{content}")

                # Reset scroll position
                if scroll_container:
                    scroll_container.scroll_home(animate=False)
                self._displayed_path = path
            except Exception:
                pass

    def _update_content_display(self) -> None:
        """Update the content display synchronously (for non-navigation updates)."""
        try:
            tree = self._get_tree()
            content_display = self._get_content_display()
            scroll_container = self._get_scroll_container()

            if not tree or not content_display or not scroll_container:
                return

            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path

                if path.is_dir():
                    self._dir_listing_highlighted = 0 if list(path.iterdir()) else -1
                    content_display.update(
                        self._render_directory_listing(path, self._dir_listing_highlighted)
                    )
                    self.original_content = ""
                elif is_image_file(path):
                    # Handle image files
                    image_str, error = render_image_preview(path)
                    if image_str is not None:
                        try:
                            from PIL import Image

                            with Image.open(path) as img:
                                width, height = img.size
                                img_format = img.format or path.suffix.upper().lstrip(".")
                                header = Text(
                                    f"🖼️ {path.name} ({width}x{height} {img_format})\n\n",
                                    style="bold",
                                )
                        except Exception:
                            header = Text(f"🖼️ {path.name}\n\n", style="bold")
                        image_text = Text.from_ansi(image_str, no_wrap=True)
                        content_display.update(Group(header, image_text))
                        self.original_content = f"[Image: {path.name}]"
                    else:
                        content_display.update(f"[dim]Cannot preview image: {error}[/dim]")
                        self.original_content = ""
                else:
                    content = read_file_content(path)
                    self.original_content = content

                    lexer = get_syntax_lexer(path)
                    if lexer and not content.startswith("[dim]"):
                        syntax = Syntax(
                            content,
                            lexer,
                            theme=get_syntax_theme(self.theme),
                            line_numbers=True,
                        )
                        header = Text(f"📄 {path.name}\n\n", style="bold")
                        content_display.update(Group(header, syntax))
                    else:
                        content_display.update(f"[bold]📄 {path.name}[/bold]\n\n{content}")

                scroll_container.scroll_home(animate=False)
                self.search_matches = []
                self.current_match_index = -1
                self.git_log_viewing = False
                self.git_log_output = ""
                self.git_log_entries = []
                self.git_log_highlighted_entry = -1
                self.git_commit_viewing = False
                self.git_commit_hash = ""
                self.git_blame_viewing = False
                self.git_log_page = 0
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle key presses for vi-style navigation."""
        # Don't handle keys if an Input widget has focus (let it handle its own keys)
        if self.focused and isinstance(self.focused, Input):
            return

        # Get widgets using helper methods (work with Textual 8.x)
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()

        if not tree or not scroll_container:
            return

        # Check if content panel has focus
        content_focused = scroll_container.has_focus

        # Map vi keys to actions
        key_map = {
            "j": "down",
            "k": "up",
            "h": "left",
            "l": "right",
            "g": "home",
            "G": "end",
        }

        # Arrow keys
        arrow_keys = {"up", "down", "left", "right"}

        if event.key in key_map:
            event.prevent_default()
            action_key = key_map[event.key]

            if content_focused:
                # Control the content scroll panel
                if action_key == "down":
                    if self.git_log_viewing and self.git_log_entries:
                        # Move highlighted entry down in log view
                        if self.git_log_highlighted_entry < len(self.git_log_entries) - 1:
                            self.git_log_highlighted_entry += 1
                            self._render_log_with_highlight()
                            self._scroll_to_log_entry()
                    elif self.git_blame_viewing and self.git_blame_output:
                        # Move highlighted line down in blame view
                        lines = self.git_blame_output.split("\n")
                        max_line = len(lines) - 1
                        if self.git_blame_highlighted_line < max_line:
                            self.git_blame_highlighted_line += 1
                            self._render_blame_with_highlight()
                            # Auto-scroll to keep highlighted line visible
                            self._scroll_to_blame_line()
                    elif self._dir_listing_entries:
                        # Move highlighted entry down in directory listing
                        if self._dir_listing_highlighted < len(self._dir_listing_entries) - 1:
                            self._dir_listing_highlighted += 1
                            self._render_dir_listing_with_highlight()
                            self._scroll_to_dir_entry()
                    else:
                        scroll_container.scroll_down()
                elif action_key == "up":
                    if self.git_log_viewing and self.git_log_entries:
                        # Move highlighted entry up in log view
                        if self.git_log_highlighted_entry > 0:
                            self.git_log_highlighted_entry -= 1
                            self._render_log_with_highlight()
                            self._scroll_to_log_entry()
                    elif self.git_blame_viewing and self.git_blame_output:
                        # Move highlighted line up in blame view
                        if self.git_blame_highlighted_line > 0:
                            self.git_blame_highlighted_line -= 1
                            self._render_blame_with_highlight()
                            # Auto-scroll to keep highlighted line visible
                            self._scroll_to_blame_line()
                    elif self._dir_listing_entries:
                        # Move highlighted entry up in directory listing
                        if self._dir_listing_highlighted > 0:
                            self._dir_listing_highlighted -= 1
                            self._render_dir_listing_with_highlight()
                            self._scroll_to_dir_entry()
                    else:
                        scroll_container.scroll_up()
                elif action_key == "home":
                    if self.git_log_viewing and self.git_log_entries:
                        self.git_log_highlighted_entry = 0
                        self._render_log_with_highlight()
                        scroll_container.scroll_home()
                    elif self.git_blame_viewing and self.git_blame_output:
                        self.git_blame_highlighted_line = 0
                        self._render_blame_with_highlight()
                        scroll_container.scroll_home()
                    elif self._dir_listing_entries:
                        self._dir_listing_highlighted = 0
                        self._render_dir_listing_with_highlight()
                        scroll_container.scroll_home()
                    else:
                        scroll_container.scroll_home()
                elif action_key == "end":
                    if self.git_log_viewing and self.git_log_entries:
                        self.git_log_highlighted_entry = len(self.git_log_entries) - 1
                        self._render_log_with_highlight()
                        scroll_container.scroll_end()
                    elif self.git_blame_viewing and self.git_blame_output:
                        lines = self.git_blame_output.split("\n")
                        self.git_blame_highlighted_line = len(lines) - 1
                    elif self._dir_listing_entries:
                        self._dir_listing_highlighted = len(self._dir_listing_entries) - 1
                        self._render_dir_listing_with_highlight()
                        scroll_container.scroll_end()
                        self._render_blame_with_highlight()
                        scroll_container.scroll_end()
                    else:
                        scroll_container.scroll_end()
                elif action_key == "right":
                    # l toggles git log in content panel
                    self.action_git_log()
                elif action_key == "left":
                    # h scrolls left in content panel
                    if scroll_container.allow_horizontal_scroll:
                        scroll_container.scroll_left()
            else:
                # Control the directory tree
                if action_key == "down":
                    tree.action_cursor_down()
                elif action_key == "up":
                    tree.action_cursor_up()
                elif action_key == "left":
                    # Collapse current node or move to parent
                    if tree.cursor_node and tree.cursor_node.is_expanded:
                        tree.cursor_node.collapse()
                    else:
                        tree.action_cursor_parent()
                elif action_key == "right":
                    # Expand current node or move down
                    if tree.cursor_node and not tree.cursor_node.is_expanded:
                        tree.cursor_node.expand()
                    else:
                        tree.action_cursor_down()
                elif action_key == "home":
                    tree.action_scroll_home()
                elif action_key == "end":
                    tree.action_scroll_end()

                # Update the content display after cursor movement (debounced)
                # Note: git info is NOT updated on navigation - it's expensive (subprocess calls)
                # and doesn't change just from moving the cursor
                self._schedule_content_update()
        elif event.key in arrow_keys:
            if content_focused:
                # Handle arrow keys in content panel same as vi keys
                event.prevent_default()
                if event.key == "down":
                    if self.git_log_viewing and self.git_log_entries:
                        if self.git_log_highlighted_entry < len(self.git_log_entries) - 1:
                            self.git_log_highlighted_entry += 1
                            self._render_log_with_highlight()
                            self._scroll_to_log_entry()
                    elif self.git_blame_viewing and self.git_blame_output:
                        lines = self.git_blame_output.split("\n")
                        max_line = len(lines) - 1
                        if self.git_blame_highlighted_line < max_line:
                            self.git_blame_highlighted_line += 1
                            self._render_blame_with_highlight()
                            self._scroll_to_blame_line()
                    elif self._dir_listing_entries:
                        if self._dir_listing_highlighted < len(self._dir_listing_entries) - 1:
                            self._dir_listing_highlighted += 1
                            self._render_dir_listing_with_highlight()
                            self._scroll_to_dir_entry()
                    else:
                        scroll_container.scroll_down()
                elif event.key == "up":
                    if self.git_log_viewing and self.git_log_entries:
                        if self.git_log_highlighted_entry > 0:
                            self.git_log_highlighted_entry -= 1
                            self._render_log_with_highlight()
                            self._scroll_to_log_entry()
                    elif self.git_blame_viewing and self.git_blame_output:
                        if self.git_blame_highlighted_line > 0:
                            self.git_blame_highlighted_line -= 1
                            self._render_blame_with_highlight()
                            self._scroll_to_blame_line()
                    elif self._dir_listing_entries:
                        if self._dir_listing_highlighted > 0:
                            self._dir_listing_highlighted -= 1
                            self._render_dir_listing_with_highlight()
                            self._scroll_to_dir_entry()
                    else:
                        scroll_container.scroll_up()
                elif event.key == "left":
                    if scroll_container.allow_horizontal_scroll:
                        scroll_container.scroll_left()
                elif event.key == "right":
                    if scroll_container.allow_horizontal_scroll:
                        scroll_container.scroll_right()
            else:
                # Arrow keys are handled by the tree widget, but we still need to update display
                # Use call_after_refresh to ensure the tree has processed the key first
                self.call_after_refresh(self._schedule_content_update)
        elif event.key in ("ctrl+f", "ctrl+d", "d"):
            # Page down (vim-style)
            event.prevent_default()
            if content_focused:
                scroll_container.scroll_page_down()
            else:
                tree.action_page_down()
                self._schedule_content_update()
        elif event.key in ("ctrl+b", "ctrl+u", "u"):
            # Page up (vim-style)
            event.prevent_default()
            if content_focused:
                scroll_container.scroll_page_up()
            else:
                tree.action_page_up()
                self._schedule_content_update()
        elif content_focused and event.key == "slash":
            # Open content search
            event.prevent_default()
            self._show_content_search()
        elif content_focused and event.key == "n":
            event.prevent_default()
            # Check if viewing git log
            if self.git_log_viewing:
                # Next page of git log
                self._git_log(self.git_log_page + 1)
            else:
                # Next search match
                self._goto_next_match()
        elif content_focused and event.key == "N":
            # Previous search match
            event.prevent_default()
            self._goto_previous_match()
        elif content_focused and event.key == "p":
            event.prevent_default()
            # Check if viewing git log
            if self.git_log_viewing and self.git_log_page > 0:
                # Previous page of git log
                self._git_log(self.git_log_page - 1)
        elif content_focused and event.key == "escape":
            # Handle ESC key in content panel
            if self.git_commit_viewing:
                # Go back to git log view
                event.prevent_default()
                self.git_commit_viewing = False
                self.git_commit_hash = ""
                self._render_log_with_highlight()
                self._scroll_to_log_entry()
            elif self.git_log_viewing:
                # Close git log display and restore file content
                event.prevent_default()
                self.git_log_viewing = False
                self.git_log_page = 0
                self.git_log_output = ""
                self.git_log_entries = []
                self.git_log_highlighted_entry = -1
                self.git_commit_viewing = False
                self.git_commit_hash = ""
                self._update_content_display()
            elif self.git_blame_viewing:
                # Close git blame display and restore file content
                event.prevent_default()
                self.git_blame_viewing = False
                self._update_content_display()
            elif self.search_query or self.search_matches:
                # Clear search and highlights (only if search is active)
                event.prevent_default()
                self._hide_content_search(clear_highlights=True)
                self.search_matches = []
                self.current_match_index = -1
                self.search_query = ""
        elif content_focused and event.key == "H":
            # Scroll left (horizontal)
            event.prevent_default()
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_left()
        elif content_focused and event.key == "L":
            # Scroll right (horizontal)
            event.prevent_default()
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_right()
        elif content_focused and event.key == "enter":
            event.prevent_default()
            if self.git_log_viewing and not self.git_commit_viewing:
                # Show the highlighted commit details
                self._show_git_commit()
            elif self._dir_listing_entries and 0 <= self._dir_listing_highlighted < len(
                self._dir_listing_entries
            ):
                # Navigate to the highlighted directory entry
                clicked_path = self._dir_listing_entries[self._dir_listing_highlighted]
                self._navigate_to_path(clicked_path)
            else:
                # Switch focus back to sidebar
                if tree:
                    tree.focus()
        elif not content_focused and event.key == "enter":
            # In sidebar: toggle directory or switch to content panel
            event.prevent_default()
            if tree and tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                if path.is_dir():
                    # Toggle directory expansion
                    if tree.cursor_node.is_expanded:
                        tree.cursor_node.collapse()
                    else:
                        tree.cursor_node.expand()
                else:
                    # For files, switch focus to content panel
                    scroll_container.focus()
            else:
                # No node selected, switch focus to content panel
                scroll_container.focus()
        elif not content_focused and event.key == "slash":
            # Open sidebar search
            event.prevent_default()
            self._show_sidebar_search()
        elif not content_focused and event.key == "n":
            # Next sidebar search match
            event.prevent_default()
            self._goto_next_sidebar_match()
        elif not content_focused and event.key == "N":
            # Previous sidebar search match
            event.prevent_default()
            self._goto_previous_sidebar_match()
        elif not content_focused and event.key == "escape":
            # Clear sidebar search (only if search is active)
            if self.sidebar_search_query or self.sidebar_search_matches:
                event.prevent_default()
                self._hide_sidebar_search()
                self.sidebar_search_matches = []
                self.sidebar_current_match_index = -1
                self.sidebar_search_query = ""

    def _show_content_search(self) -> None:
        """Show the content search input."""
        search_container = self.query_one("#content-search-container")
        search_container.add_class("visible")
        search_input = self.query_one("#content-search-input", Input)
        search_input.value = self.search_query
        search_input.focus()

    def _hide_content_search(self, clear_highlights: bool = False) -> None:
        """Hide the content search input."""
        search_container = self.query_one("#content-search-container")
        search_container.remove_class("visible")
        scroll_container = self._get_scroll_container()
        if scroll_container:
            scroll_container.focus()
        if clear_highlights:
            self._clear_search_highlights()

    def _show_sidebar_search(self) -> None:
        """Show the sidebar search input."""
        search_container = self.query_one("#sidebar-search-container")
        search_container.add_class("visible")
        search_input = self.query_one("#sidebar-search-input", Input)
        search_input.value = self.sidebar_search_query
        search_input.focus()

    def _hide_sidebar_search(self) -> None:
        """Hide the sidebar search input."""
        search_container = self.query_one("#sidebar-search-container")
        search_container.remove_class("visible")
        tree = self._get_tree()
        tree.focus()

    def _perform_sidebar_search(self, query: str) -> None:
        """Search for files/directories matching query."""
        if not query:
            self.sidebar_search_matches = []
            self.sidebar_current_match_index = -1
            return

        self.sidebar_search_query = query
        tree = self._get_tree()

        # Find all nodes matching the query
        self.sidebar_search_matches = []

        def search_nodes(node):
            """Recursively search tree nodes."""
            if node.data and hasattr(node.data, "path"):
                name = node.data.path.name.lower()
                if query.lower() in name:
                    self.sidebar_search_matches.append(node)
            for child in node.children:
                search_nodes(child)

        search_nodes(tree.root)

        if not self.sidebar_search_matches:
            self.notify(f"No files matching: {query}", severity="warning")
            return

        # Go to first match
        self.sidebar_current_match_index = 0
        self._goto_sidebar_match(self.sidebar_current_match_index)
        self.notify(f"Found {len(self.sidebar_search_matches)} match(es)")

    def _goto_sidebar_match(self, index: int) -> None:
        """Navigate to a specific sidebar search match."""
        if not self.sidebar_search_matches:
            return

        node = self.sidebar_search_matches[index]
        tree = self._get_tree()

        # Expand parent nodes to make the match visible
        parent = node.parent
        while parent:
            parent.expand()
            parent = parent.parent

        # Select the node
        tree.select_node(node)
        self._update_content_display()

    def _goto_next_sidebar_match(self) -> None:
        """Go to the next sidebar search match."""
        if not self.sidebar_search_matches:
            if self.sidebar_search_query:
                self.notify("No matches to navigate", severity="warning")
            return

        self.sidebar_current_match_index = (self.sidebar_current_match_index + 1) % len(
            self.sidebar_search_matches
        )
        self._goto_sidebar_match(self.sidebar_current_match_index)
        self.notify(
            f"Match {self.sidebar_current_match_index + 1}/{len(self.sidebar_search_matches)}"
        )

    def _goto_previous_sidebar_match(self) -> None:
        """Go to the previous sidebar search match."""
        if not self.sidebar_search_matches:
            if self.sidebar_search_query:
                self.notify("No matches to navigate", severity="warning")
            return

        self.sidebar_current_match_index = (self.sidebar_current_match_index - 1) % len(
            self.sidebar_search_matches
        )
        self._goto_sidebar_match(self.sidebar_current_match_index)
        self.notify(
            f"Match {self.sidebar_current_match_index + 1}/{len(self.sidebar_search_matches)}"
        )

    def _clear_search_highlights(self) -> None:
        """Remove search highlighting from content and restore original display."""
        if self.original_content:
            content_display = self._get_content_display()
            tree = self._get_tree()
            if tree and tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                if path.is_file():
                    content = self.original_content
                    # Check if we can syntax highlight
                    lexer = get_syntax_lexer(path)
                    if content_display:
                        if lexer and not content.startswith("[dim]"):
                            # Use syntax highlighting with theme-aware color scheme
                            syntax = Syntax(
                                content,
                                lexer,
                                theme=get_syntax_theme(self.theme),
                                line_numbers=True,
                            )
                            # Combine header and syntax
                            header = Text(f"📄 {path.name}\n\n", style="bold")
                            content_display.update(Group(header, syntax))
                        else:
                            # Plain text display
                            content_display.update(
                                f"[bold]📄 {path.name}[/bold]\n\n{self.original_content}"
                            )

    def _perform_search(self, query: str) -> None:
        """Perform search and highlight matches."""
        if not query:
            self._clear_search_highlights()
            self.search_matches = []
            self.current_match_index = -1
            return

        self.search_query = query
        tree = self._get_tree()
        if not tree or not (tree.cursor_node and tree.cursor_node.data):
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            return

        # Get the original content
        content = read_file_content(path)
        self.original_content = content

        # Find all matches and their line numbers (for scrolling)
        self.search_matches = []
        lines = content.split("\n")
        char_pos = 0
        for i, line in enumerate(lines):
            for _match in re.finditer(re.escape(query), line, re.IGNORECASE):
                # Store line_number for each match occurrence
                self.search_matches.append(i)
            char_pos += len(line) + 1  # +1 for newline

        if not self.search_matches:
            self.notify(f"Pattern not found: {query}", severity="warning")
            return

        # Go to first match
        self.current_match_index = 0
        self._update_search_highlights()
        self._scroll_to_current_match()
        self.notify(f"Found {len(self.search_matches)} match(es)")

    def _update_search_highlights(self) -> None:
        """Update content with search highlighting, marking current match differently."""
        if not self.search_query or not self.original_content:
            return

        tree = self._get_tree()
        if not (tree.cursor_node and tree.cursor_node.data):
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            return

        content = self.original_content

        # Build Rich Text object with highlighting and line numbers
        text = Text()
        text.append(f"📄 {path.name}\n\n", style="bold")

        # Styles for highlighting
        current_style = Style(color="black", bgcolor="bright_green")
        other_style = Style(color="black", bgcolor="yellow")

        lines = content.split("\n")
        global_match_count = 0

        for line_num, line in enumerate(lines, 1):
            # Add line number
            text.append(f"{line_num:4d} ", style="dim")

            last_end = 0

            # Find matches in this line
            for match in re.finditer(re.escape(self.search_query), line, flags=re.IGNORECASE):
                # Add text before match
                text.append(line[last_end : match.start()])

                # Add highlighted match
                if global_match_count == self.current_match_index:
                    text.append(match.group(), style=current_style)
                else:
                    text.append(match.group(), style=other_style)

                last_end = match.end()
                global_match_count += 1

            # Add remaining text in line
            text.append(line[last_end:])
            if line_num < len(lines):
                text.append("\n")

        content_display = self._get_content_display()
        content_display.update(text)

    def _scroll_to_current_match(self) -> None:
        """Scroll to the current match."""
        if not self.search_matches or self.current_match_index < 0:
            return

        scroll_container = self._get_scroll_container()
        if not scroll_container:
            return

        # Estimate line height and scroll to match
        match_line = self.search_matches[self.current_match_index]
        # Add 2 for the header (icon + filename + blank line)
        target_line = match_line + 3
        # Scroll to approximate position
        scroll_container.scroll_to(y=target_line, animate=self._config.animate_scroll)

    def _goto_next_match(self) -> None:
        """Go to the next search match."""
        if not self.search_matches:
            if self.search_query:
                self.notify("No matches to navigate", severity="warning")
            return

        self.current_match_index = (self.current_match_index + 1) % len(self.search_matches)
        self._update_search_highlights()
        self._scroll_to_current_match()
        self.notify(f"Match {self.current_match_index + 1}/{len(self.search_matches)}")

    def _goto_previous_match(self) -> None:
        """Go to the previous search match."""
        if not self.search_matches:
            if self.search_query:
                self.notify("No matches to navigate", severity="warning")
            return

        self.current_match_index = (self.current_match_index - 1) % len(self.search_matches)
        self._update_search_highlights()
        self._scroll_to_current_match()
        self.notify(f"Match {self.current_match_index + 1}/{len(self.search_matches)}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input submission."""
        if event.input.id == "content-search-input":
            self._perform_search(event.value)
            self._hide_content_search()
        elif event.input.id == "sidebar-search-input":
            self._perform_sidebar_search(event.value)
            self._hide_sidebar_search()

    def action_cursor_down(self) -> None:
        """Move cursor down in tree or scroll content."""
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus
        if content_focused:
            # Handle content panel navigation
            if self.git_log_viewing and self.git_log_entries:
                if self.git_log_highlighted_entry < len(self.git_log_entries) - 1:
                    self.git_log_highlighted_entry += 1
                    self._render_log_with_highlight()
                    self._scroll_to_log_entry()
            elif self.git_blame_viewing and self.git_blame_output:
                lines = self.git_blame_output.split("\n")
                max_line = len(lines) - 1
                if self.git_blame_highlighted_line < max_line:
                    self.git_blame_highlighted_line += 1
                    self._render_blame_with_highlight()
                    self._scroll_to_blame_line()
            elif self._dir_listing_entries:
                if self._dir_listing_highlighted < len(self._dir_listing_entries) - 1:
                    self._dir_listing_highlighted += 1
                    self._render_dir_listing_with_highlight()
                    self._scroll_to_dir_entry()
            else:
                scroll_container.scroll_down()
        else:
            # Control the directory tree
            tree.action_cursor_down()
            self._schedule_content_update()

    def action_cursor_up(self) -> None:
        """Move cursor up in tree or scroll content."""
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus
        if content_focused:
            # Handle content panel navigation
            if self.git_log_viewing and self.git_log_entries:
                if self.git_log_highlighted_entry > 0:
                    self.git_log_highlighted_entry -= 1
                    self._render_log_with_highlight()
                    self._scroll_to_log_entry()
            elif self.git_blame_viewing and self.git_blame_output:
                if self.git_blame_highlighted_line > 0:
                    self.git_blame_highlighted_line -= 1
                    self._render_blame_with_highlight()
                    self._scroll_to_blame_line()
            elif self._dir_listing_entries:
                if self._dir_listing_highlighted > 0:
                    self._dir_listing_highlighted -= 1
                    self._render_dir_listing_with_highlight()
                    self._scroll_to_dir_entry()
            else:
                scroll_container.scroll_up()
        else:
            # Control the directory tree
            tree.action_cursor_up()
            self._schedule_content_update()

    def action_cursor_left(self) -> None:
        """Collapse tree node or scroll content left."""
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus
        if content_focused:
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_left()
        else:
            # Collapse current node or move to parent
            if tree.cursor_node and tree.cursor_node.is_expanded:
                tree.cursor_node.collapse()
            else:
                tree.action_cursor_parent()
            self._schedule_content_update()

    def action_cursor_right(self) -> None:
        """Expand tree node or toggle git log in content."""
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus
        if content_focused:
            # l toggles git log in content panel
            self.action_git_log()
        else:
            # Expand current node or move down
            if tree.cursor_node and not tree.cursor_node.is_expanded:
                tree.cursor_node.expand()
            else:
                tree.action_cursor_down()
            self._schedule_content_update()

    def action_scroll_home(self) -> None:
        """Scroll to top of tree or content."""
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus
        if content_focused:
            if self.git_log_viewing and self.git_log_entries:
                self.git_log_highlighted_entry = 0
                self._render_log_with_highlight()
                scroll_container.scroll_home()
            elif self.git_blame_viewing and self.git_blame_output:
                self.git_blame_highlighted_line = 0
                self._render_blame_with_highlight()
                scroll_container.scroll_home()
            elif self._dir_listing_entries:
                self._dir_listing_highlighted = 0
                self._render_dir_listing_with_highlight()
                scroll_container.scroll_home()
            else:
                scroll_container.scroll_home()
        else:
            tree.action_scroll_home()
            self._schedule_content_update()

    def action_scroll_end(self) -> None:
        """Scroll to end of tree or content."""
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus
        if content_focused:
            if self.git_log_viewing and self.git_log_entries:
                self.git_log_highlighted_entry = len(self.git_log_entries) - 1
                self._render_log_with_highlight()
                scroll_container.scroll_end()
            elif self.git_blame_viewing and self.git_blame_output:
                lines = self.git_blame_output.split("\n")
                self.git_blame_highlighted_line = len(lines) - 1
                self._render_blame_with_highlight()
                scroll_container.scroll_end()
            elif self._dir_listing_entries:
                self._dir_listing_highlighted = len(self._dir_listing_entries) - 1
                self._render_dir_listing_with_highlight()
                scroll_container.scroll_end()
            else:
                scroll_container.scroll_end()
        else:
            tree.action_scroll_end()
            self._schedule_content_update()

    def action_page_up(self) -> None:
        """Scroll the content panel up by one page."""
        scroll_container = self._get_scroll_container()
        if scroll_container:
            scroll_container.scroll_page_up()

    def action_page_down(self) -> None:
        """Scroll the content panel down by one page."""
        scroll_container = self._get_scroll_container()
        if scroll_container:
            scroll_container.scroll_page_down()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from the directory tree - keep focus in sidebar."""
        # Update content display but keep focus in the sidebar (debounced for rapid navigation)
        self._schedule_content_update()
        tree = self._get_tree()
        if tree:
            tree.focus()

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """Handle directory selection from the directory tree."""
        # Update content display (debounced for rapid navigation)
        self._schedule_content_update()

    def on_tree_node_highlighted(self, event) -> None:
        """Handle cursor movement in the tree (including mouse clicks)."""
        self._schedule_content_update()

    def on_click(self, event: events.Click) -> None:
        """Handle mouse clicks to stop scroll animations and highlight blame lines."""
        # Check if the click is in the content scroll container
        scroll_container = self._get_scroll_container()
        tree = self._get_tree()

        if not scroll_container or not tree:
            return

        widget_at_click, _ = self.get_widget_at(event.screen_x, event.screen_y)

        # Handle clicks on directory tree
        if widget_at_click is tree or tree in widget_at_click.ancestors:
            # Double-click opens file in editor
            if event.chain >= 2:
                if tree.cursor_node and tree.cursor_node.data:
                    path = tree.cursor_node.data.path
                    if path.is_file():
                        self.action_edit_file()
                        return
            # Single click updates content panel
            # Use call_after_refresh to ensure the tree has processed the click first
            # Then trigger update immediately (no debounce for clicks)
            self.call_after_refresh(self._do_content_update)

        # If click is within the scroll container or its children
        if widget_at_click is scroll_container or scroll_container in widget_at_click.ancestors:
            # Stop any ongoing scroll animations
            self.call_later(scroll_container.stop_animation, "scroll_x")
            self.call_later(scroll_container.stop_animation, "scroll_y")

            # Handle git log entry highlighting
            if self.git_log_viewing and self.git_log_entries and not self.git_commit_viewing:
                # Calculate clicked line based on screen position
                container_region = scroll_container.region
                scroll_y = int(scroll_container.scroll_y)

                # Calculate y position relative to the container content
                # Subtract 2 for header lines (title + empty line), 2 for padding/border
                relative_y = event.screen_y - container_region.y - 2 + scroll_y - 2

                # Find which entry contains this line
                for i, (start_line, end_line) in enumerate(self.git_log_entries):
                    if start_line <= relative_y <= end_line:
                        self.git_log_highlighted_entry = i
                        self._render_log_with_highlight()
                        # Double-click opens the commit details
                        if event.chain >= 2:
                            self._show_git_commit()
                        break

            # Handle blame view line highlighting
            elif self.git_blame_viewing and self.git_blame_output:
                # Calculate clicked line based on screen position
                # Get the scroll container's position on screen
                container_region = scroll_container.region
                scroll_y = int(scroll_container.scroll_y)

                # Calculate y position relative to the container content
                # event.screen_y is absolute screen position
                # container_region.y is the container's top position on screen
                # Add scroll offset and subtract padding (1 line for top padding, 1 for border)
                relative_y = event.screen_y - container_region.y - 2 + scroll_y

                # Validate line number
                lines = self.git_blame_output.split("\n")
                if 0 <= relative_y < len(lines):
                    self.git_blame_highlighted_line = relative_y
                    self._render_blame_with_highlight()

            # Handle directory listing clicks
            elif (
                self._dir_listing_entries and self._displayed_path and self._displayed_path.is_dir()
            ):
                # Calculate clicked line based on screen position
                container_region = scroll_container.region
                scroll_y = int(scroll_container.scroll_y)

                # Calculate y position relative to the container content
                # Subtract 2 for header line ("📁 dirname/") and empty line, plus padding/border
                relative_y = event.screen_y - container_region.y - 2 + scroll_y - 2

                # Check if clicked on a valid entry
                if 0 <= relative_y < len(self._dir_listing_entries):
                    self._dir_listing_highlighted = relative_y
                    self._render_dir_listing_with_highlight()
                    # Double-click navigates to the item
                    if event.chain >= 2:
                        clicked_path = self._dir_listing_entries[relative_y]
                        self._navigate_to_path(clicked_path)

    def _navigate_to_path(self, path: Path) -> None:
        """Navigate to a specific path in the directory tree and update content."""
        tree = self._get_tree()

        # Find and select the node for this path
        def find_node(node, target_path: Path):
            """Recursively find a node with the given path."""
            if node.data and hasattr(node.data, "path") and node.data.path == target_path:
                return node
            for child in node.children:
                result = find_node(child, target_path)
                if result:
                    return result
            return None

        # First ensure parent directories are expanded
        try:
            rel_path = path.relative_to(self.start_path)
            parts = rel_path.parts
            current_path = self.start_path

            # Expand each parent directory
            for part in parts[:-1]:
                current_path = current_path / part
                node = find_node(tree.root, current_path)
                if node and not node.is_expanded:
                    node.expand()

            # Now find and select the target node
            # Use call_after_refresh to ensure expansions are processed
            def select_target():
                target_node = find_node(tree.root, path)
                if target_node:
                    tree.select_node(target_node)
                    self._schedule_content_update()

            self.call_after_refresh(select_target)
        except ValueError:
            # Path is not relative to start_path
            pass

    def action_edit_file(self) -> None:
        """Open the currently selected file in the editor (or image viewer for images)."""
        tree = self._get_tree()
        if tree.cursor_node and tree.cursor_node.data:
            path = tree.cursor_node.data.path
            if path.is_file():
                if is_image_file(path):
                    self._open_in_system_viewer(path)
                else:
                    self._open_in_editor(path)
            else:
                self.notify("Cannot edit a directory", severity="warning")

    def action_open_shell(self) -> None:
        """Open a shell in the current working directory."""
        tree = self._get_tree()
        if tree.cursor_node and tree.cursor_node.data:
            path = tree.cursor_node.data.path
            # If it's a file, use its parent directory
            cwd = path.parent if path.is_file() else path
            self._open_shell(cwd)
        else:
            # Fall back to start_path if no node is selected
            self._open_shell(self.start_path)

    def action_git_blame(self) -> None:
        """Toggle git blame for the current file."""
        if self.git_blame_viewing:
            # Turn off blame and restore file content
            self.git_blame_viewing = False
            self.git_blame_output = ""
            self.git_blame_highlighted_line = -1
            self._update_content_display()
            # Get the current file name for the notification
            tree = self._get_tree()
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                self.notify(f"Hiding blame for {path.name}")
        else:
            self._git_blame_current()

    def action_git_log(self) -> None:
        """Toggle git log."""
        if self.git_log_viewing:
            # Turn off log and restore file content
            self.git_log_viewing = False
            self.git_log_page = 0
            self.git_log_output = ""
            self.git_log_entries = []
            self.git_log_highlighted_entry = -1
            self.git_commit_viewing = False
            self.git_commit_hash = ""
            self._update_content_display()
            self.notify("Hiding git log")
        else:
            self._git_log()

    def _open_shell(self, directory: Path) -> None:
        """Open a shell in the specified directory."""
        try:
            # Detect the user's shell
            shell = os.environ.get("SHELL", "/bin/sh")

            # Suspend the Textual app to give control back to the terminal
            with self.suspend():
                # Run the shell in the specified directory
                result = subprocess.run(
                    [shell],
                    cwd=str(directory),
                )
                if result.returncode != 0:
                    self.notify(
                        f"Shell exited with code {result.returncode}",
                        severity="warning",
                    )
        except Exception as e:
            self.notify(f"Error opening shell: {e}", severity="error")

    def _open_in_editor(self, file_path: Path) -> None:
        """Open a file in the user's editor."""
        if self.is_terminal_editor:
            self._open_in_terminal_editor(file_path)
        else:
            self._open_in_gui_editor(file_path)

    def _open_in_terminal_editor(self, file_path: Path) -> None:
        """Open a file in a terminal editor by suspending the app."""
        try:
            # Suspend the Textual app to give control back to the terminal
            with self.suspend():
                # Run the editor and wait for it to complete
                result = subprocess.run(
                    [*self.editor_command, str(file_path)],
                )
                if result.returncode != 0:
                    self.notify(
                        f"Editor exited with code {result.returncode}",
                        severity="warning",
                    )
        except Exception as e:
            self.notify(f"Error opening file: {e}", severity="error")

    def _open_in_gui_editor(self, file_path: Path) -> None:
        """Open a file in a GUI editor (non-blocking)."""
        try:
            subprocess.Popen(
                [*self.editor_command, str(file_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.notify(f"Opened: {file_path.name}", severity="information")
        except Exception as e:
            self.notify(f"Error opening file: {e}", severity="error")

    def _open_in_system_viewer(self, file_path: Path) -> None:
        """Open a file with the system's default application (e.g., Preview for images on macOS)."""
        import sys

        try:
            if sys.platform == "darwin":
                # macOS: use 'open' command (opens in Preview for images)
                cmd = ["open", str(file_path)]
            elif sys.platform == "win32":
                # Windows: use 'start' command
                cmd = ["start", "", str(file_path)]
            else:
                # Linux/other: use 'xdg-open'
                cmd = ["xdg-open", str(file_path)]

            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.notify(f"Opened: {file_path.name}", severity="information")
        except Exception as e:
            self.notify(f"Error opening file: {e}", severity="error")

    def _delete_current_file(self) -> None:
        """Delete the currently selected file."""
        tree = self._get_tree()
        if not (tree.cursor_node and tree.cursor_node.data):
            self.notify("No file selected", severity="warning")
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            self.notify("Cannot delete a directory", severity="warning")
            return

        # Confirm deletion
        from textual.containers import Horizontal
        from textual.screen import ModalScreen
        from textual.widgets import Button, Static

        app = self
        file_path = path

        class ConfirmDeleteScreen(ModalScreen[bool]):
            """Modal screen for confirming file deletion."""

            BINDINGS = [
                Binding("enter", "confirm", "Confirm", priority=True),
                Binding("escape", "cancel", "Cancel", priority=True),
            ]

            CSS = """
            ConfirmDeleteScreen {
                align: center middle;
            }
            #dialog {
                width: 60;
                height: auto;
                border: thick $error;
                background: $surface;
                padding: 1 2;
            }
            #dialog Static {
                width: 100%;
                content-align: center middle;
            }
            #buttons {
                width: 100%;
                height: auto;
                align: center middle;
                margin-top: 1;
            }
            #buttons Button {
                margin: 0 1;
            }
            """

            def compose(self):
                with Vertical(id="dialog"):
                    yield Static(f"Delete file?\n\n[bold]{file_path.name}[/bold]")
                    with Horizontal(id="buttons"):
                        yield Button("Delete", variant="error", id="delete")
                        yield Button("Cancel", variant="primary", id="cancel")

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "delete":
                    self.dismiss(True)
                else:
                    self.dismiss(False)

            def action_confirm(self) -> None:
                self.dismiss(True)

            def action_cancel(self) -> None:
                self.dismiss(False)

        def handle_delete(confirmed: bool) -> None:
            if confirmed:
                try:
                    file_path.unlink()
                    app.notify(f"Deleted: {file_path.name}", severity="information")
                    # Reload the tree to reflect the deletion
                    app._reload_tree()
                    # Refresh git status if in a git repo
                    if app.git_branch:
                        app._git_refresh()
                except Exception as e:
                    app.notify(f"Error deleting file: {e}", severity="error")

        self.push_screen(ConfirmDeleteScreen(), handle_delete)

    def _change_theme(self, theme_name: str) -> None:
        """Change the application theme."""
        try:
            self.theme = theme_name
            # Save theme to config
            self._config.theme = theme_name
            self._config.save()
            self.notify(f"Theme changed to {theme_name}")
            # Re-render content with new syntax theme
            self._update_content_display()
        except Exception as e:
            self.notify(f"Failed to change theme: {e}", severity="error")

    def _save_config(self) -> None:
        """Save the current configuration to disk."""
        try:
            self._config.save()
            from vii.config import get_config_path

            self.notify(f"Config saved to {get_config_path()}")
        except Exception as e:
            self.notify(f"Failed to save config: {e}", severity="error")

    def _edit_config(self) -> None:
        """Open the config file in the editor."""
        from vii.config import get_config_path

        config_path = get_config_path()

        # Ensure config file exists
        if not config_path.exists():
            self._config.save()

        # Open in editor
        self._open_in_editor(config_path)

    def _apply_random_theme(self) -> None:
        """Apply a random theme without saving to config."""
        import random

        # Get all available themes except "random" itself
        themes = [name for name in self.available_themes.keys() if name != "random"]
        theme_name = random.choice(themes)
        self.theme = theme_name
        self.notify(f"Random theme: {theme_name}")


def main():
    """Main entry point."""
    start_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    if not start_path.exists():
        print(f"Error: Path '{start_path}' does not exist", file=sys.stderr)
        sys.exit(1)

    app = Vii(start_path=start_path)
    app.run()


if __name__ == "__main__":
    main()
