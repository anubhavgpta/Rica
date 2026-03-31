<p align="center">
  <img src="./ricaLogo.png" alt="Rica Banner" width="100%" />
</p>

# Rica

Language-Agnostic Autonomous Coding Agent

![Build](https://img.shields.io/github/actions/workflow/status/anubhavgpta/rica/ci.yml?branch=main&style=flat-square&label=build)
![Release](https://img.shields.io/github/v/release/anubhavgpta/rica?style=flat-square&label=release)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

## Overview

Rica is a standalone CLI tool that helps you plan, scaffold, build, debug, review, and explain coding projects across multiple programming languages. Powered by Gemini 2.5 Flash, Rica acts as an autonomous coding agent — from generating a structured build plan all the way to watching your codebase for changes and explaining what any project does in plain English.

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
- **Beautiful CLI**: Rich, colorful output with progress indicators and panels
- **Persistent Storage**: Saves all sessions, plans, builds, and reports to SQLite

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
    ├── config.py         # Paths and environment config
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
    └── prompts/
        ├── planner.txt
        ├── codegen.txt
        ├── executor.txt
        ├── debugger.txt
        ├── reviewer.txt
        ├── fixer.txt
        └── explainer.txt
```

## Data Storage

- **Plans**: `~/.rica/plans/<session_id>.json`
- **Workspaces**: `~/.rica/workspaces/<session_id>/`
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

## License

MIT License — see LICENSE file for details.