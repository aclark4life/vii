"""Configuration management for vii."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def get_config_dir() -> Path:
    """Get the configuration directory path.

    Returns:
        Path to ~/.config/vii/
    """
    return Path.home() / ".config" / "vii"


def get_config_path() -> Path:
    """Get the configuration file path.

    Returns:
        Path to ~/.config/vii/config.toml
    """
    return get_config_dir() / "config.toml"


@dataclass
class Config:
    """Configuration settings for vii."""

    theme: str = "textual-dark"
    sidebar_width: int | None = None  # None means auto (1/3 of screen width)
    animate_scroll: bool = True  # Enable/disable scroll animations

    @classmethod
    def load(cls) -> Config:
        """Load configuration from the config file.

        Returns:
            Config object with loaded settings, or defaults if file doesn't exist.
        """
        config_path = get_config_path()

        if not config_path.exists():
            return cls()

        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)
            return cls.from_dict(data)
        except Exception:
            # If there's any error reading/parsing, return defaults
            return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Create a Config from a dictionary.

        Args:
            data: Dictionary with configuration values.

        Returns:
            Config object with values from the dictionary.
        """
        sidebar_width = data.get("sidebar_width")
        # Ensure sidebar_width is int or None
        if sidebar_width is not None:
            sidebar_width = int(sidebar_width)
        animate_scroll = data.get("animate_scroll", cls.animate_scroll)
        return cls(
            theme=data.get("theme", cls.theme),
            sidebar_width=sidebar_width,
            animate_scroll=bool(animate_scroll),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert config to a dictionary.

        Returns:
            Dictionary representation of the config.
        """
        result: dict[str, Any] = {
            "theme": self.theme,
            "animate_scroll": self.animate_scroll,
        }
        if self.sidebar_width is not None:
            result["sidebar_width"] = self.sidebar_width
        return result

    def save(self) -> None:
        """Save configuration to the config file."""
        config_dir = get_config_dir()
        config_path = get_config_path()

        # Create config directory if it doesn't exist
        config_dir.mkdir(parents=True, exist_ok=True)

        # Write config as TOML
        with open(config_path, "w") as f:
            f.write("# vii configuration file\n\n")
            for key, value in self.to_dict().items():
                if isinstance(value, str):
                    f.write(f'{key} = "{value}"\n')
                elif isinstance(value, bool):
                    f.write(f"{key} = {str(value).lower()}\n")
                elif isinstance(value, int | float):
                    f.write(f"{key} = {value}\n")
