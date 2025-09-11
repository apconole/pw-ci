"""Tests for database functionality."""

import pytest
import tempfile
from pathlib import Path

from pwci.database import SeriesDatabase


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db = SeriesDatabase(db_path)
    yield db

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


def test_database_creation(temp_db):
    """Test database creation and schema."""
    # Database should be created and have proper schema
    assert temp_db.db_path.exists()


def test_series_operations(temp_db):
    """Test basic series operations."""
    instance = "https://patchwork.example.com"
    project = "testproject"
    series_id = 12345
    url = "https://patchwork.example.com/api/series/12345/"
    submitter = "Test User"
    email = "test@example.com"

    # Series should not exist initially
    assert not temp_db.series_exists(instance, series_id)

    # Add series
    temp_db.add_series(instance, project, series_id, url, submitter, email)

    # Series should now exist
    assert temp_db.series_exists(instance, series_id)

    # Should appear in uncompleted series
    uncompleted = temp_db.get_uncompleted_series(instance, project)
    assert len(uncompleted) == 1
    assert uncompleted[0][0] == series_id

    # Mark as completed
    temp_db.set_series_completed(instance, series_id)

    # Should appear in unsubmitted series
    unsubmitted = temp_db.get_unsubmitted_series(instance, project)
    assert len(unsubmitted) == 1
    assert unsubmitted[0][0] == series_id

    # Mark as submitted
    temp_db.set_series_submitted(instance, series_id)

    # Should no longer appear in unsubmitted
    unsubmitted = temp_db.get_unsubmitted_series(instance, project)
    assert len(unsubmitted) == 0


def test_build_operations(temp_db):
    """Test build tracking operations."""
    series_id = 12345
    patch_id = 67890
    patch_url = "https://patchwork.example.com/api/patches/67890/"
    patch_name = "Test patch"
    sha = "abcdef1234567890"
    instance = "https://patchwork.example.com"
    project = "testproject"
    repo_name = "owner/repo"

    # Insert build
    temp_db.insert_build(
        series_id, patch_id, patch_url, patch_name, sha, instance, project,
        repo_name
    )

    # Should appear in unsynced builds
    unsynced = temp_db.get_unsynced_builds(instance, "gap_sync")
    assert len(unsynced) == 1
    assert unsynced[0]["patch_id"] == patch_id

    # Mark as synced
    temp_db.set_build_synced(instance, patch_id, "gap_sync")

    # Should no longer appear in unsynced
    unsynced = temp_db.get_unsynced_builds(instance, "gap_sync")
    assert len(unsynced) == 0

    # Test patch ID lookup
    found_patch_id = temp_db.get_patch_id_by_series_and_sha(series_id, sha,
                                                            instance)
    assert found_patch_id == patch_id


def test_branch_operations(temp_db):
    """Test branch management operations."""
    instance = "https://patchwork.example.com"
    project = "testproject"
    series_id = 12345
    url = "https://patchwork.example.com/api/series/12345/"
    submitter = "Test User"
    email = "test@example.com"
    repo = "owner/repo"
    branch = "series_12345"

    # Add series first
    temp_db.add_series(instance, project, series_id, url, submitter, email)

    # No active branches initially
    branches = temp_db.get_active_branches(instance)
    assert len(branches) == 0

    # Set branch
    temp_db.set_series_branch(instance, series_id, repo, branch)

    # Should appear in active branches
    branches = temp_db.get_active_branches(instance)
    assert len(branches) == 1
    assert branches[0][0] == series_id  # series_id
    assert branches[0][3] == branch  # branch name
    assert branches[0][4] == repo  # repo name

    # Clear branch
    temp_db.clear_series_branch(instance, series_id)

    # Should no longer appear in active branches
    branches = temp_db.get_active_branches(instance)
    assert len(branches) == 0
