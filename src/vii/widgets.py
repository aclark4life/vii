"""Custom widgets for vii."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text
from textual import events
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DirectoryTree

if TYPE_CHECKING:
    pass


class GitDirectoryTree(DirectoryTree):
    """DirectoryTree with git status indicators."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.git_file_status: dict[str, str] = {}
        # Cache for path -> relative path mapping (avoid repeated computation)
        self._rel_path_cache: dict[Path, str | None] = {}
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

    def clear_path_cache(self) -> None:
        """Clear the relative path cache (call when tree root changes)."""
        self._rel_path_cache.clear()
        self._tree_root = None

    def render_label(self, node, base_style, style):
        """Render a label with git status indicator."""
        label = super().render_label(node, base_style, style)

        # Quick exit if no git status data
        if not self.git_file_status:
            return label

        # Add git status indicator if available
        if node.data and hasattr(node.data, "path"):
            path = node.data.path
            # Use cached relative path lookup
            rel_path = self._get_rel_path(path)
            if rel_path and rel_path in self.git_file_status:
                status_code = self.git_file_status[rel_path]
                # Map status codes to indicators
                if "M" in status_code:
                    label = Text("~", style="yellow") + Text(" ") + label
                elif "A" in status_code:
                    label = Text("+", style="green") + Text(" ") + label
                elif "D" in status_code:
                    label = Text("-", style="red") + label
                elif "?" in status_code:
                    label = Text("?", style="cyan") + Text(" ") + label

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
        background: $accent;
        pointer: ew-resize;
    }

    VerticalSplitter.-active {
        background: $accent;
        pointer: ew-resize;
    }
    """

    is_dragging: reactive[bool] = reactive(False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._drag_start_x: int = 0
        self._did_drag: bool = False  # Track if actual dragging occurred

    def render(self) -> str:
        """Render the splitter."""
        return "┃"

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Start dragging when mouse is pressed."""
        self.is_dragging = True
        self._did_drag = False  # Reset drag tracking
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
            # If we actually dragged, keep the active state
            if self._did_drag:
                self.add_class("-active")
            else:
                # Just a click - toggle active state
                if self.has_class("-active"):
                    self.remove_class("-active")
                else:
                    self.add_class("-active")
            event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Handle mouse movement during drag."""
        if self.is_dragging:
            self._did_drag = True  # Mark that actual dragging occurred
            # Calculate the new sidebar width based on mouse position
            app = self.app
            if hasattr(app, "set_sidebar_width"):
                new_width = int(event.screen_x)
                app.set_sidebar_width(new_width)
            event.stop()
