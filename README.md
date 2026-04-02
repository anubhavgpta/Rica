<p align="center">
  <img src="./ricaLogo.png" alt="Rica Banner" width="60%" />
</p>

<p align="center">Language-Agnostic Autonomous Coding Agent</p>

<p align="center">
  <img src="https://img.shields.io/badge/build-passing-brightgreen?style=flat-square" />
  <img src="https://img.shields.io/badge/release-v0.1.0-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" />
</p>

## Overview

Rica is a standalone CLI tool that helps you plan, scaffold, build, debug, review, refactor, and explain coding projects across multiple programming languages. Powered by Gemini 2.0 Flash Lite, Rica acts as an autonomous coding agent — from generating a structured build plan all the way to watching your codebase for changes, generating tests, exporting sessions as portable archives, and firing lifecycle hooks for custom automation.

## Features

- **Language-Agnostic**: Supports Python, Go, TypeScript, Rust, JavaScript, and Bash
- **Intelligent Planning**: Uses AI to choose the best language and architecture for your goal
- **Structured Plans**: Breaks projects into milestones with detailed file plans
- **Code Generation**: Scaffolds complete projects from approved plans
- **Execution & Testing**: Runs compile checks, tests, and interprets output via LLM
- **Autonomous Debugging**: Iterative debug loop — classifies errors, applies fixes, retries
- **Code Review**: Static analysis of any codebase with actionable issue reports
- **Watch Mode**: Continuously monitors a directory and re-reviews on every save
- **Explain Mode**: Generates plain-English explanations of any codebase
- **Refactor Mode**: AI-driven refactoring suggestions with dry-run support
- **Test Generation**: Scaffolds test suites for any codebase
- **Session Tagging & Search**: Tag sessions and search across goals and tags
- **Export / Import**: Pack sessions into portable `.rica` archives and restore them anywhere
- **Plugin / Hook System**: Fire custom Python scripts at lifecycle events (plan, build, debug, export, import)
- **Session Notes**: Attach freeform notes to any session; notes travel with exports
- **Programmatic API**: `rica.api` — a Rich-free Python API for embedding Rica in other tools
- **Beautiful CLI**: Rich, colorful output with progress indicators and panels
- **Persistent Storage**: Saves all sessions, plans, builds, and history to SQLite

## Installation

```bash
pip install -e .
```

## Setup

1. Create a `.env` file in your project directory:
```env
GEMINI_API_KEY=your_key_here
```

2. Get your Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

## Usage

### Planning

```bash
# Create a new plan
rica plan "build a todo CLI in Go"

# Auto-approve a plan
rica plan "create a web scraper" --yes

# Specify a language
rica plan "build a REST API" --lang typescript

# List all saved plans
rica plans

# Show a specific plan
rica show <session_id>
```

### Building

```bash
# Generate code from an approved plan
rica build <session_id>

# List all builds
rica builds

# Print workspace path
rica workspace <session_id>
```

### Execution & Testing

```bash
# Compile check
rica check <session_id>

# Run the project
rica run <session_id> [--timeout 30]

# Run tests
rica test <session_id>
```

### Debugging

```bash
# Autonomous debug loop (up to 5 iterations by default)
rica debug <session_id> [--max-iter N] [--timeout T]

# View past debug attempts
rica debug-history <session_id>
```

### Review & Fix

```bash
# Analyze a codebase for issues
rica review <path> [--lang python]

# Apply error-severity fixes
rica fix <path> [--lang python] [--dry-run]

# List past review sessions
rica reviews [--path <path>]
```

### Watch Mode

```bash
# Watch a directory and auto-review on every save
rica watch <path> [--lang python] [--debounce 2.0]
```

### Explain Mode

```bash
# Generate a plain-English explanation of a codebase
rica explain <path> [--lang python]

# Save the explanation to a Markdown file
rica explain <path> --out explanation.md

# List past explanations
rica explanations [--path <path>]
```

### Refactor Mode

```bash
# Generate refactoring suggestions for a codebase
rica refactor <path> [--lang python]

# View past refactor sessions
rica refactors [--path <path>]
```

### Test Generation

```bash
# Scaffold a test suite for a codebase
rica gen-tests <path> [--lang python]

# View past test generation sessions
rica test-generations [--path <path>]
```

### Session Tagging & Search

```bash
# Tag a session
rica tag <session_id> <tag>

# Remove a tag
rica untag <session_id> <tag>

# List tags on a session
rica tags <session_id>

# List all sessions with a given tag
rica sessions --tag <tag>

# Search sessions by goal or tag
rica search <query>
```

### Export / Import

```bash
# Export a session to a .rica archive
rica export <session_id> [--out <path>]

# Import a session from a .rica archive
rica import <file> [--tag <tag>]
```

### Plugin / Hook System

```bash
# List all registered hook scripts
rica hooks

# Manually fire a hook event
rica hook-run <event> [--session <session_id>]
```

Hook scripts are plain Python files placed in `~/.rica/hooks/<event>.py`. Rica calls them as subprocesses, passing a JSON payload as the first argument. Supported events: `pre_plan`, `post_plan`, `pre_build`, `post_build`, `pre_debug`, `post_debug`, `pre_export`, `post_export`, `post_import`.

### Session Notes

```bash
# Add a note to a session
rica note <session_id> "your note here"

# View all notes for a session
rica notes <session_id>

# Edit a note
rica note-edit <note_id> "updated content"

# Delete a note
rica note-delete <note_id>
```

## Supported Languages

- **Python**: Scripting, data processing, automation, CLIs, ML/AI
- **Go**: High-performance CLIs, servers, systems tools
- **TypeScript/Node.js**: Web applications, APIs, frontend tooling
- **Rust**: Systems programming, performance-critical tools
- **JavaScript**: Simple web scripts, Node.js utilities
- **Bash**: Simple automation, glue scripts

## Project Structure

```
rica/
├── pyproject.toml
├── README.md
├── .env.example
└── rica/
    ├── __init__.py
    ├── main.py           # CLI entry point (Typer)
    ├── api.py            # Programmatic Python API
    ├── config.py         # Paths and environment config
    ├── console.py        # Rich console (get_console)
    ├── db.py             # SQLite WAL database
    ├── llm.py            # Gemini API client
    ├── models.py         # Pydantic data models
    ├── registry.py       # Language definitions
    ├── planner.py        # L1: Plan generation
    ├── codegen.py        # L2: Code generation
    ├── executor.py       # L3: Command execution
    ├── debugger.py       # L4: Error classification and fixing
    ├── reviewer.py       # L5: Static analysis
    ├── watcher.py        # L6: File system watching
    ├── explainer.py      # L7: Codebase explanation
    ├── refactor.py       # L8: Refactoring suggestions
    ├── test_generator.py # L8: Test suite generation
    ├── exporter.py       # L15: Session export
    ├── importer.py       # L15: Session import
    ├── hooks.py          # L16: Plugin/hook system
    └── prompts/
        ├── planner.txt
        ├── codegen.txt
        ├── executor.txt
        ├── debugger.txt
        ├── reviewer.txt
        ├── fixer.txt
        ├── explainer.txt
        ├── refactor.txt
        └── test_generator.txt
```

## Data Storage

- **Plans**: `~/.rica/plans/<session_id>.json`
- **Workspaces**: `~/.rica/workspaces/<session_id>/`
- **Hooks**: `~/.rica/hooks/<event>.py`
- **Database**: `~/.rica/rica.db` (SQLite WAL)

## Architecture — Layers

| Layer | Command(s) | Description |
|-------|------------|-------------|
| L1 | `plan`, `plans`, `show` | AI-driven project planning |
| L2 | `build`, `builds`, `workspace` | Code generation from plans |
| L3 | `check`, `run`, `test` | Execution and testing |
| L4 | `debug`, `debug-history` | Autonomous debug loop |
| L5 | `review`, `fix`, `reviews` | Static analysis and auto-fix |
| L6 | `watch` | Continuous file watching and review |
| L7 | `explain`, `explanations` | Plain-English codebase explanation |
| L8 | `refactor`, `gen-tests`, `test-generations` | Refactoring and test generation |
| L12 | — | Programmatic Python API (`rica.api`) |
| L13 | `tag`, `untag`, `tags`, `search`, `sessions` | Session tagging and search |
| L14 | — | Bug sweep and stability fixes |
| L15 | `export`, `import` | Portable `.rica` session archives |
| L16 | `hooks`, `hook-run` | Plugin/hook system for lifecycle events |
| L17 | `note`, `notes`, `note-edit`, `note-delete` | Freeform session notes |

## Programmatic API

Rica exposes a Rich-free Python API for embedding in other tools:

```python
import rica

# Plan and build
session = rica.create_session("build a todo CLI in Go")
rica.approve_plan(session["session_id"])
rica.build_session(session["session_id"])

# Notes
rica.add_note(session["session_id"], "remember to add auth later")
notes = rica.get_notes(session["session_id"])

# Export
rica.export_session(session["session_id"], out_path="./my_session.rica")
```

## License

MIT License — see LICENSE file for details.