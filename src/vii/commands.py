"""Command palette providers for vii."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.command import Hit, Hits, Provider

if TYPE_CHECKING:
    pass


class ConfigCommandProvider(Provider):
    """Command provider for config commands."""

    @property
    def _config_commands(self):
        """Get the list of config commands."""
        from vii.app import Vii

        app = self.app
        assert isinstance(app, Vii)

        return [
            ("Save Config", app._save_config, "Save current settings to config file"),
            ("Show Config Path", app._show_config_path, "Show config file location"),
        ]

    async def discover(self) -> Hits:
        """Show top-level Config menu when palette is opened."""
        from textual.command import DiscoveryHit

        yield DiscoveryHit(
            "Config",
            self._show_config_commands,
            help="Configuration settings",
        )

    async def _show_config_commands(self) -> None:
        """Show config subcommands in the palette."""
        from textual.command import CommandPalette

        parent_provider = self

        class ConfigSubCommandProvider(Provider):
            """Provider for config subcommands."""

            async def discover(self) -> Hits:
                """Show all config commands."""
                from textual.command import DiscoveryHit

                for command_name, callback, help_text in parent_provider._config_commands:
                    yield DiscoveryHit(
                        command_name,
                        callback,
                        help=help_text,
                    )

            async def search(self, query: str) -> Hits:
                """Search config commands."""
                matcher = self.matcher(query)

                for command_name, callback, help_text in parent_provider._config_commands:
                    score = matcher.match(command_name)
                    if score > 0:
                        yield Hit(
                            score,
                            matcher.highlight(command_name),
                            callback,
                            help=help_text,
                        )

        self.app.push_screen(CommandPalette(providers=[ConfigSubCommandProvider]))

    async def search(self, query: str) -> Hits:
        """Search for config menu."""
        matcher = self.matcher(query)

        score = matcher.match("Config")
        if score > 0:
            yield Hit(
                score,
                matcher.highlight("Config"),
                self._show_config_commands,
                help="Configuration settings",
            )


class GitCommandProvider(Provider):
    """Command provider for git commands with submenu."""

    @property
    def _git_commands(self):
        """Get the list of git commands."""
        from vii.app import Vii

        app = self.app
        assert isinstance(app, Vii)

        return [
            ("Status", app._git_status, "Show git status"),
            ("Log", app._git_log, "Show git commit history"),
            ("Refresh", app._git_refresh, "Refresh git status"),
            ("Switch Branch", app._git_switch_branch, "Switch to a different branch"),
            ("Add Current File", app._git_add_current, "Stage the current file"),
            ("Add All", app._git_add_all, "Stage all changes"),
            ("Commit", app._git_commit, "Commit staged changes"),
            ("Push", app._git_push, "Push to remote"),
            ("Pull", app._git_pull, "Pull from remote"),
            ("Diff Current File", app._git_diff_current, "Show diff for current file"),
            ("Blame Current File", app._git_blame_current, "Show git blame for current file"),
        ]

    async def discover(self) -> Hits:
        """Show top-level Git menu when palette is opened."""
        from vii.app import Vii

        app = self.app
        assert isinstance(app, Vii)

        # Only show git menu if in a git repository
        if not app.git_branch:
            return

        from textual.command import DiscoveryHit

        # Yield a single "Git" menu item
        yield DiscoveryHit(
            "Git",
            self._show_git_commands,
            help=f"Git commands for branch: {app.git_branch}",
        )

    async def _show_git_commands(self) -> None:
        """Show git subcommands in the palette."""
        from textual.command import CommandPalette

        parent_provider = self

        # Create a provider for git subcommands
        class GitSubCommandProvider(Provider):
            """Provider for git subcommands."""

            async def discover(self) -> Hits:
                """Show all git commands."""
                from textual.command import DiscoveryHit

                for command_name, callback, help_text in parent_provider._git_commands:
                    yield DiscoveryHit(
                        command_name,
                        callback,
                        help=help_text,
                    )

            async def search(self, query: str) -> Hits:
                """Search git commands."""
                matcher = self.matcher(query)

                for command_name, callback, help_text in parent_provider._git_commands:
                    score = matcher.match(command_name)
                    if score > 0:
                        yield Hit(
                            score,
                            matcher.highlight(command_name),
                            callback,
                            help=help_text,
                        )

        # Push a new command palette with git subcommands
        self.app.push_screen(CommandPalette(providers=[GitSubCommandProvider]))

    async def search(self, query: str) -> Hits:
        """Search for git menu."""
        from vii.app import Vii

        matcher = self.matcher(query)

        app = self.app
        assert isinstance(app, Vii)

        # Only show git menu if in a git repository
        if not app.git_branch:
            return

        # Match against "Git"
        score = matcher.match("Git")
        if score > 0:
            yield Hit(
                score,
                matcher.highlight("Git"),
                self._show_git_commands,
                help=f"Git commands for branch: {app.git_branch}",
            )
