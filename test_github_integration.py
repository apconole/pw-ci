#!/usr/bin/env python3
"""
Test GitHub Actions integration with fake servers.

This script tests the complete workflow:
1. Patchwork server provides series/patch data
2. Database tracks builds for GitHub monitoring  
3. GitHub API server provides workflow run results
4. Email reports are generated (dry run)
"""

import requests
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


def check_server(url, name):
    """Check if a server is running."""
    try:
        response = requests.get(url, timeout=5)
        return response.status_code in [200, 401]  # 401 is fine for GitHub API without auth
    except:
        return False


def setup_test_data():
    """Set up test data in the database for GitHub monitoring."""
    db_path = Path.home() / ".series-db"
    
    with sqlite3.connect(str(db_path)) as conn:
        # Create tables if they don't exist
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
        
        # Insert test series
        test_series = [
            (1000, "testproject", "http://localhost:8000/api/series/1000/", 
             "Test User", "test@example.com", True, 1, "http://localhost:8000", 2, 
             "series_1000", "owner/repo", "abc1001000"),
            (1001, "testproject", "http://localhost:8000/api/series/1001/",
             "Another User", "another@example.com", True, 1, "http://localhost:8000", 2,
             "series_1001", "dpdk/dpdk", "abc1002000"),
        ]
        
        conn.executemany("""
            INSERT OR REPLACE INTO series (
                series_id, series_project, series_url, series_submitter, series_email,
                series_submitted, series_completed, series_instance, series_downloaded,
                series_branch, series_repo, series_sha
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, test_series)
        
        # Insert test builds for GitHub monitoring
        test_builds = [
            # Series 1000 builds
            (1000, 100001, "http://localhost:8000/api/patches/100001/", 
             "[PATCH 1/3] Test patch 1", "abc1001001", "http://localhost:8000", 
             "testproject", "owner/repo", 0, 0, 0),
            (1000, 100002, "http://localhost:8000/api/patches/100002/",
             "[PATCH 2/3] Test patch 2", "abc1001002", "http://localhost:8000",
             "testproject", "owner/repo", 0, 0, 0),
            (1000, 100003, "http://localhost:8000/api/patches/100003/",
             "[PATCH 3/3] Test patch 3", "abc1001003", "http://localhost:8000",
             "testproject", "owner/repo", 0, 0, 0),
            
            # Series 1001 builds  
            (1001, 100101, "http://localhost:8000/api/patches/100101/",
             "[PATCH 1/2] DPDK test patch 1", "abc1002001", "http://localhost:8000",
             "testproject", "dpdk/dpdk", 0, 0, 0),
            (1001, 100102, "http://localhost:8000/api/patches/100102/",
             "[PATCH 2/2] DPDK test patch 2", "abc1002002", "http://localhost:8000", 
             "testproject", "dpdk/dpdk", 0, 0, 0),
        ]
        
        conn.executemany("""
            INSERT OR REPLACE INTO git_builds (
                series_id, patch_id, patch_url, patch_name, sha,
                patchwork_instance, patchwork_project, repo_name,
                gap_sync, obs_sync, cirrus_sync
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, test_builds)
        
        conn.commit()
        print("✓ Test data inserted into database")


def run_test_command(cmd, description):
    """Run a test command and show results."""
    print(f"\n{'='*60}")
    print(f"Test: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    try:
        # Patch the GitHub API base URL to use our fake server
        env = {
            "GITHUB_API_BASE": "http://localhost:8001"
        }
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30, env=env
        )
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)
        
        success = result.returncode == 0
        print(f"\nResult: {'✓ PASS' if success else '✗ FAIL'} (exit code: {result.returncode})")
        
        return success
    
    except subprocess.TimeoutExpired:
        print("✗ FAIL (timeout after 30 seconds)")
        return False
    except Exception as e:
        print(f"✗ FAIL (error: {e})")
        return False


def test_api_endpoints():
    """Test the fake API endpoints directly."""
    print("\n" + "="*60)
    print("Testing API Endpoints")
    print("="*60)
    
    tests = [
        ("Patchwork series", "http://localhost:8000/api/series/1000/"),
        ("Patchwork events", "http://localhost:8000/api/events/?category=series-created&project=testproject"),
        ("GitHub repository", "http://localhost:8001/repos/owner/repo", {"Authorization": "token fake"}),
        ("GitHub workflow runs", "http://localhost:8001/repos/owner/repo/actions/runs?branch=series_1000", {"Authorization": "token fake"}),
    ]
    
    for name, url, *headers in tests:
        try:
            headers_dict = headers[0] if headers else {}
            response = requests.get(url, headers=headers_dict, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✓ {name}: {response.status_code} ({len(str(data))} chars)")
            else:
                print(f"✗ {name}: {response.status_code}")
        except Exception as e:
            print(f"✗ {name}: Error - {e}")


def main():
    """Run GitHub integration tests."""
    print("GitHub Actions Integration Testing")
    print("="*50)
    
    # Check if servers are running
    if not check_server("http://localhost:8000/api/series/1000/", "Patchwork"):
        print("❌ Patchwork server not running on localhost:8000")
        print("Please start it with: python fake_patchwork_server.py")
        sys.exit(1)
    
    if not check_server("http://localhost:8001/repos/owner/repo", "GitHub"):
        print("❌ GitHub server not running on localhost:8001") 
        print("Please start it with: python fake_github_server.py")
        sys.exit(1)
    
    print("✅ Both servers are running")
    
    # Test API endpoints
    test_api_endpoints()
    
    # Set up test data
    setup_test_data()
    
    # Test pw-ci with GitHub provider
    tests = [
        # Test GitHub CI monitoring with fake API
        (["python", "-m", "pwci.cli", "ci-monitor",
          "--pw-instance", "http://localhost:8000",
          "--pw-project", "testproject",
          "--from-addr", "ci-test@example.com", 
          "--to-addr", "results-test@example.com",
          "--github-token", "fake_github_token",
          "--dry-run"],
         "GitHub Actions CI monitoring"),
        
        # Test with specific repository
        (["python", "-c", """
import os
os.environ['GITHUB_API_BASE'] = 'http://localhost:8001'
from pwci.database import SeriesDatabase
from pwci.ci_providers import GitHubActionsProvider

db = SeriesDatabase()
provider = GitHubActionsProvider('fake_token', db)

print('Testing GitHub provider...')
results = list(provider.get_build_results('http://localhost:8000', 'testproject'))
print(f'Found {len(results)} build results')
for result in results:
    print(f'  Series {result["series_id"]}: {result["result"]} - {result["build_url"]}')
"""],
         "GitHub provider direct test"),
    ]
    
    results = []
    for cmd, description in tests:
        success = run_test_command(cmd, description)
        results.append((description, success))
        time.sleep(2)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for description, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status:8} {description}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All GitHub integration tests passed!")
        print("\nThe fake GitHub server provides:")
        print("  • Workflow runs for series branches")
        print("  • Multiple workflows per series") 
        print("  • Realistic build status and URLs")
        print("  • Proper GitHub API response format")
        print("  • Job details and step information")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()