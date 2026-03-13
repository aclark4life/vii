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
from textual.command import Hits
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import DirectoryTree, Footer, Header, Input, Static
from textual.worker import Worker, WorkerState

from vii.commands import GitCommandProvider
from vii.content import get_syntax_lexer, get_syntax_theme, read_file_content
from vii.git_utils import (
    get_git_branch,
    get_git_file_status,
    get_git_root,
    get_git_status_summary,
    is_git_repo,
)
from vii.tree_sitter_highlight import get_language_for_file, highlight_with_tree_sitter
from vii.widgets import GitDirectoryTree, VerticalSplitter


class Vii(App):
    """vii - Terminal file browser."""

    TITLE = "🤖 vii"
    COMMANDS = App.COMMANDS | {GitCommandProvider}

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
    }

    #content-scroll:focus {
        border: solid $accent;
    }

    #content-display {
        padding: 1 2;
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
        Binding("l", "git_log", "Log"),
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
        self.theme = "textual-dark"  # Set default theme
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
        self.git_log_viewing: bool = False
        self.git_blame_viewing: bool = False
        self._update_git_info()

    def set_sidebar_width(self, width: int) -> None:
        """Set the sidebar width, with bounds checking."""
        # Get screen width and set minimum/maximum bounds
        screen_width = self.size.width
        min_width = 10
        max_width = screen_width - 15  # Leave at least 15 columns for content

        # Clamp width to bounds
        self.sidebar_width = max(min_width, min(width, max_width))

    def watch_sidebar_width(self, width: int) -> None:
        """React to sidebar width changes."""
        try:
            sidebar = self.query_one("#sidebar")
            sidebar.styles.width = width
        except Exception:
            pass  # Widget may not be mounted yet

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
        # Set initial width based on screen size (about 1/3 of screen)
        initial_width = max(20, self.size.width // 3)
        self.sidebar_width = initial_width

        # Subscribe to theme changes to update syntax highlighting
        self.theme_changed_signal.subscribe(self, self._on_theme_changed)

        # Update header with git info
        self._update_header()

    def _get_current_directory(self) -> Path:
        """Get the current directory based on the tree cursor position."""
        try:
            tree = self.query_one(DirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
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

    def _on_theme_changed(self, theme: object) -> None:
        """React to theme changes by updating the content display.

        Args:
            theme: The new Theme object (from theme_changed_signal).
        """
        # Re-render the content with the new syntax theme
        self._update_content_display()

    def _navigate_to_directory(self, directory: Path) -> None:
        """Navigate to a different directory by reloading the tree."""
        try:
            # Remove the old tree
            old_tree = self.query_one(DirectoryTree)
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
            old_tree = self.query_one(DirectoryTree)
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

    def _do_content_update(self) -> None:
        """Load and display content after navigation stops (100ms debounce)."""
        self._content_update_timer = None

        # Reset search state
        self.search_matches = []
        self.current_match_index = -1
        self.git_log_viewing = False
        self.git_blame_viewing = False
        self.git_log_page = 0

        try:
            tree = self.query_one(DirectoryTree)
            if not tree.cursor_node or not tree.cursor_node.data:
                return

            path = tree.cursor_node.data.path

            # Skip if already displaying this path
            if path == self._displayed_path:
                return

            content_display = self.query_one("#content-display", Static)
            scroll_container = self.query_one("#content-scroll", ScrollableContainer)

            if path.is_dir():
                content_display.update(f"[bold]📁 {path.name}[/bold]\n\n[dim]Directory[/dim]")
                self.original_content = ""
                self._displayed_path = path
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
                tree = self.query_one(DirectoryTree)
                if not (tree.cursor_node and tree.cursor_node.data):
                    return
                current_path = tree.cursor_node.data.path
                if current_path != path:
                    return  # User navigated to a different file, discard result

                # Update state
                self.original_content = content
                self.search_matches = []
                self.current_match_index = -1
                self.git_log_viewing = False
                self.git_blame_viewing = False
                self.git_log_page = 0

                # Update display - content is already rendered, just swap it in
                content_display = self.query_one("#content-display", Static)
                scroll_container = self.query_one("#content-scroll", ScrollableContainer)

                if rendered_content is not None:
                    content_display.update(rendered_content)
                else:
                    # Plain text display
                    content_display.update(f"[bold]📄 {path.name}[/bold]\n\n{content}")

                # Reset scroll position
                scroll_container.scroll_home(animate=False)
                self._displayed_path = path
            except Exception:
                pass

    def _update_content_display(self) -> None:
        """Update the content display synchronously (for non-navigation updates)."""
        try:
            tree = self.query_one(DirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                content_display = self.query_one("#content-display", Static)
                scroll_container = self.query_one("#content-scroll", ScrollableContainer)

                if path.is_dir():
                    content_display.update(f"[bold]📁 {path.name}[/bold]\n\n[dim]Directory[/dim]")
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
                self.git_blame_viewing = False
                self.git_log_page = 0
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle key presses for vi-style navigation."""
        # Don't handle keys if an Input widget has focus (let it handle its own keys)
        if self.focused and isinstance(self.focused, Input):
            return

        tree = self.query_one(DirectoryTree)
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)

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
                    scroll_container.scroll_down()
                elif action_key == "up":
                    scroll_container.scroll_up()
                elif action_key == "home":
                    scroll_container.scroll_home()
                elif action_key == "end":
                    scroll_container.scroll_end()
                # h/l do nothing in content panel
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
        elif event.key in arrow_keys and not content_focused:
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
            if self.git_log_viewing:
                # Close git log display and restore file content
                event.prevent_default()
                self.git_log_viewing = False
                self.git_log_page = 0
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
        elif content_focused and event.key == "enter":
            # Switch focus back to sidebar
            event.prevent_default()
            tree = self.query_one(DirectoryTree)
            tree.focus()
        elif not content_focused and event.key == "enter":
            # In sidebar: toggle directory or switch to content panel
            event.prevent_default()
            tree = self.query_one(DirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
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
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
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
        tree = self.query_one(DirectoryTree)
        tree.focus()

    def _perform_sidebar_search(self, query: str) -> None:
        """Search for files/directories matching query."""
        if not query:
            self.sidebar_search_matches = []
            self.sidebar_current_match_index = -1
            return

        self.sidebar_search_query = query
        tree = self.query_one(DirectoryTree)

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
        tree = self.query_one(DirectoryTree)

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
            content_display = self.query_one("#content-display", Static)
            tree = self.query_one(DirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                if path.is_file():
                    content = self.original_content
                    # Check if we can syntax highlight
                    lexer = get_syntax_lexer(path)
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
        tree = self.query_one(DirectoryTree)
        if not (tree.cursor_node and tree.cursor_node.data):
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

        tree = self.query_one(DirectoryTree)
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

        content_display = self.query_one("#content-display", Static)
        content_display.update(text)

    def _scroll_to_current_match(self) -> None:
        """Scroll to the current match."""
        if not self.search_matches or self.current_match_index < 0:
            return

        scroll_container = self.query_one("#content-scroll", ScrollableContainer)

        # Estimate line height and scroll to match
        match_line = self.search_matches[self.current_match_index]
        # Add 2 for the header (icon + filename + blank line)
        target_line = match_line + 3
        # Scroll to approximate position
        scroll_container.scroll_to(y=target_line, animate=True)

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

    def action_page_up(self) -> None:
        """Scroll the content panel up by one page."""
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        scroll_container.scroll_page_up()

    def action_page_down(self) -> None:
        """Scroll the content panel down by one page."""
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        scroll_container.scroll_page_down()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from the directory tree - keep focus in sidebar."""
        # Update content display but keep focus in the sidebar (debounced for rapid navigation)
        # Note: git info is NOT updated here - it's expensive and doesn't change from file selection
        self._schedule_content_update()
        tree = self.query_one(DirectoryTree)
        tree.focus()

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        """Handle directory selection from the directory tree."""
        # Note: git info is NOT updated here - it's expensive and doesn't change from navigation
        pass

    def on_click(self, event: events.Click) -> None:
        """Handle mouse clicks to stop scroll animations."""
        # Check if the click is in the content scroll container
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        widget_at_click, _ = self.get_widget_at(event.screen_x, event.screen_y)

        # If click is within the scroll container or its children, stop animations
        if widget_at_click is scroll_container or scroll_container in widget_at_click.ancestors:
            # Stop any ongoing scroll animations
            self.call_later(scroll_container.stop_animation, "scroll_x")
            self.call_later(scroll_container.stop_animation, "scroll_y")

    def action_edit_file(self) -> None:
        """Open the currently selected file in the editor."""
        tree = self.query_one(DirectoryTree)
        if tree.cursor_node and tree.cursor_node.data:
            path = tree.cursor_node.data.path
            if path.is_file():
                self._open_in_editor(path)
            else:
                self.notify("Cannot edit a directory", severity="warning")

    def action_open_shell(self) -> None:
        """Open a shell in the current working directory."""
        tree = self.query_one(DirectoryTree)
        if tree.cursor_node and tree.cursor_node.data:
            path = tree.cursor_node.data.path
            # If it's a file, use its parent directory
            cwd = path.parent if path.is_file() else path
            self._open_shell(cwd)
        else:
            # Fall back to start_path if no node is selected
            self._open_shell(self.start_path)

    def action_git_blame(self) -> None:
        """Show git blame for the current file."""
        self._git_blame_current()

    def action_git_log(self) -> None:
        """Show git log."""
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

    # Git command implementations
    def _git_status(self) -> None:
        """Show git status."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(self.git_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout:
                self.notify(f"Git status:\n{result.stdout}")
            else:
                self.notify("Working tree clean", severity="information")
        except Exception as e:
            self.notify(f"Git status failed: {e}", severity="error")

    def _git_refresh(self) -> None:
        """Refresh git status."""
        self._update_git_info()
        self._update_header()
        self.notify("Git status refreshed")

    def _git_log(self, page: int = 0) -> None:
        """Show git commit history.

        Args:
            page: Page number to display (0-based)
        """
        if not self.git_branch:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            from .git_utils import get_git_log

            current_dir = self._get_current_directory()
            skip = page * self.git_log_page_size
            log_output = get_git_log(current_dir, max_count=self.git_log_page_size, skip=skip)

            if log_output:
                # Display log in content panel
                from rich.text import Text

                text = Text()
                text.append(f"📜 Git Log (Page {page + 1})\n\n", style="bold")
                text.append(log_output)
                text.append("\n\n")
                text.append("Navigation: ", style="dim")
                if page > 0:
                    text.append("n", style="bold cyan")
                    text.append(" = Next page  ", style="dim")
                    text.append("p", style="bold cyan")
                    text.append(" = Previous page  ", style="dim")
                else:
                    text.append("n", style="bold cyan")
                    text.append(" = Next page  ", style="dim")
                text.append("ESC", style="bold cyan")
                text.append(" = Close", style="dim")

                content_display = self.query_one("#content-display", Static)
                content_display.update(text)

                # Update state
                self.git_log_page = page
                self.git_log_viewing = True

                # Focus the content panel so n/p keys work
                scroll_container = self.query_one("#content-scroll", ScrollableContainer)
                scroll_container.focus()

                self.notify(f"Showing git log (page {page + 1})")
            else:
                if page > 0:
                    self.notify("No more commits", severity="information")
                else:
                    self.notify("No git log available", severity="information")
        except Exception as e:
            self.notify(f"Git log failed: {e}", severity="error")

    def _git_add_current(self) -> None:
        """Add the current file to git."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        tree = self.query_one(DirectoryTree)
        if not (tree.cursor_node and tree.cursor_node.data):
            self.notify("No file selected", severity="warning")
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            self.notify("Cannot add a directory", severity="warning")
            return

        try:
            rel_path = path.relative_to(self.git_root)
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=str(self.git_root),
                check=True,
                timeout=5,
            )
            self.notify(f"Added {path.name} to git")
            self._git_refresh()
        except Exception as e:
            self.notify(f"Git add failed: {e}", severity="error")

    def _git_add_all(self) -> None:
        """Add all changes to git."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            subprocess.run(
                ["git", "add", "."],
                cwd=str(self.git_root),
                check=True,
                timeout=5,
            )
            self.notify("Added all changes to git")
            self._git_refresh()
        except Exception as e:
            self.notify(f"Git add failed: {e}", severity="error")

    def _git_commit(self) -> None:
        """Commit changes (opens editor for commit message)."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        self.notify("Opening editor for commit message...")
        try:
            subprocess.run(
                ["git", "commit"],
                cwd=str(self.git_root),
                timeout=300,  # 5 minutes for commit message
            )
            self._git_refresh()
        except Exception as e:
            self.notify(f"Git commit failed: {e}", severity="error")

    def _git_push(self) -> None:
        """Push changes to remote."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        self.notify("Pushing to remote...")
        try:
            result = subprocess.run(
                ["git", "push"],
                cwd=str(self.git_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                self.notify("Pushed successfully")
            else:
                self.notify(f"Push failed: {result.stderr}", severity="error")
        except Exception as e:
            self.notify(f"Git push failed: {e}", severity="error")

    def _git_pull(self) -> None:
        """Pull changes from remote."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        self.notify("Pulling from remote...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(self.git_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                self.notify("Pulled successfully")
                # Reload the directory tree to reflect pulled changes
                self._reload_tree()
                self._git_refresh()
            else:
                self.notify(f"Pull failed: {result.stderr}", severity="error")
        except Exception as e:
            self.notify(f"Git pull failed: {e}", severity="error")

    def _git_diff_current(self) -> None:
        """Show git diff for the current file."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        tree = self.query_one(DirectoryTree)
        if not (tree.cursor_node and tree.cursor_node.data):
            self.notify("No file selected", severity="warning")
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            self.notify("Cannot diff a directory", severity="warning")
            return

        try:
            rel_path = path.relative_to(self.git_root)
            result = subprocess.run(
                ["git", "diff", "HEAD", str(rel_path)],
                cwd=str(self.git_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout:
                # Display diff in content panel
                content_display = self.query_one("#content-display", Static)
                content_display.update(f"[bold]Git Diff: {path.name}[/bold]\n\n{result.stdout}")
                self.notify(f"Showing diff for {path.name}")
            else:
                self.notify("No changes to show", severity="information")
        except Exception as e:
            self.notify(f"Git diff failed: {e}", severity="error")

    def _git_blame_current(self) -> None:
        """Show git blame for the current file."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        tree = self.query_one(DirectoryTree)
        if not (tree.cursor_node and tree.cursor_node.data):
            self.notify("No file selected", severity="warning")
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            self.notify("Cannot blame a directory", severity="warning")
            return

        try:
            from .git_utils import get_git_blame_file

            rel_path = path.relative_to(self.git_root)
            blame_output = get_git_blame_file(self.git_root, str(rel_path))

            if blame_output:
                # Display blame in content panel with syntax highlighting
                from rich.syntax import Syntax

                syntax = Syntax(
                    blame_output,
                    "diff",  # Use diff lexer for git blame output
                    theme=get_syntax_theme(self.theme),
                    line_numbers=False,
                    word_wrap=False,
                )
                content_display = self.query_one("#content-display", Static)
                content_display.update(syntax)

                # Update state so ESC can restore file content
                self.git_blame_viewing = True

                # Focus the content panel
                scroll_container = self.query_one("#content-scroll", ScrollableContainer)
                scroll_container.focus()

                self.notify(f"Showing blame for {path.name}")
            else:
                self.notify("No blame information available", severity="information")
        except Exception as e:
            self.notify(f"Git blame failed: {e}", severity="error")

    def _git_switch_branch(self) -> None:
        """Show branch selection and switch to selected branch."""
        if not self.git_branch or not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            from textual.command import CommandPalette, DiscoveryHit, Hit, Provider

            from .git_utils import get_git_branches

            branches = get_git_branches(self.git_root)
            if not branches:
                self.notify("Failed to get branch list", severity="error")
                return

            current_branch = self.git_branch
            app = self

            # Create a provider for branch selection
            class BranchProvider(Provider):
                """Provider for branch selection."""

                async def discover(self) -> Hits:
                    """Show all branches."""
                    # Show local branches first
                    for branch in branches["local"]:
                        if branch == current_branch:
                            yield DiscoveryHit(
                                f"✓ {branch} (current)",
                                lambda b=branch: None,  # No-op for current branch
                                help="Current branch",
                            )
                        else:
                            yield DiscoveryHit(
                                f"  {branch}",
                                lambda b=branch: app._do_checkout_branch(b, False),
                                help="Local branch",
                            )

                    # Show remote branches
                    for branch in branches["remote"]:
                        # Extract local name for comparison
                        local_name = branch.split("/", 1)[1] if "/" in branch else branch
                        if local_name not in branches["local"]:
                            yield DiscoveryHit(
                                f"  {branch} (remote)",
                                lambda b=branch: app._do_checkout_branch(b, True),
                                help="Remote branch - will create local tracking branch",
                            )

                async def search(self, query: str) -> Hits:
                    """Search branches."""
                    matcher = self.matcher(query)

                    # Search local branches
                    for branch in branches["local"]:
                        score = matcher.match(branch)
                        if score > 0:
                            if branch == current_branch:
                                yield Hit(
                                    score,
                                    matcher.highlight(f"✓ {branch} (current)"),
                                    lambda b=branch: None,
                                    help="Current branch",
                                )
                            else:
                                yield Hit(
                                    score,
                                    matcher.highlight(f"  {branch}"),
                                    lambda b=branch: app._do_checkout_branch(b, False),
                                    help="Local branch",
                                )

                    # Search remote branches
                    for branch in branches["remote"]:
                        score = matcher.match(branch)
                        if score > 0:
                            local_name = branch.split("/", 1)[1] if "/" in branch else branch
                            if local_name not in branches["local"]:
                                yield Hit(
                                    score,
                                    matcher.highlight(f"  {branch} (remote)"),
                                    lambda b=branch: app._do_checkout_branch(b, True),
                                    help="Remote branch - will create local tracking branch",
                                )

            # Show branch selection palette
            self.push_screen(CommandPalette(providers=[BranchProvider]))

        except Exception as e:
            self.notify(f"Failed to show branches: {e}", severity="error")

    def _do_checkout_branch(self, branch: str, is_remote: bool) -> None:
        """Actually perform the branch checkout.

        Args:
            branch: Branch name to checkout
            is_remote: Whether this is a remote branch
        """
        if not self.git_root:
            self.notify("Not in a git repository", severity="error")
            return

        try:
            from .git_utils import git_checkout_branch, git_checkout_remote_branch

            if is_remote:
                success, message = git_checkout_remote_branch(self.git_root, branch)
            else:
                success, message = git_checkout_branch(self.git_root, branch)

            if success:
                self.notify(message, severity="information")
                # Reload the directory tree to reflect branch changes
                self._reload_tree()
                # Refresh git info to update header
                self._update_git_info()
            else:
                self.notify(message, severity="error")
        except Exception as e:
            self.notify(f"Checkout failed: {e}", severity="error")

    def _change_theme(self, theme_name: str) -> None:
        """Change the application theme."""
        try:
            self.theme = theme_name
            self.notify(f"Theme changed to {theme_name}")
            # Re-render content with new syntax theme
            self._update_content_display()
        except Exception as e:
            self.notify(f"Failed to change theme: {e}", severity="error")


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
