# pw-ci Python Rewrite

This is a complete rewrite of the pw-ci project from bash scripts to Python 3.8+.

## Overview

The original pw-ci project was a collection of bash scripts for monitoring CI systems (GitHub Actions, Travis CI, Cirrus CI, etc.) and posting results back to Patchwork instances. This Python rewrite provides the same functionality with improved maintainability, error handling, and extensibility.

## Architecture

### Core Components

- **`database.py`** - SQLite database layer for tracking series and builds
- **`patchwork.py`** - Patchwork API client and monitoring
- **`ci_providers.py`** - CI provider implementations (GitHub, Travis, Cirrus, etc.)
- **`email.py`** - Email generation and sending functionality  
- **`monitor.py`** - Main orchestration and monitoring logic
- **`cli.py`** - Command-line interface

### Key Features

- **Modular CI Providers**: Easy to add new CI systems
- **Database Management**: Automatic schema migrations and SQLite backend
- **Email Integration**: Git send-email and SMTP support
- **Configuration**: File-based config with command-line overrides
- **Error Handling**: Robust error handling and logging
- **Testing**: Built-in dummy provider for testing

## Installation

```bash
# Install in development mode
pip install -e .

# Or install from requirements.txt
pip install -r requirements.txt
```

## Usage

### Monitor Patchwork for New Series

```bash
# Monitor a patchwork instance
pw-ci monitor --pw-instance https://patchwork.example.com --pw-project myproject

# With authentication
pw-ci monitor --pw-instance https://patchwork.example.com --pw-project myproject --pw-credentials user:pass
```

### Monitor CI Systems

```bash
# Monitor GitHub Actions and send result emails
pw-ci ci-monitor --pw-instance https://patchwork.example.com \
                 --from-addr ci@example.com --to-addr patches@example.com \
                 --github-token ghp_xxxx

# Monitor multiple CI systems
pw-ci ci-monitor --pw-instance https://patchwork.example.com \
                 --from-addr ci@example.com --to-addr patches@example.com \
                 --github-token ghp_xxxx --travis-token xxxx --cirrus-token xxxx

# Dry run mode
pw-ci ci-monitor --dry-run --pw-instance https://patchwork.example.com \
                 --from-addr ci@example.com --to-addr patches@example.com \
                 --github-token ghp_xxxx
```

### Series Management

```bash
# Get information about a series
pw-ci series-info --pw-instance https://patchwork.example.com --series-id 12345

# List tracked series
pw-ci list-series --pw-instance https://patchwork.example.com --pw-project myproject
```

## Configuration

Configuration can be provided via files in your home directory:

- `~/.pwmon-rc` - General patchwork monitoring config
- `~/.cimon-rc` - CI monitoring config
- `~/.github_actions_mon_rc` - GitHub Actions specific config

Example `~/.pwmon-rc`:
```bash
pw_instance=https://patchwork.example.com
pw_project=myproject
pw_credential=user:password
```

Example `~/.cimon-rc`:
```bash
from_addr=ci@example.com
to_addr=patches@example.com
github_token=ghp_xxxxxxx
travis_token=xxxxxxx
```

## CI Provider Support

### GitHub Actions
- Monitors workflow runs for series branches
- Reports success/failure status for each workflow
- Supports multiple workflows per series

### Travis CI  
- Monitors builds for active branches
- Reports build status (passed/failed/errored)
- Cleans up completed branches

### Cirrus CI
- Uses GraphQL API to monitor builds
- Reports task success/failure status
- Handles complex build pipelines

### Dummy Provider
- For testing and development
- Always reports success
- Can be enabled with `--enable-dummy`

## Email Integration

Supports two email sending methods:

1. **Git send-email** (default) - Uses `git send-email` command
2. **SMTP** - Direct SMTP server connection

Email templates include:
- Build result notifications with status
- Threading support (In-Reply-To headers)  
- CC to patch authors on failures
- Post-result submission confirmations

## Database Schema

Uses SQLite database (`~/.series-db`) with these tables:

- `series` - Patchwork series tracking
- `git_builds` - Build/patch correlation
- `travis_build` - Travis CI specific data
- `recheck_requests` - Manual recheck requests
- `check_id_scanned` - Processed check IDs

Schema is automatically upgraded on startup.

## Migration from Bash Scripts

The Python version maintains compatibility with the original bash scripts:

1. Uses the same database file (`~/.series-db`)
2. Reads the same configuration files
3. Maintains the same email format and threading
4. Preserves the same command-line interface patterns

### Command Mapping

| Bash Script | Python Command |
|-------------|----------------|
| `pw_mon` | `pw-ci monitor` |
| `ci_mon` | `pw-ci ci-monitor` |
| `series_get` | `pw-ci series-info` |

## Development

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/
isort src/
```

### Type Checking

```bash
mypy src/
```

## Contributing

1. Follow the existing code style (black, isort)
2. Add type hints for new functions
3. Include docstrings for public APIs
4. Add tests for new functionality
5. Update documentation for new features