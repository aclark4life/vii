"""Main application entry point for vii."""

import os
import subprocess
import sys
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DirectoryTree, Footer, Header, Static


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

    .info-text {
        color: $text-muted;
        text-style: italic;
    }

    #content-display {
        padding: 2;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
        # Vi-style navigation (shown in footer)
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("h", "cursor_left", "Collapse"),
        Binding("l", "cursor_right", "Expand"),
        Binding("g", "scroll_home", "Top"),
        Binding("G", "scroll_end", "Bottom"),
        # Arrow keys still work but hidden from footer
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("left", "cursor_left", "Left", show=False),
        Binding("right", "cursor_right", "Right", show=False),
    ]

    def __init__(self, start_path: Path | None = None):
        super().__init__()
        self.start_path = start_path or Path.cwd()
        self.editor_command = self._detect_editor()
        self.is_terminal_editor = self._is_terminal_editor()

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
            yield Static(
                "📁 Navigate with j/k to see folder/file icons",
                id="content-display",
            )

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

                if path.is_dir():
                    # Display folder icon for directories
                    content_display.update(f"[bold]📁 {path.name}[/bold]\n\n[dim]Directory[/dim]")
                else:
                    # For files, show file icon, name, and contents
                    content = self._read_file_content(path)
                    content_display.update(f"[bold]📄 {path.name}[/bold]\n\n{content}")
        except Exception:
            pass

    def on_key(self, event: events.Key) -> None:
        """Handle key presses for vi-style navigation."""
        tree = self.query_one(DirectoryTree)

        # Map vi keys to actions
        key_map = {
            "j": "down",
            "k": "up",
            "h": "left",
            "l": "right",
            "g": "home",
            "G": "end",
        }

        # Arrow keys that should also update the display
        arrow_keys = {"up", "down", "left", "right"}

        if event.key in key_map:
            # Prevent the key from being processed further
            event.prevent_default()
            # Simulate the corresponding arrow key or action
            action_key = key_map[event.key]
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
        elif event.key in arrow_keys:
            # Arrow keys are handled by the tree widget, but we still need to update display
            # Use call_after_refresh to ensure the tree has processed the key first
            self.call_after_refresh(self._update_content_display)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection from the directory tree."""
        file_path = event.path
        self._open_in_editor(file_path)

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
