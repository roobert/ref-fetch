# ref-fetch

Automates fetching and caching of documentation and source code for specified versions of core standard libraries and third-party packages. It intelligently locates repositories, resolves dependencies, and provides a local, version-controlled reference of your project's entire dependency tree for LLM-assisted development.

## Installation

```bash
pip install ref-fetch
```

## Usage

```bash
ref-fetch <ecosystem> [path]
```

- `ecosystem`: The package ecosystem to process (e.g., `pip`, `npm`, `swift`).
- `path`: The path to the project directory (defaults to the current directory).
