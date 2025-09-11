# Testing pw-ci with Fake Patchwork Server

This directory includes a fake Patchwork HTTP server for testing the Python pw-ci implementation without requiring a real Patchwork instance.

## Fake Patchwork Server

The `fake_patchwork_server.py` provides a mock Patchwork API that serves:

- **Series data** - Fake series with patches, submitters, and metadata
- **Patch data** - Individual patches with states, comments, and check results  
- **Events** - Series creation events for monitoring
- **Comments** - Patch comments including recheck requests
- **Checks** - CI check results and status

### Features

- **Realistic data** - Generates series, patches, and metadata that match real Patchwork format
- **Dynamic responses** - Creates new data on-demand for unknown IDs
- **Configurable** - Supports different projects, states, and filtering
- **Recheck simulation** - Randomly includes recheck requests in comments
- **CI checks** - Provides fake CI check status and URLs

### API Endpoints

The server implements these Patchwork API endpoints:

```
GET /api/events/?category=series-created&project=testproject
GET /api/series/{id}/
GET /api/series/?project=testproject&state=new
GET /api/patches/{id}/
GET /api/patches/{id}/comments/
GET /api/patches/{id}/checks/
```

## Running Tests

### 1. Start the Fake Server

```bash
# Terminal 1: Start fake Patchwork server
python fake_patchwork_server.py
```

The server will start on `http://localhost:8000` and provide sample data.

### 2. Run Tests

```bash
# Terminal 2: Run the test suite
python test_with_fake_server.py
```

This will run a comprehensive test of pw-ci functionality including:

- Fetching series information
- Monitoring for new series
- Listing tracked series  
- CI monitoring with dummy provider
- Database operations

### 3. Manual Testing

You can also test individual components manually:

```bash
# Test patchwork monitoring
python -m pwci.cli monitor --pw-instance http://localhost:8000 --pw-project testproject

# Get series info
python -m pwci.cli series-info --pw-instance http://localhost:8000 --series-id 1000

# Test CI monitoring (dry run)
python -m pwci.cli ci-monitor --pw-instance http://localhost:8000 \
  --from-addr test@example.com --to-addr results@example.com \
  --enable-dummy --dry-run
```

## Sample API Responses

### Series Response
```json
{
  "id": 1000,
  "url": "http://localhost:8000/api/series/1000/",
  "name": "Test series 1000",
  "submitter": {
    "name": "John Doe", 
    "email": "john@example.com"
  },
  "received_all": true,
  "patches": [
    {
      "id": 100001,
      "url": "http://localhost:8000/api/patches/100001/",
      "name": "[PATCH 1/3] Test patch 100001"
    }
  ]
}
```

### Events Response
```json
[
  {
    "category": "series-created",
    "project": "testproject", 
    "date": "2024-01-15T10:30:00",
    "payload": {
      "series": {
        "id": 1000,
        "url": "http://localhost:8000/api/series/1000/"
      }
    }
  }
]
```

### Comments with Recheck
```json
[
  {
    "id": 1,
    "content": "This looks good!\n\nRecheck-request: github, travis",
    "submitter": {"name": "Reviewer", "email": "reviewer@example.com"}
  }
]
```

## Test Configuration

The test script creates a temporary configuration file:

```bash
# ~/.pwmon-test-rc (temporary)
pw_instance=http://localhost:8000
pw_project=testproject
from_addr=test-ci@example.com
to_addr=test-results@example.com
github_token=fake_github_token_for_testing
dummy_token=1111
```

This is automatically cleaned up after tests complete.

## Database Testing

The tests use the same SQLite database as the main application (`~/.series-db`). You can inspect the database after tests:

```bash
# View database contents
sqlite3 ~/.series-db "SELECT * FROM series;"
sqlite3 ~/.series-db "SELECT * FROM git_builds;"
```

## Expected Test Output

Successful tests will show:

```
✓ PASS Get series information
✓ PASS Monitor patchwork for new series  
✓ PASS List series in database
✓ PASS Monitor CI systems (dry run)

Results: 4/4 tests passed
🎉 All tests passed!
```

## Troubleshooting

**Server not running:**
```
ERROR: Fake Patchwork server is not running on localhost:8000
Please start it with: python fake_patchwork_server.py
```

**Import errors:**
```bash
# Install dependencies
pip install -e .
# Or
pip install -r requirements.txt
```

**Database permission errors:**
```bash
# Check database permissions
ls -la ~/.series-db
# Or use a different database path
export PWCI_DB_PATH=/tmp/test-series.db
```

This testing setup allows you to validate all pw-ci functionality without requiring access to a real Patchwork instance or CI systems.