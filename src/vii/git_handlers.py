"""Git-related handlers for the vii application."""

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text
from textual.command import Hits
from textual.containers import ScrollableContainer
from textual.widgets import DirectoryTree, Static

from vii.constants import TIMEOUT_INTERACTIVE, TIMEOUT_MEDIUM, TIMEOUT_NETWORK
from vii.content import get_syntax_lexer, get_syntax_theme
from vii.git_state import GitState

if TYPE_CHECKING:
    # Import for documentation - the protocol defines the contract

    from vii.git_state import GitLogEntry


class GitHandlersMixin:
    """Mixin providing git-related functionality for the Vii app.

    This mixin requires the host class to implement ViiProtocol.
    The type stubs below ensure type safety - they match the protocol definition.

    WARNING: Do NOT stub Textual framework methods (push_screen, focus, etc.) here.
    Stub methods are real Python methods that shadow App's implementations in the MRO,
    silently breaking features. Use  # type: ignore[attr-defined] at the call site instead.
    See commit bcd9776 for the original incident with push_screen.
    """

    # Attributes from ViiProtocol (provided by host class)
    git: GitState
    theme: str

    # Methods from ViiProtocol (provided by host class)
    # NOTE: Do NOT stub Textual framework methods (push_screen, query_one, query, etc.)
    # here unless Vii (app.py) overrides them — Vii is first in the MRO so its definition
    # wins, but GitHandlersMixin comes before App, so stubs here shadow App's implementations.
    # notify is safe to stub because Vii.notify (app.py:213) always takes precedence.
    # See commit bcd9776 / fa2be3a / f08012f for prior shadowing incidents.
    def notify(self, *args: Any, **kwargs: Any) -> None: ...
    def _get_current_directory(self) -> Path: ...
    def _update_git_info(self, path: Path | None = None) -> None: ...
    def _update_header(self) -> None: ...
    def _reload_tree(self) -> None: ...
    def _get_tree(self) -> DirectoryTree | None: ...
    def _get_scroll_container(self) -> ScrollableContainer | None: ...
    def _get_content_display(self) -> Static | None: ...
    def _git_status(self) -> None:
        """Show git status."""
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            result = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(self.git.root),
                capture_output=True,
                text=True,
                timeout=TIMEOUT_MEDIUM,
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
        if not self.git.branch:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            from .git_utils import get_git_log

            current_dir = self._get_current_directory()
            skip = page * self.git.log_page_size
            log_result = get_git_log(current_dir, max_count=self.git.log_page_size, skip=skip)

            if log_result:
                machine_readable, pretty_output = log_result

                # Store pretty output for display
                self.git.log_output = pretty_output

                # Parse machine-readable format into structured entries
                self.git.log_entries = self._parse_git_log_entries(machine_readable, pretty_output)
                self.git.log_highlighted_entry = 0 if self.git.log_entries else -1

                # Update state
                self.git.log_page = page
                self.git.log_viewing = True

                # Render with highlighting
                self._render_log_with_highlight()

                # Focus the content panel so n/p keys work
                scroll_container = self._get_scroll_container()
                if scroll_container:
                    scroll_container.focus()

                self.notify(f"Showing git log (page {page + 1})")
            else:
                if page > 0:
                    self.notify("No more commits", severity="information")
                else:
                    self.notify("No git log available", severity="information")
        except Exception as e:
            self.notify(f"Git log failed: {e}", severity="error")

    def _parse_git_log_entries(
        self, machine_readable: str, pretty_output: str
    ) -> list["GitLogEntry"]:
        """Parse git log using machine-readable format to create structured entries.

        This function parses the machine-readable format (with null-byte delimiters)
        and maps it to line positions in the pretty output for highlighting.

        Args:
            machine_readable: Machine-readable format
                (hash\\x00short\\x00author\\x00date\\x00msg per line)
            pretty_output: Pretty formatted output with graph and colors for display

        Returns:
            List of GitLogEntry objects with structured data
        """
        from .git_state import GitLogEntry

        entries = []
        pretty_lines = pretty_output.split("\n")

        # Parse machine-readable entries (one commit per line)
        machine_lines = machine_readable.strip().split("\n")

        # Each entry in pretty output takes 3 lines (header + message + blank)
        # But we need to account for the graph characters

        for idx, machine_line in enumerate(machine_lines):
            # Split on null bytes
            parts = machine_line.split("\x00")
            if len(parts) >= 5:
                full_hash, short_hash, author, date, message = parts[:5]

                # Calculate line positions in pretty output
                # Each commit has roughly 3 lines: graph+header, message, blank
                # We need to find the actual line with the short hash
                start_line = -1
                for i, line in enumerate(pretty_lines):
                    if short_hash in line:
                        start_line = i
                        break

                if start_line >= 0:
                    # Find end of this entry (next commit or end of output)
                    end_line = start_line + 2  # Default: header + message + blank

                    # Look for next commit or end
                    for i in range(start_line + 1, len(pretty_lines)):
                        # Check if this looks like a new commit line (has graph + hash)
                        if i >= len(pretty_lines):
                            break
                        # If we find another hash from our list, that's the next entry
                        if idx + 1 < len(machine_lines):
                            next_parts = machine_lines[idx + 1].split("\x00")
                            if len(next_parts) >= 2 and next_parts[1] in pretty_lines[i]:
                                end_line = i - 1
                                break
                        # Also stop at empty separator before next entry
                        if i > start_line + 1 and not pretty_lines[i].strip():
                            if i + 1 < len(pretty_lines) and "*" in pretty_lines[i + 1]:
                                end_line = i
                                break

                    # Use last line if this is the last entry
                    if idx == len(machine_lines) - 1:
                        end_line = len(pretty_lines) - 1
                        # Trim trailing empty lines
                        while end_line > start_line and not pretty_lines[end_line].strip():
                            end_line -= 1

                    entry = GitLogEntry(
                        hash=full_hash,
                        short_hash=short_hash,
                        author=author,
                        date=date,
                        message=message,
                        start_line=start_line,
                        end_line=end_line,
                    )
                    entries.append(entry)

        return entries

    def _render_log_with_highlight(self) -> None:
        """Render git log output with entry highlighting."""
        if not self.git.log_output:
            return

        lines = self.git.log_output.split("\n")
        text = Text()

        # Add header
        text.append(f"📜 Git Log (Page {self.git.log_page + 1})\n\n", style="bold")

        # Get terminal width to pad highlighted lines
        scroll_container = self._get_scroll_container()
        width = max(scroll_container.size.width - 4, 80) if scroll_container else 80

        # Get highlighted entry boundaries
        highlight_start = -1
        highlight_end = -1
        if 0 <= self.git.log_highlighted_entry < len(self.git.log_entries):
            entry = self.git.log_entries[self.git.log_highlighted_entry]
            highlight_start = entry.start_line
            highlight_end = entry.end_line

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
        if self.git.log_page > 0:
            text.append("p", style="bold cyan")
            text.append(" = Prev page  ", style="dim")
        text.append("n", style="bold cyan")
        text.append(" = Next page  ", style="dim")
        text.append("ESC", style="bold cyan")
        text.append(" = Close", style="dim")

        content_display = self._get_content_display()
        if content_display:
            content_display.update(text)

    def _scroll_to_log_entry(self) -> None:
        """Scroll to keep the highlighted log entry visible."""
        if self.git.log_highlighted_entry < 0 or not self.git.log_entries:
            return

        entry = self.git.log_entries[self.git.log_highlighted_entry]
        scroll_container = self._get_scroll_container()
        if not scroll_container:
            return

        # Add 2 for the header lines (title + empty line)
        target_y = entry.start_line + 2

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
            The commit hash string (full hash), or None if not found
        """
        if self.git.log_highlighted_entry < 0 or not self.git.log_entries:
            return None

        # Now we can get the hash directly from the structured entry!
        entry = self.git.log_entries[self.git.log_highlighted_entry]
        return entry.hash

    def _show_git_commit(self) -> None:
        """Show the detailed view of the highlighted commit."""
        commit_hash = self._get_highlighted_commit_hash()
        if not commit_hash:
            self.notify("No commit selected", severity="warning")
            return

        if not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            from .git_utils import get_git_show

            show_output = get_git_show(self.git.root, commit_hash)

            if show_output:
                # Create a header with commit info
                text = Text()
                text.append(f"📋 Commit: {commit_hash}\n\n", style="bold")

                # Try to syntax highlight the diff portion
                content_display = self._get_content_display()
                if not content_display:
                    return

                # Use diff syntax highlighting with theme matching content panel
                syntax = Syntax(
                    show_output,
                    "diff",
                    theme=get_syntax_theme(self.theme),
                    line_numbers=False,
                )

                content_display.update(Group(text, syntax))

                # Update state
                self.git.commit_viewing = True
                self.git.commit_hash = commit_hash

                # Scroll to top
                scroll_container = self._get_scroll_container()
                if scroll_container:
                    scroll_container.scroll_home(animate=False)

                self.notify(f"Showing commit {commit_hash}")
            else:
                self.notify("Could not retrieve commit details", severity="error")
        except Exception as e:
            self.notify(f"Git show failed: {e}", severity="error")

    def _git_add_current(self) -> None:
        """Add the current file to git."""
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        tree = self._get_tree()
        if not tree or not (tree.cursor_node and tree.cursor_node.data):
            self.notify("No file selected", severity="warning")
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            self.notify("Cannot add a directory", severity="warning")
            return

        try:
            rel_path = path.relative_to(self.git.root)
            subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=str(self.git.root),
                check=True,
                timeout=TIMEOUT_MEDIUM,
            )
            self.notify(f"Added {path.name} to git")
            self._git_refresh()
        except Exception as e:
            self.notify(f"Git add failed: {e}", severity="error")

    def _git_add_all(self) -> None:
        """Add all changes to git."""
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            subprocess.run(
                ["git", "add", "."],
                cwd=str(self.git.root),
                check=True,
                timeout=5,
            )
            self.notify("Added all changes to git")
            self._git_refresh()
        except Exception as e:
            self.notify(f"Git add failed: {e}", severity="error")

    def _git_commit(self) -> None:
        """Commit changes (opens editor for commit message)."""
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        self.notify("Opening editor for commit message...")
        try:
            subprocess.run(
                ["git", "commit"],
                cwd=str(self.git.root),
                timeout=TIMEOUT_INTERACTIVE,  # 5 minutes for commit message
            )
            self._git_refresh()
        except Exception as e:
            self.notify(f"Git commit failed: {e}", severity="error")

    def _git_push(self) -> None:
        """Push changes to remote."""
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        self.notify("Pushing to remote...")
        try:
            result = subprocess.run(
                ["git", "push"],
                cwd=str(self.git.root),
                capture_output=True,
                text=True,
                timeout=TIMEOUT_NETWORK,
            )
            if result.returncode == 0:
                self.notify("Pushed successfully")
            else:
                self.notify(f"Push failed: {result.stderr}", severity="error")
        except Exception as e:
            self.notify(f"Git push failed: {e}", severity="error")

    def _git_pull(self) -> None:
        """Pull changes from remote."""
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        self.notify("Pulling from remote...")
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=str(self.git.root),
                capture_output=True,
                text=True,
                timeout=TIMEOUT_NETWORK,
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
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        tree = self._get_tree()
        if not tree or not (tree.cursor_node and tree.cursor_node.data):
            self.notify("No file selected", severity="warning")
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            self.notify("Cannot diff a directory", severity="warning")
            return

        try:
            rel_path = path.relative_to(self.git.root)
            result = subprocess.run(
                ["git", "diff", "HEAD", str(rel_path)],
                cwd=str(self.git.root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.stdout:
                # Display diff in content panel
                content_display = self._get_content_display()
                if content_display:
                    content_display.update(f"[bold]Git Diff: {path.name}[/bold]\n\n{result.stdout}")
                self.notify(f"Showing diff for {path.name}")
            else:
                self.notify("No changes to show", severity="information")
        except Exception as e:
            self.notify(f"Git diff failed: {e}", severity="error")

    def _git_blame_current(self) -> None:
        """Show git blame for the current file."""
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        tree = self._get_tree()
        if not tree or not (tree.cursor_node and tree.cursor_node.data):
            self.notify("No file selected", severity="warning")
            return

        path = tree.cursor_node.data.path
        if not path.is_file():
            self.notify("Cannot blame a directory", severity="warning")
            return

        # Check file size - don't blame files that are too large to preview
        # Uses same limit as content.read_file_content (100KB)
        try:
            file_size = path.stat().st_size
            if file_size > 100000:
                self.notify(f"File too large for blame ({file_size:,} bytes)", severity="warning")
                return
        except OSError:
            pass  # If we can't stat, let git blame try anyway

        try:
            from .git_utils import get_git_blame_file

            rel_path = path.relative_to(self.git.root)
            blame_output = get_git_blame_file(self.git.root, str(rel_path))

            if blame_output:
                # Store blame output and file path for re-rendering with highlights
                self.git.blame_output = blame_output
                self.git.blame_highlighted_line = 0  # Start at first line
                self.git.blame_file_path = path  # Store path for syntax highlighting

                # Display blame in content panel
                self._render_blame_with_highlight()

                # Update state so ESC can restore file content
                self.git.blame_viewing = True

                # Focus the content panel
                scroll_container = self._get_scroll_container()
                if scroll_container:
                    scroll_container.focus()

                self.notify(f"Showing blame for {path.name}")
            else:
                self.notify("No blame information available", severity="information")
        except Exception as e:
            self.notify(f"Git blame failed: {e}", severity="error")

    def _render_blame_with_highlight(self) -> None:
        """Render git blame output with optional line highlighting and syntax highlighting."""
        if not self.git.blame_output:
            return

        lines = self.git.blame_output.split("\n")
        text = Text()

        # Get terminal width to pad lines
        scroll_container = self._get_scroll_container()
        width = max(scroll_container.size.width - 4, 80) if scroll_container else 80

        # Get syntax highlighting info for the file
        lexer = None
        syntax_theme = get_syntax_theme(self.theme)
        if self.git.blame_file_path:
            lexer = get_syntax_lexer(self.git.blame_file_path)

        # Regex to parse git blame output: hash [filename] (author date line_num) code
        # e.g.: "abc123de src/file.py (John Doe   2024-01-15  10) some code here"
        # The [^)]+ matches everything up to and including the closing paren
        blame_pattern = re.compile(r"^(\^?[a-f0-9]+[^)]+\)\s?)(.*)")

        for i, line in enumerate(lines):
            is_highlighted = i == self.git.blame_highlighted_line

            # Try to parse blame line into metadata and code
            match = blame_pattern.match(line)
            if match and lexer:
                blame_meta = match.group(1)  # hash (author date line) part
                code_part = match.group(2)  # actual code

                # Add blame metadata with dim style
                if is_highlighted:
                    text.append(blame_meta, style="reverse dim")
                else:
                    text.append(blame_meta, style="dim")

                # Syntax highlight the code portion
                if code_part:
                    # Use Rich's Syntax to get highlighted text for just this line
                    syntax = Syntax(
                        code_part,
                        lexer,
                        theme=syntax_theme,
                        line_numbers=False,
                        word_wrap=False,
                    )
                    # Extract the highlighted text from Syntax
                    highlighted_text = syntax.highlight(code_part)
                    # Remove trailing newline that Syntax.highlight() adds
                    highlighted_text.rstrip()

                    if is_highlighted:
                        # Apply reverse style on top of syntax highlighting
                        # Pad to full width
                        remaining_width = max(0, width - len(blame_meta) - len(code_part))
                        highlighted_text.append(" " * remaining_width)
                        # Use stylize to overlay reverse on the entire highlighted text
                        highlighted_text.stylize("reverse")
                    text.append_text(highlighted_text)
                    text.append("\n")
                elif is_highlighted:
                    # Empty code part but highlighted - pad the line
                    remaining_width = max(0, width - len(blame_meta))
                    text.append(" " * remaining_width + "\n", style="reverse")
                else:
                    text.append("\n")
            else:
                # Fallback: render without syntax highlighting
                if is_highlighted:
                    padded_line = line.ljust(width)
                    text.append(padded_line + "\n", style="reverse")
                else:
                    text.append(line + "\n")

        content_display = self._get_content_display()
        if content_display:
            content_display.update(text)

    def _scroll_to_blame_line(self) -> None:
        """Scroll to keep the highlighted blame line visible."""
        if self.git.blame_highlighted_line < 0:
            return

        scroll_container = self._get_scroll_container()
        if not scroll_container:
            return
        # Each line is roughly 1 unit of scroll height
        # Add 1 for padding at top
        target_y = self.git.blame_highlighted_line + 1

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

    def _get_blame_line_commit_hash(self) -> str | None:
        """Extract the commit hash from the currently highlighted blame line.

        Returns:
            The commit hash string, or None if not found
        """
        if self.git.blame_highlighted_line < 0 or not self.git.blame_output:
            return None

        lines = self.git.blame_output.split("\n")
        if self.git.blame_highlighted_line >= len(lines):
            return None

        line = lines[self.git.blame_highlighted_line]

        # Parse the blame line to extract the commit hash
        # Format: "^?[a-f0-9]+ [filename] (author date line_num) code"
        # The hash is at the beginning, may have ^ prefix for boundary commits
        match = re.match(r"^(\^?[a-f0-9]+)", line)
        if match:
            commit_hash = match.group(1).lstrip("^")  # Remove ^ prefix if present
            return commit_hash
        return None

    def _show_blame_commit(self) -> None:
        """Show the detailed view of the commit for the highlighted blame line."""
        commit_hash = self._get_blame_line_commit_hash()
        if not commit_hash:
            self.notify("No commit found on this line", severity="warning")
            return

        if not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            from .git_utils import get_git_show

            show_output = get_git_show(self.git.root, commit_hash)

            if show_output:
                # Create a header with commit info
                text = Text()
                text.append(f"📋 Commit: {commit_hash}\n\n", style="bold")

                # Try to syntax highlight the diff portion
                content_display = self._get_content_display()
                if not content_display:
                    return

                # Use diff syntax highlighting with theme matching content panel
                syntax = Syntax(
                    show_output,
                    "diff",
                    theme=get_syntax_theme(self.theme),
                    line_numbers=False,
                )

                content_display.update(Group(text, syntax))

                # Update state - we're now viewing a commit from blame
                self.git.commit_viewing = True
                self.git.commit_hash = commit_hash
                # Keep git_blame_viewing True so ESC can go back to blame

                # Scroll to top
                scroll_container = self._get_scroll_container()
                if scroll_container:
                    scroll_container.scroll_home(animate=False)

                self.notify(f"Showing commit {commit_hash[:8]}")
            else:
                self.notify("Could not retrieve commit details", severity="error")
        except Exception as e:
            self.notify(f"Failed to show commit: {e}", severity="error")

    def _git_switch_branch(self) -> None:
        """Show branch selection and switch to selected branch."""
        if not self.git.branch or not self.git.root:
            self.notify("Not in a git repository", severity="warning")
            return

        try:
            from textual.command import DiscoveryHit, Hit, Provider

            from .git_utils import get_git_branches
            from .widgets import CommandPalette

            branches = get_git_branches(self.git.root)
            if not branches:
                self.notify("Failed to get branch list", severity="error")
                return

            current_branch = self.git.branch
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
            # NOTE: Do NOT add push_screen as a stub on this mixin — it would shadow
            # App.push_screen in the MRO and silently swallow the call (see bcd9776).
            self.push_screen(CommandPalette(providers=[BranchProvider]))  # type: ignore[attr-defined]

        except Exception as e:
            self.notify(f"Failed to show branches: {e}", severity="error")

    def _do_checkout_branch(self, branch: str, is_remote: bool) -> None:
        """Actually perform the branch checkout.

        Args:
            branch: Branch name to checkout
            is_remote: Whether this is a remote branch
        """
        if not self.git.root:
            self.notify("Not in a git repository", severity="error")
            return

        try:
            from .git_utils import (
                clear_git_cache,
                git_checkout_branch,
                git_checkout_remote_branch,
            )

            if is_remote:
                success, message = git_checkout_remote_branch(self.git.root, branch)
            else:
                success, message = git_checkout_branch(self.git.root, branch)

            if success:
                # Clear git cache since branch changed
                clear_git_cache()
                self.notify(message, severity="information")
                # Reload the directory tree to reflect branch changes
                self._reload_tree()
                # Refresh git info to update header
                self._update_git_info()
            else:
                self.notify(message, severity="error")
        except Exception as e:
            self.notify(f"Checkout failed: {e}", severity="error")
