# Tide (Textual IDE)

A terminal-based IDE with a file browser that opens selected files in your preferred editor.

## Features

- 🗂️ Interactive file browser using Textual's DirectoryTree
- 🚀 Opens files in your preferred editor (VS Code, Sublime, Vim, etc.)
- ⌨️ Keyboard-driven interface
- 🎨 Clean, terminal-based UI

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Usage

Run Tide from any directory:

```bash
tide
```

Or specify a directory to browse:

```bash
tide /path/to/project
```

## Keyboard Shortcuts

Vi-style navigation (arrow keys also work):

- `j/k` - Navigate down/up
- `h/l` - Collapse/expand directories
- `g` - Jump to top
- `G` - Jump to bottom
- `Enter` - Open selected file in editor
- `q` - Quit
- `Ctrl+C` - Quit

## Editor Detection

Tide automatically detects your preferred editor by checking:
1. `$VISUAL` environment variable
2. `$EDITOR` environment variable
3. Common editors: `code`, `subl`, `atom`, `vim`, `nvim`, `nano`
4. Falls back to `open` (macOS default)

### Editor Behavior

- **GUI Editors** (VS Code, Sublime, etc.): Opens in the background while Tide continues running
- **Terminal Editors** (vim, nvim, nano, etc.): Tide suspends and the editor takes over full screen. When you quit the editor, Tide resumes automatically

## Development

Run with Textual's development console:

```bash
textual console
textual run --dev src/tide/app.py
```

## License

MIT

