# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a6] - 2026-03-16

### Added
- Syntax highlighting for code portions in git blame view
  - Blame metadata (commit, author, date) shown in dim style
  - Code portion syntax highlighted based on file type
  - Works with all supported languages (Python, JavaScript, Rust, Markdown, etc.)
- Git blame now disabled for files too large to preview (>100KB)
- Markdown syntax highlighting with tree-sitter
  - Headings (h1-h6) in bold cyan
  - Code spans and fenced code blocks in green
  - List markers in yellow
  - Emphasis (italic) and strong emphasis (bold)
  - Block quote markers in dim italic
- Maximize focused panel with `m` key
  - When sidebar is focused, `m` hides content panel (maximizes sidebar)
  - When content panel is focused, `m` hides sidebar (maximizes content)
  - Press `m` again to restore both panels
  - Sidebar expands to full width when maximized
  - Focus stays on the panel that was maximized when restoring
- Cursor line highlighting in content panel
  - Click any line to highlight it
  - `j`/`k` keys move highlight line by line
  - Highlight shown with reverse style when content panel has focus
  - `ESC` removes highlight when returning focus to sidebar
  - Works with both tree-sitter and Pygments syntax highlighting
- Page up/down cursor movement in file content view
  - `ctrl+f`, `ctrl+d`, `d` move cursor down by page size
  - `ctrl+b`, `ctrl+u`, `u` move cursor up by page size
  - Cursor highlight follows page movement
  - Falls back to scroll-only behavior for git log, blame, and directory views
- Double-click in content panel to open file in editor (same as `e` key)

### Fixed
- Content search now works correctly with `/` key in content panel
- Content search uses the currently displayed file instead of tree cursor
- Search scrolling uses viewport-aware positioning to keep matches visible
- Blank lines in git blame view no longer doubled
- Sidebar restore now correctly sets width after maximizing
- CI badge in README now points to correct workflow file

## [0.1.0a5] - 2026-03-14

### Added
- Image preview in content panel (PNG, JPG, GIF, BMP, WebP, ICO, TIFF)
  - Shows image dimensions and format in header
  - Press `e` to open in system viewer (Preview on macOS)
- Toggle git blame on/off with `b` key (was show-only before)
- Toggle git log on/off with `l` key (was show-only before)
- Horizontal scrolling in content panel with `h`/`H` (left) and `L` (right) keys
- Interactive blame view with line highlighting:
  - Click to highlight/select any line
  - `j`/`k` keys to move cursor up/down through blame
  - `g`/`G` to jump to top/bottom
  - Full-width highlight bar
  - Auto-scroll to keep highlighted line visible
- Interactive git log view with entry highlighting:
  - Visual highlight (reverse video) on selected commit entry
  - `j`/`k` keys to navigate between commits
  - `g`/`G` to jump to first/last commit
  - Click to select a commit entry
  - Double-click or `Enter` to view full commit details with `git show`
  - `ESC` returns from commit view to log, or closes log
  - `l` key navigates back through views (commit → log → file)
  - Syntax-highlighted diff output matching content panel theme
- Double-click on file in sidebar to open in editor (same as `e` key)
- Notification limit: max 3 notifications visible, oldest removed when exceeded

### Changed
- Splitter shows white background while dragging for better visual feedback
- Refactored key handling into separate mixin module for maintainability

### Fixed
- Command palette now opens correctly with `ctrl+p` (Textual 8.x compatibility)
- j/k navigation in left sidebar now works correctly (Textual 8.x compatibility)
- Panel resizing via splitter drag now works correctly (Textual 8.x compatibility)
- Content panel now loads file content when navigating (Textual 8.x compatibility)
- Enter key in content panel correctly toggles focus back to sidebar
- j/k keys in git commit view now scroll content instead of navigating log entries

## [0.1.0a4] - 2026-03-12

### Added
- Tree-sitter syntax highlighting (2.6x faster than Pygments)
- Shell command (`s` key) - drop into shell in current directory
- Git log with pagination (`l` key)
- Git blame (`b` key)
- Git branch switching (`B` key)
- Hierarchical Git menu in command palette
- Line numbers in search results

### Changed
- Smooth j/k navigation with 100ms debounced content updates
- Increased render cache from 10 to 30 files
- Cached relative path lookups in directory tree for faster rendering

### Fixed
- Tree state (expanded/collapsed) preserved when reloading
- Git operations now work correctly from repository root
- ESC key properly closes git log display

## [0.1.0a3] - 2026-03-11

### Added

- Syntax highlighting support for Justfile (justfile, Justfile, .justfile)
- `d/u` keys for page down/up navigation (in addition to existing Ctrl+F/B/D/U)
- Mouse click in content panel now stops scroll animations
- ENTER key in sidebar toggles directory expansion/collapse

### Changed

- Simplified ENTER key behavior: always switches panel focus from content to sidebar
- ENTER in sidebar on files switches to content panel
- ENTER in sidebar on directories toggles expand/collapse
- More subtle focus indicators for better visual clarity
- File selection in sidebar keeps focus in sidebar (doesn't auto-switch to content panel)

### Fixed

- Default theme now properly set to atom-one-dark
- Improved theme mapping for all Textual themes (dark and light variants)
- Syntax highlighting now properly restored when clearing search
- ESC key only handled when search is active (prevents interference with other operations)
- Correct widget detection for mouse click events

## [0.1.0a2] - 2026-03-10

### Added

- Two-panel layout: directory tree sidebar and file content preview
- File content preview panel when navigating the directory tree
- Scrollable content panel with focus-aware navigation
- Syntax highlighting for Python files
- Syntax highlighting extended to many common file types:
  - Shell scripts (bash, zsh, fish)
  - Config files (toml, yaml, json, ini)
  - Markup (markdown, html, xml, css)
  - JavaScript/TypeScript
  - C/C++
  - Rust, Go, Ruby, Java, Kotlin, Swift, PHP, SQL, Lua, Perl
  - Special files (Dockerfile, Makefile, .bashrc, etc.)
- Vim-style search (`/`) in content panel with match highlighting
- Search in sidebar panel for finding files/directories by name
- `n/N` keys to navigate between search matches
- `Enter` key in content panel to open file in editor
- `e` key to edit selected file
- `Ctrl+F/B` for page up/down navigation in sidebar
- Draggable splitter between sidebar and content panels for resizable layout
- Syntax highlighting theme syncs with Textual app theme (dark/light)

### Changed

- `Enter` now switches focus to content panel (use `e` to edit)

### Fixed

- Vim h/l keybindings now work correctly in DirectoryTree
- Test assertions updated to match actual application behavior

## [0.1.0a1] - 2026-03-09

### Added

- Initial alpha release
- Terminal-based file browser using Textual framework
- Directory tree navigation with vim-style keybindings (j/k/h/l/g/G)
- Automatic editor detection (checks VISUAL, EDITOR env vars, then common editors)
- Support for both terminal editors (vim, nvim, nano, etc.) and GUI editors (VS Code, etc.)
- Keyboard shortcuts:
  - `j/k` - Navigate up/down
  - `h/l` - Collapse/expand directories
  - `g/G` - Go to top/bottom
  - `Tab` - Switch focus between panels
  - `q` - Quit
- Pre-commit hooks for code quality with ruff (replaced black, flake8, and isort)
- Comprehensive test suite

[Unreleased]: https://github.com/aclark4life/vii/compare/v0.1.0a6...HEAD
[0.1.0a6]: https://github.com/aclark4life/vii/compare/v0.1.0a5...v0.1.0a6
[0.1.0a5]: https://github.com/aclark4life/vii/compare/v0.1.0a4...v0.1.0a5
[0.1.0a4]: https://github.com/aclark4life/vii/compare/v0.1.0a3...v0.1.0a4
[0.1.0a3]: https://github.com/aclark4life/vii/compare/v0.1.0a2...v0.1.0a3
[0.1.0a2]: https://github.com/aclark4life/vii/compare/v0.1.0a1...v0.1.0a2
[0.1.0a1]: https://github.com/aclark4life/vii/releases/tag/v0.1.0a1
