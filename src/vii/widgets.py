"""Custom widgets for vii."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual import events
from textual.binding import Binding, BindingType
from textual.command import CommandPalette as TextualCommandPalette
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Button, DirectoryTree

if TYPE_CHECKING:
    from textual.app import ComposeResult


# Import CommandInput from textual.command so we can use it in compose
from textual.command import CommandInput as CustomCommandInput


class CommandPalette(TextualCommandPalette):
    """Custom CommandPalette that supports j/k navigation and Enter to submit."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "ctrl+end, shift+end",
            "command_list('last')",
            "Go to bottom",
            show=False,
        ),
        Binding(
            "ctrl+home, shift+home",
            "command_list('first')",
            "Go to top",
            show=False,
        ),
        Binding("down,tab", "cursor_down", "Next command", show=False, priority=True),
        Binding("escape", "escape", "Exit the command palette"),
        Binding("pagedown", "command_list('page_down')", "Next page", show=False),
        Binding("pageup", "command_list('page_up')", "Previous page", show=False),
        Binding(
            "up,shift+tab",
            "command_list('cursor_up')",
            "Previous command",
            show=False,
            priority=True,
        ),
        Binding("enter", "select_or_submit", "Select/Submit", show=False, priority=True),
    ]
    """Extended bindings that add j/k navigation and enter handling."""

    def on_key(self, event: events.Key) -> None:
        """Handle key events, especially ESC to close the palette."""
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.dismiss()

    def action_escape(self) -> None:
        """Handle ESC key - close the command palette."""
        self.dismiss()

    def action_select_or_submit(self) -> None:
        """Handle Enter key - select highlighted option or submit input."""
        from textual.command import CommandList

        # Check if the list is visible and has a highlighted option
        if self._list_visible:
            command_list = self.query_one(CommandList)
            # If something is highlighted, select it
            if command_list.highlighted is not None:
                self._action_command_list("select")
            # If nothing is highlighted but there are options, highlight the first one
            elif command_list.option_count > 0:
                self._action_cursor_down()
                # If there's only one option, select it
                if command_list.option_count == 1:
                    self._action_command_list("select")
        else:
            # List not visible, trigger the normal submit behavior
            # Simulate an Input.Submitted event
            from textual.widgets import Input

            input_widget = self.query_one(Input)
            self.post_message(Input.Submitted(input_widget, input_widget.value))

    def compose(self) -> ComposeResult:
        """Compose the command palette with our custom input."""
        from textual.command import CommandList, SearchIcon
        from textual.containers import Horizontal, Vertical
        from textual.widgets import LoadingIndicator

        with Vertical(id="--container"):
            with Horizontal(id="--input"):
                yield SearchIcon()
                yield CustomCommandInput(placeholder=self._placeholder, select_on_focus=False)
                if not self.run_on_select:
                    yield Button("\u25b6")
            with Vertical(id="--results"):
                yield CommandList()
                yield LoadingIndicator()


class GitDirectoryTree(DirectoryTree):
    """DirectoryTree with git status indicators."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.git_file_status: dict[str, str] = {}
        # Cache for path -> relative path mapping (avoid repeated computation)
        self._rel_path_cache: dict[Path, str | None] = {}
        # Cache for path -> pre-rendered status indicator (avoid re-creating Text objects)
        self._status_indicator_cache: dict[Path, Text | None] = {}
        self._tree_root: Path | None = None

    def _get_rel_path(self, path: Path) -> str | None:
        """Get cached relative path for a file."""
        if path in self._rel_path_cache:
            return self._rel_path_cache[path]

        # Lazily initialize tree root
        if self._tree_root is None:
            self._tree_root = Path(self.path)

        try:
            rel_path = str(path.relative_to(self._tree_root))
            self._rel_path_cache[path] = rel_path
            return rel_path
        except (ValueError, AttributeError):
            self._rel_path_cache[path] = None
            return None

    def _build_status_indicator(self, status_code: str) -> Text:
        """Build a Text object for a git status code.

        Args:
            status_code: Git status code (e.g., 'M ', 'A ', '??')

        Returns:
            Pre-rendered Text object with status indicator
        """
        # Map status codes to indicators (pre-rendered Text objects)
        if "M" in status_code:
            return Text("~", style="yellow") + Text(" ")
        elif "A" in status_code:
            return Text("+", style="green") + Text(" ")
        elif "D" in status_code:
            return Text("-", style="red")
        elif "?" in status_code:
            return Text("?", style="cyan") + Text(" ")
        return Text("")

    def update_git_status_cache(self) -> None:
        """Pre-compute status indicators for all files with git status.

        Call this after updating git_file_status to rebuild the cache.
        This avoids computing status on every render.
        """
        self._status_indicator_cache.clear()

        if not self.git_file_status:
            return

        # Lazily initialize tree root
        if self._tree_root is None:
            self._tree_root = Path(self.path)

        # Pre-compute status indicators for all tracked files
        for rel_path, status_code in self.git_file_status.items():
            try:
                abs_path = self._tree_root / rel_path
                self._status_indicator_cache[abs_path] = self._build_status_indicator(status_code)
            except Exception:
                # Skip files that can't be resolved
                pass

    def clear_path_cache(self) -> None:
        """Clear all caches (call when tree root changes)."""
        self._rel_path_cache.clear()
        self._status_indicator_cache.clear()
        self._tree_root = None

    def render_label(self, node, base_style, style):
        """Render a label with git status indicator.

        This method is called on every render for every visible node,
        so it's optimized to use pre-computed status indicators from cache.
        """
        label = super().render_label(node, base_style, style)

        # Quick exit if no git status data
        if not self._status_indicator_cache:
            return label

        # Add git status indicator if available (from pre-computed cache)
        if node.data and hasattr(node.data, "path"):
            path = node.data.path
            # O(1) lookup in pre-computed cache (no path computation, no Text creation)
            status_indicator = self._status_indicator_cache.get(path)
            if status_indicator:
                label = status_indicator + label

        return label


class VerticalSplitter(Widget):
    """A draggable vertical splitter for resizing panels."""

    DEFAULT_CSS = """
    VerticalSplitter {
        width: 1;
        height: 100%;
        background: $primary;
        content-align: center middle;
    }

    VerticalSplitter:hover {
        background: $accent;
        pointer: ew-resize;
    }

    VerticalSplitter.-dragging {
        background: white;
    }
    """

    is_dragging: reactive[bool] = reactive(False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._drag_start_x: int = 0

    def render(self) -> str:
        """Render the splitter."""
        return "┃"

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Start dragging when mouse is pressed."""
        self.is_dragging = True
        self._drag_start_x = event.screen_x
        self.capture_mouse()
        self.add_class("-dragging")
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """Stop dragging when mouse is released."""
        if self.is_dragging:
            self.is_dragging = False
            self.release_mouse()
            self.remove_class("-dragging")
            event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Handle mouse movement during drag."""
        if self.is_dragging:
            # Calculate the new sidebar width based on mouse position
            app = self.app
            if hasattr(app, "set_sidebar_width"):
                new_width = int(event.screen_x)
                app.set_sidebar_width(new_width)
            event.stop()
