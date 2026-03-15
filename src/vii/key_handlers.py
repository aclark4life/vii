"""Key handling mixin for the vii application."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import events
from textual.widgets import Input

if TYPE_CHECKING:
    from textual.containers import ScrollableContainer
    from textual.widgets import DirectoryTree


class KeyHandlersMixin:
    """Mixin providing key handling functionality for the Vii app.

    This mixin expects to be used with a class that has the following attributes
    and methods from other mixins or the main class. The type hints below are
    for documentation only - the actual implementations come from other mixins
    or the main class.
    """

    # Type hints for attributes (for IDE support only - not actual attributes)
    if TYPE_CHECKING:
        focused: Any
        git_log_viewing: bool
        git_log_entries: list[tuple[int, int]]
        git_log_highlighted_entry: int
        git_commit_viewing: bool
        git_commit_hash: str
        git_blame_viewing: bool
        git_blame_output: str
        git_blame_highlighted_line: int
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

        def _get_tree(self) -> "DirectoryTree | None": ...
        def _get_scroll_container(self) -> "ScrollableContainer | None": ...
        def _get_content_display(self) -> Any: ...
        def _schedule_content_update(self) -> None: ...
        def _render_log_with_highlight(self) -> None: ...
        def _scroll_to_log_entry(self) -> None: ...
        def _render_blame_with_highlight(self) -> None: ...
        def _scroll_to_blame_line(self) -> None: ...
        def _render_dir_listing_with_highlight(self) -> None: ...
        def _scroll_to_dir_entry(self) -> None: ...
        def _render_file_content_with_highlight(self) -> None: ...
        def _scroll_to_content_line(self) -> None: ...
        def _show_content_search(self) -> None: ...
        def _goto_next_match(self) -> None: ...
        def _goto_previous_match(self) -> None: ...
        def _update_content_display(self) -> None: ...
        def _navigate_to_path(self, path: Path) -> None: ...
        def _show_git_commit(self) -> None: ...
        def _git_log(self, page: int = 0) -> None: ...
        def action_git_log(self) -> None: ...
        def call_after_refresh(self, callback: Any) -> None: ...
        def _show_sidebar_search(self) -> None: ...
        def _hide_sidebar_search(self) -> None: ...
        def _goto_next_sidebar_match(self) -> None: ...
        def _goto_previous_sidebar_match(self) -> None: ...

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
                self._handle_content_key(action_key, scroll_container)
            else:
                self._handle_tree_key(action_key, tree, scroll_container)
        elif event.key in arrow_keys:
            if content_focused:
                self._handle_content_arrow_key(event, scroll_container)
            else:
                # Arrow keys are handled by the tree widget, but we still need to update display
                # Use call_after_refresh to ensure the tree has processed the key first
                self.call_after_refresh(self._schedule_content_update)
        elif event.key in ("ctrl+f", "ctrl+d", "d"):
            # Page down (vim-style)
            event.prevent_default()
            if content_focused:
                # Move cursor by page in file content view
                if (
                    self.original_content
                    and self._displayed_path
                    and self._displayed_path.is_file()
                    and not self.git_log_viewing
                    and not self.git_blame_viewing
                    and not self._dir_listing_entries
                ):
                    lines = self.original_content.split("\n")
                    page_size = max(1, scroll_container.size.height - 2)
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
        elif event.key in ("ctrl+b", "ctrl+u", "u"):
            # Page up (vim-style)
            event.prevent_default()
            if content_focused:
                # Move cursor by page in file content view
                if (
                    self.original_content
                    and self._displayed_path
                    and self._displayed_path.is_file()
                    and not self.git_log_viewing
                    and not self.git_blame_viewing
                    and not self._dir_listing_entries
                ):
                    page_size = max(1, scroll_container.size.height - 2)
                    new_line = max(0, self._content_highlighted_line - page_size)
                    self._content_highlighted_line = new_line
                    self._render_file_content_with_highlight()
                    self._scroll_to_content_line()
                else:
                    scroll_container.scroll_page_up()
            else:
                tree.action_page_up()
        elif content_focused and event.key == "/":
            # Open content search
            event.prevent_default()
            self._show_content_search()
        elif content_focused and event.key == "n":
            event.prevent_default()
            # Check if viewing git log
            if self.git_log_viewing:
                # Next page of git log
                self._git_log(getattr(self, "git_log_page", 0) + 1)
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
            git_log_page = getattr(self, "git_log_page", 0)
            if self.git_log_viewing and git_log_page > 0:
                # Previous page of git log
                self._git_log(git_log_page - 1)
        elif content_focused and event.key == "escape":
            self._handle_escape_key(event, tree, scroll_container)
        elif content_focused and event.key == "H":
            # H scrolls left more in content panel
            event.prevent_default()
            if scroll_container.allow_horizontal_scroll:
                scroll_container.scroll_left()
        elif content_focused and event.key == "L":
            # L scrolls right more in content panel
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
                tree.focus()
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
            if self.git_commit_viewing:
                scroll_container.scroll_down()
            elif self.git_log_viewing and self.git_log_entries:
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
                    self._scroll_to_blame_line()
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
            if self.git_commit_viewing:
                scroll_container.scroll_up()
            elif self.git_log_viewing and self.git_log_entries:
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
                    self._scroll_to_blame_line()
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
            if self.git_commit_viewing:
                scroll_container.scroll_home()
            elif self.git_log_viewing and self.git_log_entries:
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
            elif self.original_content and self._displayed_path and self._displayed_path.is_file():
                self._content_highlighted_line = 0
                self._render_file_content_with_highlight()
                scroll_container.scroll_home()
            else:
                scroll_container.scroll_home()
        elif action_key == "end":
            # When viewing a commit, just scroll (don't navigate log entries)
            if self.git_commit_viewing:
                scroll_container.scroll_end()
            elif self.git_log_viewing and self.git_log_entries:
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
            elif self.original_content and self._displayed_path and self._displayed_path.is_file():
                lines = self.original_content.split("\n")
                self._content_highlighted_line = len(lines) - 1
                self._render_file_content_with_highlight()
                scroll_container.scroll_end()
            else:
                scroll_container.scroll_end()
        elif action_key == "right":
            # l navigates back through git views or toggles git log
            if self.git_commit_viewing:
                # Go back to git log view
                self.git_commit_viewing = False
                self.git_commit_hash = ""
                self._render_log_with_highlight()
                self._scroll_to_log_entry()
            elif self.git_log_viewing:
                # Close git log and restore file content
                self.action_git_log()
            else:
                # Toggle git log on
                self.action_git_log()
        elif action_key == "left":
            # h scrolls left in content panel
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
            if self.git_commit_viewing:
                scroll_container.scroll_down()
            elif self.git_log_viewing and self.git_log_entries:
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
            # When viewing a commit, just scroll (don't navigate log entries)
            if self.git_commit_viewing:
                scroll_container.scroll_up()
            elif self.git_log_viewing and self.git_log_entries:
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

    def _handle_escape_key(self, event: events.Key, tree: Any, scroll_container: Any) -> None:
        """Handle ESC key in content panel."""
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

    def action_select_or_toggle_focus(self) -> None:
        """Handle Enter key - select item or toggle focus between panels."""
        tree = self._get_tree()
        scroll_container = self._get_scroll_container()
        if not tree or not scroll_container:
            return

        content_focused = scroll_container.has_focus

        if content_focused:
            # In content panel: handle special views or switch back to sidebar
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
                tree.focus()
        else:
            # In sidebar: toggle directory or switch to content panel
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                if path.is_dir():
                    # Toggle directory expansion
                    if tree.cursor_node.is_expanded:
                        tree.cursor_node.collapse()
                    else:
                        tree.cursor_node.expand()
                else:
                    # For files, switch focus to content panel and show line highlight
                    scroll_container.focus()
                    if (
                        self.original_content
                        and self._displayed_path
                        and self._displayed_path.is_file()
                    ):
                        self._render_file_content_with_highlight()
            else:
                # No node selected, switch focus to content panel
                scroll_container.focus()
