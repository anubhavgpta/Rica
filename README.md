# Rica

Language-Agnostic Autonomous Coding Agent

## Overview

Rica is a standalone CLI tool that helps you plan and scaffold coding projects across multiple programming languages. Powered by Gemini 2.5 Flash, Rica analyzes your goal and creates structured build plans with milestones, file structures, and installation commands.

## Features

- **Language-Agnostic**: Supports Python, Go, TypeScript, Rust, JavaScript, and Bash
- **Intelligent Planning**: Uses AI to choose the best language and architecture for your goal
- **Structured Plans**: Breaks projects into milestones with detailed file plans
- **Beautiful CLI**: Rich, colorful output with progress spinners and tree views
- **Persistent Storage**: Saves plans to SQLite database and JSON files

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

### Create a new plan
```bash
rica plan "build a todo CLI in Go"
```

### Auto-approve a plan
```bash
rica plan "create a web scraper" --yes
```

### Specify a language
```bash
rica plan "build a REST API" --lang typescript
```

### List all saved plans
```bash
rica plans
```

### Show a specific plan
```bash
rica show <session_id>
```

### Check version
```bash
rica --version
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
├── pyproject.toml          # Package configuration
├── README.md              # This file
├── .env.example           # Environment variables template
└── rica/
    ├── __init__.py        # Package initialization
    ├── main.py            # CLI entry point
    ├── config.py          # Configuration and paths
    ├── db.py              # SQLite database management
    ├── llm.py             # Gemini API client
    ├── planner.py         # Core planning logic
    ├── models.py          # Pydantic data models
    ├── registry.py        # Language definitions
    └── prompts/
        └── planner.txt     # System prompt for planning
```

## Data Storage

- **Plans**: Saved to `~/.rica/plans/<session_id>.json`
- **Database**: SQLite at `~/.rica/rica.db` with WAL mode
- **Configuration**: Environment variables and `~/.rica/` directory

## Development

Rica is designed to be extended with additional layers:

- **L1**: Planner (current implementation)
- **L2**: Code generation
- **L3**: Testing and validation
- **L4**: Self-healing and optimization

## License

MIT License - see LICENSE file for details.
