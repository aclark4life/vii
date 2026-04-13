"""Key handling mixin for the vii application."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import events
from textual.containers import ScrollableContainer
from textual.widgets import DirectoryTree, Input, Static

from .git_state import GitState

if TYPE_CHECKING:
    # Import for documentation - the protocol defines the contract
    pass


class KeyHandlersMixin:
    """Mixin providing key handling functionality for the Vii app.

    This mixin requires the host class to implement ViiProtocol.
    The type stubs below ensure type safety - they match the protocol definition.
    """

    # Attributes from ViiProtocol (provided by host class)
    focused: Any
    git: GitState
    search_query: str
    search_matches: list[int]
    _dir_listing_entries: list[Path]
    _dir_listing_highlighted: int
    _content_highlighted_line: int
    _displayed_path: Path | None
    original_content: str
    sidebar_search_query: str
    sidebar_search_matches: list[Any]
    sidebar_current_match_index: int

    # Methods from ViiProtocol (provided by host class)
    # NOTE: Only stub methods defined in Vii (app.py) here. Do NOT stub methods
    # from GitHandlersMixin or Textual framework methods — stubs are real Python
    # methods that shadow implementations later in the MRO (KeyHandlersMixin comes
    # before GitHandlersMixin and App). See commit bcd9776 / fa2be3a.
    def _get_tree(self) -> DirectoryTree | None: ...
    def _get_scroll_container(self) -> ScrollableContainer | None: ...
    def _get_content_display(self) -> Static | None: ...
    def _schedule_content_update(self) -> None: ...
    def _render_dir_listing_with_highlight(self) -> None: ...
    def _scroll_to_dir_entry(self) -> None: ...
    def _render_file_content_with_highlight(self) -> None: ...
    def _scroll_to_content_line(self) -> None: ...
    def _show_content_search(self) -> None: ...
    def _hide_content_search(self) -> None: ...
    def _perform_search(self, query: str) -> None: ...
    def _goto_next_match(self) -> None: ...
    def _goto_previous_match(self) -> None: ...
    def _goto_next_git_log_match(self) -> None: ...
    def _goto_previous_git_log_match(self) -> None: ...
    def _goto_next_git_blame_match(self) -> None: ...
    def _goto_previous_git_blame_match(self) -> None: ...
    def _update_content_display(self) -> None: ...
    def _do_content_update(self) -> None: ...
    def _navigate_to_path(self, path: Path) -> None: ...
    def action_git_log(self) -> None: ...
    def notify(self, *args: Any, **kwargs: Any) -> None: ...
    def _show_sidebar_search(self) -> None: ...
    def _hide_sidebar_search(self) -> None: ...
    def _perform_sidebar_search(self, query: str) -> None: ...
    def _goto_next_sidebar_match(self) -> None: ...
    def _goto_previous_sidebar_match(self) -> None: ...

    def on_key(self, event: events.Key) -> None:
        """Handle key presses for vi-style navigation."""
        # Handle keys when an Input widget has focus
        if self.focused and isinstance(self.focused, Input):
            if event.key == "escape":
                # Cancel search and hide input
                event.prevent_default()
                if self.focused.id == "content-search-input":
                    self._hide_content_search()
                elif self.focused.id == "sidebar-search-input":
                    self._hide_sidebar_search()
            elif event.key == "enter":
                # Submit search - manually trigger the submission
                event.prevent_default()
                input_widget = self.focused
                if input_widget.id == "content-search-input":
                    query = input_widget.value
                    self.notify(f"Searching for: {query}")  # Debug
                    self._perform_search(query)
                    self._hide_content_search()
                elif input_widget.id == "sidebar-search-input":
                    query = input_widget.value
                    self.notify(f"Searching sidebar for: {query}")  # Debug
                    self._perform_sidebar_search(query)
                    self._hide_sidebar_search()
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
        }

        # Arrow keys
        arrow_keys = {"up", "down", "left", "right"}

        if event.key in key_map:
            event.prevent_default()
            action_key = key_map[event.key]

            if content_focused:
                self._handle_content_key(action_key, scroll_container)
            else:
                self._handle_tree_key(action_key, tree, scroll_container)
        elif event.key in arrow_keys:
            if content_focused:
                self._handle_content_arrow_key(event, scroll_container)
            else:
                # Arrow keys are handled by the tree widget, but we still need to update display
                # Use call_after_refresh to ensure the tree has processed the key first
                self.call_after_refresh(self._schedule_content_update)  # type: ignore[attr-defined]
        elif event.key in ("ctrl+f", "ctrl+d"):
            # Page down (vim-style)
            event.prevent_default()
            if content_focused:
                # Move cursor by page in file content view
                if (
                    self.original_content
                    and self._displayed_path
                    and self._displayed_path.is_file()
                    and not self.git.log_viewing
                    and not self.git.blame_viewing
                    and not self._dir_listing_entries
                ):
                    lines = self.original_content.split("\n")
                    page_size = max(1, scroll_container.size.height - 2)

                    # If no line is highlighted yet, start from the top visible line
                    if self._content_highlighted_line < 0:
                        # Account for header lines (2 lines: filename + empty line)
                        current_line = max(0, int(scroll_container.scroll_y) - 2)
                        self._content_highlighted_line = current_line

                    new_line = min(
                        len(lines) - 1,
                        self._content_highlighted_line + page_size,
                    )
                    self._content_highlighted_line = new_line
                    self._render_file_content_with_highlight()
                    self._scroll_to_content_line()
                else:
                    scroll_container.scroll_page_down()
            else:
                tree.action_page_down()
        elif event.key in ("ctrl+b", "ctrl+u"):
            # Page up (vim-style)
            event.prevent_default()
            if content_focused:
                # Move cursor by page in file content view
                if (
                    self.original_content
                    and self._displayed_path
                    and self._displayed_path.is_file()
                    and not self.git.log_viewing
                    and not self.git.blame_viewing
                    and not self._dir_listing_entries
                ):
                    page_size = max(1, scroll_container.size.height - 2)

                    # If no line is highlighted yet, start from the top visible line
                    if self._content_highlighted_line < 0:
                        # Account for header lines (2 lines: filename + empty line)
                        current_line = max(0, int(scroll_container.scroll_y) - 2)
                        self._content_highlighted_line = current_line

                    new_line = max(0, self._content_highlighted_line - page_size)
                    self._content_highlighted_line = new_line
                    self._render_file_content_with_highlight()
                    self._scroll_to_content_line()
                else:
                    scroll_container.scroll_page_up()
            else:
                tree.action_page_up()
        elif content_focused and event.key == "slash":
            # Open content search (works in files, git log, and git blame)
            event.prevent_default()
            self._show_content_search()
        elif content_focused and event.key == "n":
            event.prevent_default()
            # Check if searching in git log
            if self.git.log_viewing and self.git.log_search_query:
                self._goto_next_git_log_match()
            # Check if searching in git blame
            elif self.git.blame_viewing and self.git.blame_search_query:
                self._goto_next_git_blame_match()
            # Check if viewing git log (without search) - navigate pages
            elif self.git.log_viewing:
                self._git_log(getattr(self, "git_log_page", 0) + 1)  # type: ignore[attr-defined]
            else:
                # Next search match in file
                self._goto_next_match()
        elif content_focused and event.key == "N":
            # Previous search match
            event.prevent_default()
            # Check if searching in git log
            if self.git.log_viewing and self.git.log_search_query:
                self._goto_previous_git_log_match()
            # Check if searching in git blame
            elif self.git.blame_viewing and self.git.blame_search_query:
                self._goto_previous_git_blame_match()
            else:
                # Previous search match in file
                self._goto_previous_match()
        elif content_focused and event.key == "p":
            event.prevent_default()
            # Check if viewing git log
            git_log_page = getattr(self, "git_log_page", 0)
            if self.git.log_viewing and git_log_page > 0:
                # Previous page of git log
                self._git_log(git_log_page - 1)  # type: ignore[attr-defined]
        elif content_focused and event.key == "escape":
            self._handle_escape_key(event, tree, scroll_container)
        elif content_focused and event.key == "H":
            # H scrolls left in content panel (large movement)
            event.prevent_default()
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_left()
        elif content_focused and event.key == "L":
            # L scrolls right in content panel (large movement)
            event.prevent_default()
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_right()
        elif content_focused and event.key == "enter":
            event.prevent_default()
            if self.git.log_viewing and not self.git.commit_viewing:
                # Show the highlighted commit details
                self._show_git_commit()  # type: ignore[attr-defined]
            elif self.git.blame_viewing and not self.git.commit_viewing:
                # Show the commit for the highlighted blame line
                self._show_blame_commit()  # type: ignore[attr-defined]
            elif self._dir_listing_entries and 0 <= self._dir_listing_highlighted < len(
                self._dir_listing_entries
            ):
                # Navigate to the highlighted directory entry
                clicked_path = self._dir_listing_entries[self._dir_listing_highlighted]
                self._navigate_to_path(clicked_path)
            else:
                # Scroll down one line (like a pager)
                scroll_container.scroll_down()
        elif not content_focused and event.key == "enter":
            # In sidebar: toggle dirs, switch focus for files
            event.prevent_default()
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                if path.is_dir():
                    # Toggle directory expansion
                    if tree.cursor_node.is_expanded:
                        tree.cursor_node.collapse()
                    else:
                        tree.cursor_node.expand()
                else:
                    # For files: update content and switch focus to content panel
                    self._do_content_update()
                    scroll_container.focus()
        # Sidebar-specific key handling (when sidebar has focus)
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

    def _handle_content_key(self, action_key: str, scroll_container: Any) -> None:
        """Handle vi key in content panel."""
        if action_key == "down":
            # When viewing a commit, just scroll (don't navigate log entries)
            if self.git.commit_viewing:
                scroll_container.scroll_down()
            elif self.git.log_viewing and self.git.log_entries:
                # Move highlighted entry down in log view
                if self.git.log_highlighted_entry < len(self.git.log_entries) - 1:
                    self.git.log_highlighted_entry += 1
                    self._render_log_with_highlight()  # type: ignore[attr-defined]
                    self._scroll_to_log_entry()  # type: ignore[attr-defined]
            elif self.git.blame_viewing and self.git.blame_output:
                # Move highlighted line down in blame view
                lines = self.git.blame_output.split("\n")
                max_line = len(lines) - 1
                if self.git.blame_highlighted_line < max_line:
                    self.git.blame_highlighted_line += 1
                    self._render_blame_with_highlight()  # type: ignore[attr-defined]
                    self._scroll_to_blame_line()  # type: ignore[attr-defined]
            elif self._dir_listing_entries:
                # Move highlighted entry down in directory listing
                if self._dir_listing_highlighted < len(self._dir_listing_entries) - 1:
                    self._dir_listing_highlighted += 1
                    self._render_dir_listing_with_highlight()
                    self._scroll_to_dir_entry()
            elif self.original_content and self._displayed_path and self._displayed_path.is_file():
                # Move highlighted line down in file content view
                lines = self.original_content.split("\n")
                max_line = len(lines) - 1
                if self._content_highlighted_line < max_line:
                    self._content_highlighted_line += 1
                    self._render_file_content_with_highlight()
                    self._scroll_to_content_line()
            else:
                scroll_container.scroll_down()
        elif action_key == "up":
            # When viewing a commit, just scroll (don't navigate log entries)
            if self.git.commit_viewing:
                scroll_container.scroll_up()
            elif self.git.log_viewing and self.git.log_entries:
                # Move highlighted entry up in log view
                if self.git.log_highlighted_entry > 0:
                    self.git.log_highlighted_entry -= 1
                    self._render_log_with_highlight()  # type: ignore[attr-defined]
                    self._scroll_to_log_entry()  # type: ignore[attr-defined]
            elif self.git.blame_viewing and self.git.blame_output:
                # Move highlighted line up in blame view
                if self.git.blame_highlighted_line > 0:
                    self.git.blame_highlighted_line -= 1
                    self._render_blame_with_highlight()  # type: ignore[attr-defined]
                    self._scroll_to_blame_line()  # type: ignore[attr-defined]
            elif self._dir_listing_entries:
                # Move highlighted entry up in directory listing
                if self._dir_listing_highlighted > 0:
                    self._dir_listing_highlighted -= 1
                    self._render_dir_listing_with_highlight()
                    self._scroll_to_dir_entry()
            elif self.original_content and self._displayed_path and self._displayed_path.is_file():
                # Move highlighted line up in file content view
                if self._content_highlighted_line > 0:
                    self._content_highlighted_line -= 1
                    self._render_file_content_with_highlight()
                    self._scroll_to_content_line()
            else:
                scroll_container.scroll_up()
        elif action_key == "home":
            # When viewing a commit, just scroll (don't navigate log entries)
            if self.git.commit_viewing:
                scroll_container.scroll_home()
            elif self.git.log_viewing and self.git.log_entries:
                self.git.log_highlighted_entry = 0
                self._render_log_with_highlight()  # type: ignore[attr-defined]
                scroll_container.scroll_home()
            elif self.git.blame_viewing and self.git.blame_output:
                self.git.blame_highlighted_line = 0
                self._render_blame_with_highlight()  # type: ignore[attr-defined]
                scroll_container.scroll_home()
            elif self._dir_listing_entries:
                self._dir_listing_highlighted = 0
                self._render_dir_listing_with_highlight()
                scroll_container.scroll_home()
            elif self.original_content and self._displayed_path and self._displayed_path.is_file():
                self._content_highlighted_line = 0
                self._render_file_content_with_highlight()
                scroll_container.scroll_home()
            else:
                scroll_container.scroll_home()
        elif action_key == "end":
            # When viewing a commit, just scroll (don't navigate log entries)
            if self.git.commit_viewing:
                scroll_container.scroll_end()
            elif self.git.log_viewing and self.git.log_entries:
                self.git.log_highlighted_entry = len(self.git.log_entries) - 1
                self._render_log_with_highlight()  # type: ignore[attr-defined]
                scroll_container.scroll_end()
            elif self.git.blame_viewing and self.git.blame_output:
                lines = self.git.blame_output.split("\n")
                self.git.blame_highlighted_line = len(lines) - 1
                self._render_blame_with_highlight()  # type: ignore[attr-defined]
                scroll_container.scroll_end()
            elif self._dir_listing_entries:
                self._dir_listing_highlighted = len(self._dir_listing_entries) - 1
                self._render_dir_listing_with_highlight()
                scroll_container.scroll_end()
            elif self.original_content and self._displayed_path and self._displayed_path.is_file():
                lines = self.original_content.split("\n")
                self._content_highlighted_line = len(lines) - 1
                self._render_file_content_with_highlight()
                scroll_container.scroll_end()
            else:
                scroll_container.scroll_end()
        elif action_key == "right":
            # l scrolls right in content panel (small movement)
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_right()
        elif action_key == "left":
            # h scrolls left in content panel (small movement)
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_left()

    def _handle_tree_key(self, action_key: str, tree: Any, scroll_container: Any) -> None:
        """Handle vi key in tree panel."""
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
        self._schedule_content_update()

    def _handle_content_arrow_key(self, event: events.Key, scroll_container: Any) -> None:
        """Handle arrow key in content panel."""
        event.prevent_default()
        if event.key == "down":
            # When viewing a commit, just scroll (don't navigate log entries)
            if self.git.commit_viewing:
                scroll_container.scroll_down()
            elif self.git.log_viewing and self.git.log_entries:
                if self.git.log_highlighted_entry < len(self.git.log_entries) - 1:
                    self.git.log_highlighted_entry += 1
                    self._render_log_with_highlight()  # type: ignore[attr-defined]
                    self._scroll_to_log_entry()  # type: ignore[attr-defined]
            elif self.git.blame_viewing and self.git.blame_output:
                lines = self.git.blame_output.split("\n")
                max_line = len(lines) - 1
                if self.git.blame_highlighted_line < max_line:
                    self.git.blame_highlighted_line += 1
                    self._render_blame_with_highlight()  # type: ignore[attr-defined]
                    self._scroll_to_blame_line()  # type: ignore[attr-defined]
            elif self._dir_listing_entries:
                if self._dir_listing_highlighted < len(self._dir_listing_entries) - 1:
                    self._dir_listing_highlighted += 1
                    self._render_dir_listing_with_highlight()
                    self._scroll_to_dir_entry()
            elif self.original_content and self._displayed_path and self._displayed_path.is_file():
                # Move highlighted line down in file content view
                lines = self.original_content.split("\n")
                max_line = len(lines) - 1
                if self._content_highlighted_line < max_line:
                    self._content_highlighted_line += 1
                    self._render_file_content_with_highlight()
                    self._scroll_to_content_line()
            else:
                scroll_container.scroll_down()
        elif event.key == "up":
            # When viewing a commit, just scroll (don't navigate log entries)
            if self.git.commit_viewing:
                scroll_container.scroll_up()
            elif self.git.log_viewing and self.git.log_entries:
                if self.git.log_highlighted_entry > 0:
                    self.git.log_highlighted_entry -= 1
                    self._render_log_with_highlight()  # type: ignore[attr-defined]
                    self._scroll_to_log_entry()  # type: ignore[attr-defined]
            elif self.git.blame_viewing and self.git.blame_output:
                if self.git.blame_highlighted_line > 0:
                    self.git.blame_highlighted_line -= 1
                    self._render_blame_with_highlight()  # type: ignore[attr-defined]
                    self._scroll_to_blame_line()  # type: ignore[attr-defined]
            elif self._dir_listing_entries:
                if self._dir_listing_highlighted > 0:
                    self._dir_listing_highlighted -= 1
                    self._render_dir_listing_with_highlight()
                    self._scroll_to_dir_entry()
            elif self.original_content and self._displayed_path and self._displayed_path.is_file():
                # Move highlighted line up in file content view
                if self._content_highlighted_line > 0:
                    self._content_highlighted_line -= 1
                    self._render_file_content_with_highlight()
                    self._scroll_to_content_line()
            else:
                scroll_container.scroll_up()
        elif event.key == "left":
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_left()
        elif event.key == "right":
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_right()

    def _handle_escape_key(self, event: events.Key, tree: Any, scroll_container: Any) -> None:
        """Handle ESC key in content panel."""
        if self.git.commit_viewing:
            # Go back to git log or blame view
            event.prevent_default()
            self.git.commit_viewing = False
            self.git.commit_hash = ""

            # Check if we came from blame view or log view
            if self.git.blame_viewing:
                # Go back to blame view
                self._render_blame_with_highlight()  # type: ignore[attr-defined]
                self._scroll_to_blame_line()  # type: ignore[attr-defined]
            else:
                # Go back to log view
                self._render_log_with_highlight()  # type: ignore[attr-defined]
                self._scroll_to_log_entry()  # type: ignore[attr-defined]
        elif self.git.log_viewing and self.git.log_search_query:
            # Clear git log search (but stay in git log view)
            event.prevent_default()
            self.git.log_search_query = ""
            self.git.log_search_matches = []
            self.git.log_current_match_index = -1
            self._render_log_with_highlight()  # type: ignore[attr-defined]
            self.notify("Search cleared")
        elif self.git.log_viewing:
            # Close git log display and restore file content
            event.prevent_default()
            self.git.log_viewing = False
            self.git.log_page = 0
            self.git.log_output = ""
            self.git.log_entries = []
            self.git.log_highlighted_entry = -1
            self.git.log_search_query = ""
            self.git.log_search_matches = []
            self.git.log_current_match_index = -1
            self.git.commit_viewing = False
            self.git.commit_hash = ""
            self._update_content_display()
        elif self.git.blame_viewing and self.git.blame_search_query:
            # Clear git blame search (but stay in git blame view)
            event.prevent_default()
            self.git.blame_search_query = ""
            self.git.blame_search_matches = []
            self.git.blame_current_match_index = -1
            self._render_blame_with_highlight()  # type: ignore[attr-defined]
            self.notify("Search cleared")
        elif self.git.blame_viewing:
            # Close git blame display and restore file content
            event.prevent_default()
            self.git.blame_viewing = False
            self.git.blame_search_query = ""
            self.git.blame_search_matches = []
            self.git.blame_current_match_index = -1
            self._update_content_display()
        elif self.search_query or self.search_matches:
            # Clear search and highlights (only if search is active)
            event.prevent_default()
            self.search_query = ""
            self.search_matches = []
            self.current_match_index = -1
            self._update_content_display()
        else:
            # Switch focus back to sidebar and remove line highlight
            event.prevent_default()
            tree.focus()
            # Re-render file content without highlight
            if self.original_content and self._displayed_path and self._displayed_path.is_file():
                self._content_highlighted_line = -1
                self._update_content_display()

    def action_cursor_down(self) -> None:
        """Move cursor down in tree or scroll content."""
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus
        if content_focused:
            self._handle_content_key("down", scroll_container)
        else:
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
            self._handle_content_key("up", scroll_container)
        else:
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
            self._handle_content_key("home", scroll_container)
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
            self._handle_content_key("end", scroll_container)
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

    def action_select_and_focus(self) -> None:
        """Handle Enter key - toggle dirs, switch focus for files."""
        # Don't handle if an Input widget has focus (let it submit the search)
        if self.focused and isinstance(self.focused, Input):
            return

        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus

        if content_focused:
            # In content panel: handle special views
            if self.git.log_viewing and not self.git.commit_viewing:
                # Show the highlighted commit details
                self._show_git_commit()  # type: ignore[attr-defined]
            elif self.git.blame_viewing and not self.git.commit_viewing:
                # Show the commit for the highlighted blame line
                self._show_blame_commit()  # type: ignore[attr-defined]
            elif self._dir_listing_entries and 0 <= self._dir_listing_highlighted < len(
                self._dir_listing_entries
            ):
                # Navigate to the highlighted directory entry
                clicked_path = self._dir_listing_entries[self._dir_listing_highlighted]
                self._navigate_to_path(clicked_path)
        else:
            # In sidebar: toggle dirs, switch focus for files
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                if path.is_dir():
                    # Toggle directory expansion
                    if tree.cursor_node.is_expanded:
                        tree.cursor_node.collapse()
                    else:
                        tree.cursor_node.expand()
                else:
                    # For files: update content and switch focus to content panel
                    self._do_content_update()
                    scroll_container.focus()
