"""Git-related handlers for the vii application."""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text
from textual.command import Hits
from textual.containers import ScrollableContainer
from textual.widgets import DirectoryTree, Static

from vii.content import get_syntax_theme

if TYPE_CHECKING:
    from textual.screen import Screen


class GitHandlersMixin:
    """Mixin providing git-related functionality for the Vii app.

    This mixin expects to be used with a class that has the following attributes:
    - git_branch: str | None
    - git_root: Path | None
    - git_log_page: int
    - git_log_page_size: int
    - git_log_output: str
    - git_log_entries: list[tuple[int, int]]
    - git_log_highlighted_entry: int
    - git_log_viewing: bool
    - git_commit_viewing: bool
    - git_commit_hash: str
    - git_blame_output: str
    - git_blame_viewing: bool
    - git_blame_highlighted_line: int
    - theme: str
    """

    # Type hints for attributes provided by the main class
    git_branch: str | None
    git_root: Path | None
    git_log_page: int
    git_log_page_size: int
    git_log_output: str
    git_log_entries: list[tuple[int, int]]
    git_log_highlighted_entry: int
    git_log_viewing: bool
    git_commit_viewing: bool
    git_commit_hash: str
    git_blame_output: str
    git_blame_viewing: bool
    git_blame_highlighted_line: int
    theme: str

    # Methods provided by the main class
    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: float | None = None,
    ) -> None: ...
    def query_one(self, selector: Any, widget_type: type | None = None) -> Any: ...
    def push_screen(self, screen: "Screen", callback: Any = None) -> None: ...
    def _get_current_directory(self) -> Path: ...
    def _update_git_info(self, path: Path | None = None) -> None: ...
    def _update_header(self) -> None: ...
    def _reload_tree(self) -> None: ...

    """Mixin providing git-related functionality for the Vii app."""

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
                # Store log output and parse entries
                self.git_log_output = log_output
                self.git_log_entries = self._parse_git_log_entries(log_output)
                self.git_log_highlighted_entry = 0 if self.git_log_entries else -1

                # Update state
                self.git_log_page = page
                self.git_log_viewing = True

                # Render with highlighting
                self._render_log_with_highlight()

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

    def _parse_git_log_entries(self, log_output: str) -> list[tuple[int, int]]:
        """Parse git log output to identify entry boundaries.

        Each commit entry typically has:
        - Line with hash, date, author (may have graph chars like * or |)
        - Line(s) with commit message (indented)
        - Empty line separator

        Returns:
            List of (start_line, end_line) tuples for each commit entry
        """
        lines = log_output.split("\n")
        entries = []
        entry_start = None

        for i, line in enumerate(lines):
            stripped = line.lstrip("*| ")
            # Check if this line starts a new commit (has a short hash pattern)
            # The format is: "* <hash> <date> <author>" or similar with graph chars
            if stripped and not stripped.startswith(" ") and len(stripped) > 7:
                # Check for typical hash pattern (7+ hex chars at start)
                first_word = stripped.split()[0] if stripped.split() else ""
                if len(first_word) >= 7 and all(
                    c in "0123456789abcdef" for c in first_word.lower()
                ):
                    # This is a new commit entry
                    if entry_start is not None:
                        # End the previous entry (exclude trailing empty lines)
                        end_line = i - 1
                        while end_line > entry_start and not lines[end_line].strip():
                            end_line -= 1
                        entries.append((entry_start, end_line))
                    entry_start = i

        # Don't forget the last entry
        if entry_start is not None:
            end_line = len(lines) - 1
            while end_line > entry_start and not lines[end_line].strip():
                end_line -= 1
            entries.append((entry_start, end_line))

        return entries

    def _render_log_with_highlight(self) -> None:
        """Render git log output with entry highlighting."""
        if not self.git_log_output:
            return

        lines = self.git_log_output.split("\n")
        text = Text()

        # Add header
        text.append(f"📜 Git Log (Page {self.git_log_page + 1})\n\n", style="bold")

        # Get terminal width to pad highlighted lines
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        width = max(scroll_container.size.width - 4, 80)

        # Get highlighted entry boundaries
        highlight_start = -1
        highlight_end = -1
        if 0 <= self.git_log_highlighted_entry < len(self.git_log_entries):
            highlight_start, highlight_end = self.git_log_entries[self.git_log_highlighted_entry]

        for i, line in enumerate(lines):
            if highlight_start <= i <= highlight_end:
                # Highlighted entry - pad to full width
                padded_line = line.ljust(width)
                text.append(padded_line + "\n", style="reverse")
            else:
                text.append(line + "\n")

        # Add navigation footer
        text.append("\n")
        text.append("Navigation: ", style="dim")
        text.append("j/k", style="bold cyan")
        text.append(" = Up/Down  ", style="dim")
        text.append("Enter", style="bold cyan")
        text.append(" = Show commit  ", style="dim")
        if self.git_log_page > 0:
            text.append("p", style="bold cyan")
            text.append(" = Prev page  ", style="dim")
        text.append("n", style="bold cyan")
        text.append(" = Next page  ", style="dim")
        text.append("ESC", style="bold cyan")
        text.append(" = Close", style="dim")

        content_display = self.query_one("#content-display", Static)
        content_display.update(text)

    def _scroll_to_log_entry(self) -> None:
        """Scroll to keep the highlighted log entry visible."""
        if self.git_log_highlighted_entry < 0 or not self.git_log_entries:
            return

        entry_start, _ = self.git_log_entries[self.git_log_highlighted_entry]
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)

        # Add 2 for the header lines (title + empty line)
        target_y = entry_start + 2

        # Get visible region
        visible_top = scroll_container.scroll_y
        visible_height = scroll_container.size.height - 2
        visible_bottom = visible_top + visible_height

        # Scroll if entry is outside visible region
        if target_y < visible_top + 2:
            scroll_container.scroll_to(y=max(0, target_y - 2), animate=False)
        elif target_y > visible_bottom - 2:
            scroll_container.scroll_to(y=target_y - visible_height + 2, animate=False)

    def _get_highlighted_commit_hash(self) -> str | None:
        """Extract the commit hash from the currently highlighted log entry.

        Returns:
            The commit hash string, or None if not found
        """
        if self.git_log_highlighted_entry < 0 or not self.git_log_entries:
            return None

        entry_start, _ = self.git_log_entries[self.git_log_highlighted_entry]
        lines = self.git_log_output.split("\n")

        if entry_start >= len(lines):
            return None

        line = lines[entry_start]
        # Strip graph characters and find the hash
        stripped = line.lstrip("*| ")
        if stripped:
            first_word = stripped.split()[0] if stripped.split() else ""
            # Verify it looks like a hash (7+ hex chars)
            if len(first_word) >= 7 and all(c in "0123456789abcdef" for c in first_word.lower()):
                return first_word
        return None

    def _show_git_commit(self) -> None:
        """Show the detailed view of the highlighted commit."""
        commit_hash = self._get_highlighted_commit_hash()
        if not commit_hash:
            self.notify("No commit selected", severity="warning")
            return

        if not self.git_root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            from .git_utils import get_git_show

            show_output = get_git_show(self.git_root, commit_hash)

            if show_output:
                # Create a header with commit info
                text = Text()
                text.append(f"📋 Commit: {commit_hash}\n\n", style="bold")

                # Try to syntax highlight the diff portion
                content_display = self.query_one("#content-display", Static)

                # Use diff syntax highlighting with theme matching content panel
                syntax = Syntax(
                    show_output,
                    "diff",
                    theme=get_syntax_theme(self.theme),
                    line_numbers=False,
                )

                content_display.update(Group(text, syntax))

                # Update state
                self.git_commit_viewing = True
                self.git_commit_hash = commit_hash

                # Scroll to top
                scroll_container = self.query_one("#content-scroll", ScrollableContainer)
                scroll_container.scroll_home(animate=False)

                self.notify(f"Showing commit {commit_hash}")
            else:
                self.notify("Could not retrieve commit details", severity="error")
        except Exception as e:
            self.notify(f"Git show failed: {e}", severity="error")

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
                # Store blame output for re-rendering with highlights
                self.git_blame_output = blame_output
                self.git_blame_highlighted_line = 0  # Start at first line

                # Display blame in content panel
                self._render_blame_with_highlight()

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

    def _render_blame_with_highlight(self) -> None:
        """Render git blame output with optional line highlighting."""
        if not self.git_blame_output:
            return

        lines = self.git_blame_output.split("\n")
        text = Text()

        # Get terminal width to pad lines
        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        width = max(scroll_container.size.width - 4, 80)  # -4 for padding, min 80

        for i, line in enumerate(lines):
            if i == self.git_blame_highlighted_line:
                # Highlighted line - pad to full width
                padded_line = line.ljust(width)
                text.append(padded_line + "\n", style="reverse")
            else:
                text.append(line + "\n")

        content_display = self.query_one("#content-display", Static)
        content_display.update(text)

    def _scroll_to_blame_line(self) -> None:
        """Scroll to keep the highlighted blame line visible."""
        if self.git_blame_highlighted_line < 0:
            return

        scroll_container = self.query_one("#content-scroll", ScrollableContainer)
        # Each line is roughly 1 unit of scroll height
        # Add 1 for padding at top
        target_y = self.git_blame_highlighted_line + 1

        # Get visible region
        visible_top = scroll_container.scroll_y
        visible_height = scroll_container.size.height - 2  # Account for borders
        visible_bottom = visible_top + visible_height

        # Scroll if line is outside visible region
        if target_y < visible_top + 2:
            # Line is above visible area, scroll up
            scroll_container.scroll_to(y=max(0, target_y - 2), animate=False)
        elif target_y > visible_bottom - 2:
            # Line is below visible area, scroll down
            scroll_container.scroll_to(y=target_y - visible_height + 2, animate=False)

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

                async def discover(self) -> "Hits":
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

                async def search(self, query: str) -> "Hits":
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
