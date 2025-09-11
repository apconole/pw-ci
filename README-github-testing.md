# GitHub Actions Testing with Fake Servers

This directory includes comprehensive testing for GitHub Actions integration using fake HTTP servers that simulate both Patchwork and GitHub REST APIs.

## Test Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Fake          │    │   pw-ci         │    │   Fake          │
│   Patchwork     │◄──►│   Python        │◄──►│   GitHub API    │
│   Server        │    │   Client        │    │   Server        │
│   :8000         │    │                 │    │   :8001         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
       │                        │                        │
       ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Series        │    │   SQLite        │    │   Workflow      │
│   Patches       │    │   Database      │    │   Runs          │
│   Events        │    │   ~/.series-db  │    │   Jobs          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Fake GitHub API Server

The `fake_github_server.py` provides a complete GitHub REST API simulation:

### Supported Endpoints

- `GET /repos/{owner}/{repo}` - Repository information
- `GET /repos/{owner}/{repo}/actions/runs` - List workflow runs
- `GET /repos/{owner}/{repo}/actions/runs/{run_id}` - Individual workflow run
- `GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs` - Jobs for a workflow run
- `GET /repos/{owner}/{repo}/actions/jobs/{job_id}` - Individual job details

### Features

- **Realistic workflow runs** - Generates runs with proper GitHub API format
- **Multiple workflows** - Simulates different workflow types (Build, Test, CI, etc.)
- **Branch filtering** - Supports `?branch=series_1000` filtering
- **Status progression** - Workflows can be queued, in_progress, or completed
- **Conclusion types** - success, failure, cancelled, timed_out, etc.
- **Job details** - Each run includes multiple jobs with steps
- **Authentication** - Requires `Authorization: token {token}` header
- **Rate limiting headers** - Includes proper GitHub API headers

### Sample Workflow Run Response

```json
{
  "id": 1001001,
  "name": "Build and Test",
  "head_branch": "series_1000",
  "head_sha": "abc1001001",
  "status": "completed",
  "conclusion": "success",
  "html_url": "https://github.com/owner/repo/actions/runs/1001001",
  "run_started_at": "2024-01-15T10:00:00Z",
  "repository": {
    "full_name": "owner/repo",
    "owner": {"login": "owner"}
  }
}
```

## Test Suites

### 1. Basic Integration Test (`test_github_integration.py`)

Tests the complete GitHub Actions workflow:

- **Database setup** - Creates test series and builds
- **API endpoints** - Verifies fake servers are responding
- **GitHub provider** - Tests GitHubActionsProvider directly
- **CI monitoring** - Full ci-monitor command with GitHub provider
- **Build results** - Validates workflow run parsing and result mapping

### 2. Comprehensive Test Runner (`run_full_tests.py`)

Automated test runner that:

- **Starts servers** - Launches both Patchwork and GitHub fake servers
- **Manages processes** - Handles server lifecycle and cleanup
- **Runs all tests** - Executes both basic and GitHub integration tests
- **Process isolation** - Uses process groups for clean shutdown
- **Error handling** - Graceful handling of server failures and timeouts

## Running Tests

### Option 1: Manual Testing

Start servers manually in separate terminals:

```bash
# Terminal 1: Patchwork server
python fake_patchwork_server.py

# Terminal 2: GitHub server  
python fake_github_server.py

# Terminal 3: Run tests
python test_github_integration.py
```

### Option 2: Automated Testing

Use the comprehensive test runner:

```bash
# Runs everything automatically
python run_full_tests.py
```

This will:
1. Check dependencies
2. Start both fake servers
3. Run all test suites
4. Clean up servers
5. Provide comprehensive reporting

## Test Data

The GitHub integration tests use this test data structure:

### Series Data
- **Series 1000**: `owner/repo` with 3 patches
- **Series 1001**: `dpdk/dpdk` with 2 patches
- Each series has a corresponding `series_{id}` branch

### Build Records
- Patch builds tracked in `git_builds` table
- `gap_sync = 0` indicates unsynced builds ready for GitHub monitoring
- SHA values match GitHub workflow run commits

### Workflow Runs
- Multiple workflows per series (Build, Test, CI, etc.)
- Different conclusion states (success, failure, cancelled)
- Realistic timing and metadata

## Expected Test Output

Successful GitHub integration test:

```bash
✅ Both servers are running

Testing API Endpoints
✓ Patchwork series: 200 (1234 chars)
✓ GitHub workflow runs: 200 (5678 chars)

Test: GitHub Actions CI monitoring
Command: python -m pwci.cli ci-monitor --github-token fake_token --dry-run
Scanning github
  Using API base: http://localhost:8001
Clear result for series_1000 with success at url https://github.com/owner/repo/actions/runs/1001001
Email sent successfully

✅ PASS GitHub Actions CI monitoring

Results: 2/2 tests passed
🎉 All GitHub integration tests passed!
```

## API Compatibility

The fake GitHub server maintains full compatibility with the GitHub REST API v3:

- **Authentication** - Supports token authentication
- **Response format** - Matches GitHub JSON response structure  
- **Headers** - Includes proper API headers and rate limit info
- **Error handling** - Returns appropriate HTTP status codes
- **Pagination** - Supports `per_page` parameter
- **Filtering** - Branch and status filtering work correctly

## Configuration

### Environment Variables

- `GITHUB_API_BASE` - Override GitHub API base URL (default: https://api.github.com)
- Set to `http://localhost:8001` for testing with fake server

### Database

Tests use the same SQLite database as production (`~/.series-db`):
- Creates test data that doesn't interfere with real data
- Uses predictable series IDs (1000, 1001) for testing
- Automatically sets up required schema

## Troubleshooting

**Port conflicts:**
```bash
# Check if ports are in use
lsof -i :8000
lsof -i :8001

# Kill existing processes
kill $(lsof -t -i :8000)
kill $(lsof -t -i :8001)
```

**Authentication errors:**
- Fake GitHub server requires any `Authorization` header
- Use `Authorization: token fake_token` for testing

**Database issues:**
- Tests modify `~/.series-db` - backup if needed
- Or set `PWCI_DB_PATH=/tmp/test.db` for isolated testing

**Server startup failures:**
- Check that Python scripts are executable
- Ensure no other processes are using ports 8000/8001
- Verify all dependencies are installed

This testing framework provides comprehensive validation of GitHub Actions integration without requiring real GitHub tokens, repositories, or network access to external APIs.