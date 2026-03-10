"""Main application entry point for vii."""

import os
import re
import subprocess
import sys
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import DirectoryTree, Footer, Header, Input, Static


class Vii(App):
    """vii - Terminal file browser."""

    TITLE = "vii"

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 1;
        grid-columns: 1fr 2fr;
    }

    #sidebar {
        width: 100%;
        height: 100%;
        border-right: solid $primary;
    }

    #main-content {
        width: 100%;
        height: 100%;
    }

    DirectoryTree {
        width: 100%;
        height: 100%;
    }

    DirectoryTree:focus {
        border: solid $primary;
    }

    .info-text {
        color: $text-muted;
        text-style: italic;
    }

    #content-scroll {
        width: 100%;
        height: 100%;
    }

    #content-scroll:focus {
        border: solid $primary;
    }

    #content-display {
        padding: 1 2;
    }

    #search-container {
        dock: bottom;
        height: auto;
        display: none;
    }

    #search-container.visible {
        display: block;
    }

    #search-input {
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
        # Vi-style navigation (shown in footer)
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("h", "cursor_left", "Collapse"),
        Binding("l", "cursor_right", "Expand"),
        Binding("g", "scroll_home", "Top"),
        Binding("G", "scroll_end", "Bottom"),
        Binding("e", "edit_file", "Edit"),
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
        self.start_path = start_path or Path.cwd()
        self.editor_command = self._detect_editor()
        self.is_terminal_editor = self._is_terminal_editor()
        # Search state
        self.search_query = ""
        self.search_matches: list[int] = []  # Line numbers with matches
        self.current_match_index = -1
        self.original_content = ""  # Content without highlighting

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
            yield DirectoryTree(str(self.start_path))

        with Vertical(id="main-content"):
            with ScrollableContainer(id="content-scroll", can_focus=True):
                yield Static(
                    "📁 Navigate with j/k to see folder/file icons\n\n"
                    "Press Tab to switch focus between panels.\n"
                    "Use Page Up/Down or mouse wheel to scroll content.\n"
                    "Press / to search in file content.",
                    id="content-display",
                )
            with Horizontal(id="search-container"):
                yield Input(placeholder="Search...", id="search-input")

        yield Footer()

    def _read_file_content(self, path: Path, max_size: int = 100000) -> str:
        """Read file content, handling binary files and size limits."""
        try:
            # Check file size first
            file_size = path.stat().st_size
            if file_size > max_size:
                return f"[dim]File too large to preview ({file_size:,} bytes)[/dim]"

            # Try to read as text
            content = path.read_text(encoding="utf-8")
            return content
        except UnicodeDecodeError:
            return "[dim]Binary file - cannot preview[/dim]"
        except PermissionError:
            return "[dim]Permission denied[/dim]"
        except Exception as e:
            return f"[dim]Cannot read file: {e}[/dim]"

    def _update_content_display(self) -> None:
        """Update the content display based on the currently highlighted tree node."""
        try:
            tree = self.query_one(DirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                content_display = self.query_one("#content-display", Static)
                scroll_container = self.query_one("#content-scroll", ScrollableContainer)

                if path.is_dir():
                    # Display folder icon for directories
                    content_display.update(f"[bold]📁 {path.name}[/bold]\n\n[dim]Directory[/dim]")
                    self.original_content = ""
                else:
                    # For files, show file icon, name, and contents
                    content = self._read_file_content(path)
                    self.original_content = content
                    content_display.update(f"[bold]📄 {path.name}[/bold]\n\n{content}")

                # Reset scroll position to top when content changes
                scroll_container.scroll_home(animate=False)
                # Clear search matches when file changes
                self.search_matches = []
                self.current_match_index = -1
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle key presses for vi-style navigation."""
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
                    tree.action_cursor_left()
                elif action_key == "right":
                    tree.action_cursor_right()
                elif action_key == "home":
                    tree.action_scroll_home()
                elif action_key == "end":
                    tree.action_scroll_end()

                # Update the content display after cursor movement
                self._update_content_display()
        elif event.key in arrow_keys and not content_focused:
            # Arrow keys are handled by the tree widget, but we still need to update display
            # Use call_after_refresh to ensure the tree has processed the key first
            self.call_after_refresh(self._update_content_display)
        elif content_focused and event.key in ("ctrl+f", "ctrl+d"):
            # Page down in content panel (vim-style)
            event.prevent_default()
            scroll_container.scroll_page_down()
        elif content_focused and event.key in ("ctrl+b", "ctrl+u"):
            # Page up in content panel (vim-style)
            event.prevent_default()
            scroll_container.scroll_page_up()
        elif content_focused and event.key == "slash":
            # Open search
            event.prevent_default()
            self._show_search()
        elif content_focused and event.key == "n":
            # Next search match
            event.prevent_default()
            self._goto_next_match()
        elif content_focused and event.key == "N":
            # Previous search match
            event.prevent_default()
            self._goto_previous_match()
        elif content_focused and event.key == "escape":
            # Clear search and highlights
            event.prevent_default()
            self._hide_search(clear_highlights=True)
            self.search_matches = []
            self.current_match_index = -1
            self.search_query = ""

    def _show_search(self) -> None:
        """Show the search input."""
        search_container = self.query_one("#search-container")
        search_container.add_class("visible")
        search_input = self.query_one("#search-input", Input)
        search_input.value = self.search_query
        search_input.focus()

    def _hide_search(self, clear_highlights: bool = False) -> None:
        """Hide the search input."""
        search_container = self.query_one("#search-container")
        search_container.remove_class("visible")
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        scroll_container.focus()
        if clear_highlights:
            self._clear_search_highlights()

    def _clear_search_highlights(self) -> None:
        """Remove search highlighting from content."""
        if self.original_content:
            content_display = self.query_one("#content-display", Static)
            tree = self.query_one(DirectoryTree)
            if tree.cursor_node and tree.cursor_node.data:
                path = tree.cursor_node.data.path
                if path.is_file():
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
        content = self._read_file_content(path)
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

        # Build Rich Text object with highlighting
        text = Text()
        text.append(f"📄 {path.name}\n\n", style="bold")

        # Styles for highlighting
        current_style = Style(color="black", bgcolor="bright_green")
        other_style = Style(color="black", bgcolor="yellow")

        last_end = 0
        match_count = 0

        for match in re.finditer(re.escape(self.search_query), content, flags=re.IGNORECASE):
            # Add text before match (no style)
            text.append(content[last_end : match.start()])

            # Add highlighted match
            if match_count == self.current_match_index:
                text.append(match.group(), style=current_style)
            else:
                text.append(match.group(), style=other_style)

            last_end = match.end()
            match_count += 1

        # Add remaining text
        text.append(content[last_end:])

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
        if event.input.id == "search-input":
            self._perform_search(event.value)
            self._hide_search()

    def action_page_up(self) -> None:
        """Scroll the content panel up by one page."""
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        scroll_container.scroll_page_up()

    def action_page_down(self) -> None:
        """Scroll the content panel down by one page."""
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        scroll_container.scroll_page_down()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from the directory tree - switch to content panel."""
        # Update content display and switch focus to content panel
        self._update_content_display()
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        scroll_container.focus()

    def action_edit_file(self) -> None:
        """Open the currently selected file in the editor."""
        tree = self.query_one(DirectoryTree)
        if tree.cursor_node and tree.cursor_node.data:
            path = tree.cursor_node.data.path
            if path.is_file():
                self._open_in_editor(path)
            else:
                self.notify("Cannot edit a directory", severity="warning")

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
