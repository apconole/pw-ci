#!/usr/bin/env python3
"""
Test script to demonstrate pw-ci with the fake Patchwork server.
"""

import subprocess
import sys
import time
from pathlib import Path

def run_command(cmd, description):
    """Run a command and show its output."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print('='*60)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        if result.returncode != 0:
            print(f"Command failed with return code: {result.returncode}")
        
        return result.returncode == 0
    
    except subprocess.TimeoutExpired:
        print("Command timed out after 30 seconds")
        return False
    except Exception as e:
        print(f"Error running command: {e}")
        return False


def check_server_running():
    """Check if the fake server is running."""
    import requests
    try:
        response = requests.get("http://localhost:8000/api/series/1000/", timeout=5)
        return response.status_code == 200
    except:
        return False


def main():
    """Run tests with the fake Patchwork server."""
    print("pw-ci Testing with Fake Patchwork Server")
    print("="*50)
    
    # Check if server is running
    if not check_server_running():
        print("ERROR: Fake Patchwork server is not running on localhost:8000")
        print("Please start it with: python fake_patchwork_server.py")
        sys.exit(1)
    
    print("✓ Fake Patchwork server is running")
    
    # Set up test configuration
    config_dir = Path.home()
    test_config = config_dir / ".pwmon-test-rc"
    
    with open(test_config, "w") as f:
        f.write("""# Test configuration for pw-ci
pw_instance=http://localhost:8000
pw_project=testproject
from_addr=test-ci@example.com
to_addr=test-results@example.com
github_token=fake_github_token_for_testing
dummy_token=1111
""")
    
    print(f"✓ Created test config: {test_config}")
    
    # Test commands
    tests = [
        # Test basic series info
        (["python", "-m", "pwci.cli", "series-info", 
          "--pw-instance", "http://localhost:8000", 
          "--series-id", "1000"], 
         "Get series information"),
        
        # Test patchwork monitoring
        (["python", "-m", "pwci.cli", "monitor",
          "--pw-instance", "http://localhost:8000",
          "--pw-project", "testproject"],
         "Monitor patchwork for new series"),
        
        # Test series listing
        (["python", "-m", "pwci.cli", "list-series",
          "--pw-instance", "http://localhost:8000",
          "--pw-project", "testproject"],
         "List series in database"),
        
        # Test CI monitoring in dry-run mode
        (["python", "-m", "pwci.cli", "ci-monitor",
          "--pw-instance", "http://localhost:8000",
          "--pw-project", "testproject",
          "--from-addr", "test-ci@example.com",
          "--to-addr", "test-results@example.com",
          "--enable-dummy",
          "--dry-run"],
         "Monitor CI systems (dry run)"),
    ]
    
    results = []
    
    for cmd, description in tests:
        success = run_command(cmd, description)
        results.append((description, success))
        time.sleep(1)  # Brief pause between tests
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    total = len(results)
    
    for description, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status:8} {description}")
        if success:
            passed += 1
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    # Cleanup
    if test_config.exists():
        test_config.unlink()
        print(f"✓ Cleaned up test config: {test_config}")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        sys.exit(0)
    else:
        print(f"\n❌ {total - passed} tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()