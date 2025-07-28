# ref-fetch

A tool to fetch, cache, and copy specific versions of libraries into repositories to provide code references and documentation to LLMs.

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
