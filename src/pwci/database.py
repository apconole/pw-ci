"""Database layer for series tracking and CI management."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


class SeriesDatabase:
    """SQLite database for tracking patchwork series and CI builds."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.expanduser("~/.series-db")
        self.db_path = Path(db_path)
        self._ensure_schema()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with timeout."""
        conn = sqlite3.connect(str(self.db_path), timeout=500)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        """Ensure database schema exists and is up to date."""
        with self._connection() as conn:
            # Create initial series table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS series (
                    series_id INTEGER,
                    series_project TEXT NOT NULL,
                    series_url TEXT NOT NULL,
                    series_submitter TEXT NOT NULL,
                    series_email TEXT NOT NULL,
                    series_submitted BOOLEAN,
                    series_completed INTEGER,
                    series_instance TEXT NOT NULL DEFAULT 'none',
                    series_downloaded INTEGER,
                    series_branch TEXT,
                    series_repo TEXT,
                    series_sha TEXT
                )
            """)

            # Create travis_build table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS travis_build (
                    pw_series_id INTEGER,
                    pw_series_instance TEXT,
                    travis_api_server TEXT,
                    travis_repo TEXT,
                    travis_branch TEXT,
                    travis_sha TEXT,
                    pw_patch_url TEXT
                )
            """)

            # Create git_builds table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS git_builds (
                    series_id INTEGER,
                    patch_id INTEGER,
                    patch_url STRING,
                    patch_name STRING,
                    sha STRING,
                    patchwork_instance STRING,
                    patchwork_project STRING,
                    repo_name STRING,
                    gap_sync INTEGER,
                    obs_sync INTEGER,
                    cirrus_sync INTEGER
                )
            """)

            # Create recheck_requests table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS recheck_requests (
                    recheck_id INTEGER,
                    recheck_message_id STRING,
                    recheck_requested_by STRING,
                    recheck_series STRING,
                    recheck_patch INTEGER,
                    patchwork_instance STRING,
                    patchwork_project STRING,
                    recheck_sync INTEGER
                )
            """)

            # Create check_id_scanned table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS check_id_scanned (
                    check_patch_id INTEGER,
                    check_url STRING
                )
            """)

            # Create schema version table for migrations
            conn.execute("""
                CREATE TABLE IF NOT EXISTS series_schema_version (
                    id INTEGER
                )
            """)

            conn.commit()

    def series_exists(self, instance: str, series_id: int) -> bool:
        """Check if a series exists in the database."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT series_id FROM series WHERE series_id = ? AND series_instance = ?",
                (series_id, instance)
            )
            return cursor.fetchone() is not None

    def add_series(self, instance: str, project: str, series_id: int, 
                   url: str, submitter_name: str, submitter_email: str, 
                   completed: bool = False) -> None:
        """Add a new series to the database."""
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO series (
                    series_id, series_project, series_url, series_submitter,
                    series_email, series_submitted, series_completed,
                    series_instance, series_downloaded
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (series_id, project, url, submitter_name, submitter_email, 
                  False, 1 if completed else 0, instance, 0))
            conn.commit()

    def get_unsubmitted_series(self, instance: str, project: str) -> List[Tuple]:
        """Get series that are completed but not submitted."""
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT series_id, series_url, series_submitter, series_email
                FROM series 
                WHERE series_instance = ? AND series_project = ? 
                AND series_completed = 1 AND series_submitted = 0
            """, (instance, project))
            return cursor.fetchall()

    def get_uncompleted_series(self, instance: str, project: str) -> List[Tuple]:
        """Get series that are not yet completed."""
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT series_id, series_url, series_submitter, series_email
                FROM series 
                WHERE series_instance = ? AND series_project = ? 
                AND series_completed = 0 AND series_submitted = 0 
                AND series_downloaded = 0
            """, (instance, project))
            return cursor.fetchall()

    def set_series_submitted(self, instance: str, series_id: int) -> None:
        """Mark a series as submitted."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE series SET series_submitted = 1 WHERE series_id = ? AND series_instance = ?",
                (series_id, instance)
            )
            conn.commit()

    def set_series_completed(self, instance: str, series_id: int) -> None:
        """Mark a series as completed."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE series SET series_completed = 1 WHERE series_id = ? AND series_instance = ?",
                (series_id, instance)
            )
            conn.commit()

    def get_active_branches(self, instance: str) -> List[Tuple]:
        """Get series with active branches."""
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT series_id, series_project, series_url, series_branch, series_repo
                FROM series 
                WHERE series_instance = ? AND series_branch IS NOT NULL 
                AND series_branch != ''
            """, (instance,))
            return cursor.fetchall()

    def set_series_branch(self, instance: str, series_id: int, repo: str, branch: str) -> None:
        """Set the branch information for a series."""
        with self._connection() as conn:
            conn.execute("""
                UPDATE series SET series_branch = ?, series_repo = ? 
                WHERE series_id = ? AND series_instance = ?
            """, (branch, repo, series_id, instance))
            conn.commit()

    def clear_series_branch(self, instance: str, series_id: int) -> None:
        """Clear the branch information for a series."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE series SET series_branch = '' WHERE series_id = ? AND series_instance = ?",
                (series_id, instance)
            )
            conn.commit()

    def get_unsynced_builds(self, instance: str, ci_type: str) -> List[Tuple]:
        """Get builds that haven't been synced to a CI system."""
        with self._connection() as conn:
            cursor = conn.execute(f"""
                SELECT * FROM git_builds 
                WHERE patchwork_instance = ? AND {ci_type} = 0 
                ORDER BY series_id
            """, (instance,))
            return cursor.fetchall()

    def set_build_synced(self, instance: str, patch_id: int, ci_type: str) -> None:
        """Mark a build as synced to a CI system."""
        with self._connection() as conn:
            conn.execute(f"""
                UPDATE git_builds SET {ci_type} = 1 
                WHERE patchwork_instance = ? AND patch_id = ?
            """, (instance, patch_id))
            conn.commit()

    def insert_build(self, series_id: int, patch_id: int, patch_url: str,
                     patch_name: str, sha: str, instance: str, project: str,
                     repo_name: str) -> None:
        """Insert a new build record."""
        with self._connection() as conn:
            conn.execute("""
                INSERT INTO git_builds (
                    series_id, patch_id, patch_url, patch_name, sha,
                    patchwork_instance, patchwork_project, repo_name,
                    gap_sync, obs_sync, cirrus_sync
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
            """, (series_id, patch_id, patch_url, patch_name, sha, 
                  instance, project, repo_name))
            conn.commit()

    def get_patch_id_by_series_and_sha(self, series_id: int, sha: str, instance: str) -> Optional[int]:
        """Get patch ID by series ID and SHA."""
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT patch_id FROM git_builds 
                WHERE patchwork_instance = ? AND series_id = ? AND sha = ?
            """, (instance, series_id, sha))
            row = cursor.fetchone()
            return row[0] if row else None
