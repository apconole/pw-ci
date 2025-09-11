#!/usr/bin/env python3
"""
Fake GitHub REST API server for testing pw-ci GitHub Actions integration.

This server provides mock GitHub API endpoints to test the GitHub Actions
CI provider without requiring real GitHub tokens or repositories.
"""

import json
import random
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# Sample data
REPOSITORIES = {
    "owner/repo": {
        "id": 123456,
        "name": "repo", 
        "owner": {"login": "owner"},
        "full_name": "owner/repo",
        "private": False,
        "default_branch": "main"
    },
    "dpdk/dpdk": {
        "id": 789012,
        "name": "dpdk",
        "owner": {"login": "dpdk"},
        "full_name": "dpdk/dpdk", 
        "private": False,
        "default_branch": "main"
    },
    "openvswitch/ovs": {
        "id": 345678,
        "name": "ovs",
        "owner": {"login": "openvswitch"},
        "full_name": "openvswitch/ovs",
        "private": False,
        "default_branch": "master"
    }
}

WORKFLOW_NAMES = [
    "Build and Test",
    "CI", 
    "Linux Build",
    "Windows Build",
    "MacOS Build",
    "Documentation",
    "Static Analysis",
    "Integration Tests"
]

CONCLUSIONS = ["success", "failure", "cancelled", "timed_out", "skipped", "neutral"]
STATUSES = ["queued", "in_progress", "completed"]

# Global state for workflow runs
WORKFLOW_RUNS = {}


def generate_workflow_run(run_id: int, repo_name: str, branch: str, sha: str = None) -> dict:
    """Generate a fake GitHub Actions workflow run."""
    if sha is None:
        sha = f"abc{run_id:09d}"
    
    workflow_name = random.choice(WORKFLOW_NAMES)
    status = random.choice(STATUSES)
    
    if status == "completed":
        conclusion = random.choice(CONCLUSIONS)
    else:
        conclusion = None
    
    created_time = datetime.now() - timedelta(hours=random.randint(1, 24))
    updated_time = created_time + timedelta(minutes=random.randint(5, 120))
    
    if status == "completed":
        run_started_at = created_time + timedelta(minutes=1)
        run_completed_at = updated_time
    else:
        run_started_at = created_time + timedelta(minutes=1)
        run_completed_at = None
    
    run = {
        "id": run_id,
        "name": workflow_name,
        "head_branch": branch,
        "head_sha": sha,
        "path": f".github/workflows/{workflow_name.lower().replace(' ', '_')}.yml",
        "display_title": f"{workflow_name} for {branch}",
        "run_number": random.randint(1, 1000),
        "event": "push",
        "status": status,
        "conclusion": conclusion,
        "workflow_id": random.randint(1000000, 9999999),
        "check_suite_id": random.randint(1000000, 9999999),
        "check_suite_node_id": f"CS_kwDOABCD{run_id}",
        "url": f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}",
        "html_url": f"https://github.com/{repo_name}/actions/runs/{run_id}",
        "pull_requests": [],
        "created_at": created_time.isoformat() + "Z",
        "updated_at": updated_time.isoformat() + "Z",
        "actor": {
            "login": "github-actions[bot]",
            "id": 41898282,
            "type": "Bot"
        },
        "run_attempt": 1,
        "referenced_workflows": [],
        "run_started_at": run_started_at.isoformat() + "Z" if run_started_at else None,
        "triggering_actor": {
            "login": "test-user",
            "id": random.randint(1000, 9999),
            "type": "User"
        },
        "jobs_url": f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}/jobs",
        "logs_url": f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}/logs",
        "check_suite_url": f"https://api.github.com/repos/{repo_name}/check-suites/{random.randint(1000000, 9999999)}",
        "artifacts_url": f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}/artifacts",
        "cancel_url": f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}/cancel",
        "rerun_url": f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}/rerun",
        "previous_attempt_url": None,
        "workflow_url": f"https://api.github.com/repos/{repo_name}/actions/workflows/{random.randint(1000000, 9999999)}",
        "head_commit": {
            "id": sha,
            "tree_id": f"tree{run_id:09d}",
            "message": f"Test commit for {branch}",
            "timestamp": created_time.isoformat() + "Z",
            "author": {
                "name": "Test User",
                "email": "test@example.com"
            },
            "committer": {
                "name": "Test User", 
                "email": "test@example.com"
            }
        },
        "repository": REPOSITORIES.get(repo_name, {
            "id": random.randint(100000, 999999),
            "name": repo_name.split("/")[-1],
            "full_name": repo_name,
            "owner": {"login": repo_name.split("/")[0]},
            "private": False
        }),
        "head_repository": REPOSITORIES.get(repo_name, {
            "id": random.randint(100000, 999999),
            "name": repo_name.split("/")[-1],
            "full_name": repo_name,
            "owner": {"login": repo_name.split("/")[0]},
            "private": False
        })
    }
    
    if run_completed_at:
        run["run_completed_at"] = run_completed_at.isoformat() + "Z"
    
    return run


def generate_jobs_for_run(run_id: int, repo_name: str, workflow_name: str) -> list:
    """Generate fake jobs for a workflow run."""
    jobs = []
    num_jobs = random.randint(1, 4)
    
    job_names = [
        "build",
        "test", 
        "lint",
        "security-scan",
        f"build-{random.choice(['ubuntu', 'windows', 'macos'])}"
    ]
    
    for i in range(num_jobs):
        job_id = run_id * 100 + i + 1
        job_name = random.choice(job_names)
        
        status = random.choice(STATUSES)
        if status == "completed":
            conclusion = random.choice(CONCLUSIONS[:3])  # success, failure, cancelled
        else:
            conclusion = None
        
        started_time = datetime.now() - timedelta(minutes=random.randint(10, 60))
        completed_time = started_time + timedelta(minutes=random.randint(2, 30)) if status == "completed" else None
        
        job = {
            "id": job_id,
            "run_id": run_id,
            "workflow_name": workflow_name,
            "head_branch": f"series_{random.randint(1000, 9999)}",
            "run_url": f"https://api.github.com/repos/{repo_name}/actions/runs/{run_id}",
            "run_attempt": 1,
            "node_id": f"J_kwDOABCD{job_id}",
            "head_sha": f"abc{run_id:09d}",
            "url": f"https://api.github.com/repos/{repo_name}/actions/jobs/{job_id}",
            "html_url": f"https://github.com/{repo_name}/actions/runs/{run_id}/jobs/{job_id}",
            "status": status,
            "conclusion": conclusion,
            "created_at": started_time.isoformat() + "Z",
            "started_at": started_time.isoformat() + "Z",
            "completed_at": completed_time.isoformat() + "Z" if completed_time else None,
            "name": job_name,
            "steps": [
                {
                    "name": "Checkout",
                    "status": "completed",
                    "conclusion": "success",
                    "number": 1,
                    "started_at": started_time.isoformat() + "Z",
                    "completed_at": (started_time + timedelta(minutes=1)).isoformat() + "Z"
                },
                {
                    "name": f"Run {job_name}",
                    "status": status,
                    "conclusion": conclusion,
                    "number": 2,
                    "started_at": (started_time + timedelta(minutes=1)).isoformat() + "Z",
                    "completed_at": completed_time.isoformat() + "Z" if completed_time else None
                }
            ],
            "check_run_url": f"https://api.github.com/repos/{repo_name}/check-runs/{job_id}",
            "labels": [random.choice(["ubuntu-latest", "windows-latest", "macos-latest"])],
            "runner_id": random.randint(1, 100),
            "runner_name": f"GitHub Actions {random.randint(1, 20)}",
            "runner_group_id": 1,
            "runner_group_name": "GitHub Actions"
        }
        
        jobs.append(job)
    
    return jobs


class GitHubHandler(BaseHTTPRequestHandler):
    """HTTP request handler for fake GitHub API."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)
        
        # Check for authorization header
        auth_header = self.headers.get('Authorization')
        if not auth_header or not auth_header.startswith(('token ', 'Bearer ')):
            self.send_error(401, "Bad credentials")
            return
        
        try:
            if path.startswith("/repos/") and "/actions/runs" in path:
                self.handle_actions_runs(path, query_params)
            elif path.startswith("/repos/") and "/actions/jobs" in path:
                self.handle_actions_jobs(path, query_params)
            elif path.startswith("/repos/"):
                self.handle_repository(path, query_params)
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            print(f"Error handling request {path}: {e}")
            self.send_error(500, "Internal Server Error")
    
    def handle_actions_runs(self, path, query_params):
        """Handle /repos/{owner}/{repo}/actions/runs requests."""
        path_parts = path.strip("/").split("/")
        
        if len(path_parts) >= 4:
            owner = path_parts[1]
            repo = path_parts[2]
            repo_name = f"{owner}/{repo}"
            
            if len(path_parts) == 4:  # List workflow runs
                branch = query_params.get("branch", [None])[0]
                per_page = int(query_params.get("per_page", ["30"])[0])
                
                # Generate workflow runs for the requested branch
                workflow_runs = []
                
                if branch and branch.startswith("series_"):
                    series_id = branch.replace("series_", "")
                    
                    # Generate multiple workflow runs for this series
                    for i in range(random.randint(2, 6)):
                        run_id = int(series_id) * 1000 + i + 1
                        sha = f"abc{run_id:09d}"
                        
                        run = generate_workflow_run(run_id, repo_name, branch, sha)
                        workflow_runs.append(run)
                        WORKFLOW_RUNS[run_id] = run
                
                # Sort by run number (newest first)
                workflow_runs.sort(key=lambda x: x["run_number"], reverse=True)
                workflow_runs = workflow_runs[:per_page]
                
                response = {
                    "total_count": len(workflow_runs),
                    "workflow_runs": workflow_runs
                }
                
                self.send_json_response(response)
            
            elif len(path_parts) == 5:  # Individual workflow run
                run_id = int(path_parts[4])
                
                if run_id not in WORKFLOW_RUNS:
                    # Generate a workflow run if it doesn't exist
                    WORKFLOW_RUNS[run_id] = generate_workflow_run(run_id, repo_name, f"series_{run_id // 1000}")
                
                self.send_json_response(WORKFLOW_RUNS[run_id])
            
            elif len(path_parts) == 6 and path_parts[5] == "jobs":  # Jobs for a run
                run_id = int(path_parts[4])
                
                if run_id not in WORKFLOW_RUNS:
                    WORKFLOW_RUNS[run_id] = generate_workflow_run(run_id, repo_name, f"series_{run_id // 1000}")
                
                run = WORKFLOW_RUNS[run_id]
                jobs = generate_jobs_for_run(run_id, repo_name, run["name"])
                
                response = {
                    "total_count": len(jobs),
                    "jobs": jobs
                }
                
                self.send_json_response(response)
            
            else:
                self.send_error(404, "Not Found")
        else:
            self.send_error(404, "Not Found")
    
    def handle_actions_jobs(self, path, query_params):
        """Handle /repos/{owner}/{repo}/actions/jobs/{job_id} requests."""
        path_parts = path.strip("/").split("/")
        
        if len(path_parts) == 6:
            owner = path_parts[1]
            repo = path_parts[2]
            job_id = int(path_parts[5])
            repo_name = f"{owner}/{repo}"
            
            # Generate a job if it doesn't exist
            run_id = job_id // 100
            jobs = generate_jobs_for_run(run_id, repo_name, "Test Workflow")
            
            # Find the specific job
            job = None
            for j in jobs:
                if j["id"] == job_id:
                    job = j
                    break
            
            if job:
                self.send_json_response(job)
            else:
                self.send_error(404, "Not Found")
        else:
            self.send_error(404, "Not Found")
    
    def handle_repository(self, path, query_params):
        """Handle repository requests."""
        path_parts = path.strip("/").split("/")
        
        if len(path_parts) == 3:  # /repos/{owner}/{repo}
            owner = path_parts[1]
            repo = path_parts[2]
            repo_name = f"{owner}/{repo}"
            
            if repo_name in REPOSITORIES:
                self.send_json_response(REPOSITORIES[repo_name])
            else:
                # Generate a repository if it doesn't exist
                repository = {
                    "id": random.randint(100000, 999999),
                    "name": repo,
                    "full_name": repo_name,
                    "owner": {
                        "login": owner,
                        "id": random.randint(1000, 9999),
                        "type": "User"
                    },
                    "private": False,
                    "html_url": f"https://github.com/{repo_name}",
                    "description": f"Test repository for {repo_name}",
                    "default_branch": "main",
                    "created_at": "2020-01-01T00:00:00Z",
                    "updated_at": datetime.now().isoformat() + "Z",
                    "pushed_at": datetime.now().isoformat() + "Z"
                }
                REPOSITORIES[repo_name] = repository
                self.send_json_response(repository)
        else:
            self.send_error(404, "Not Found")
    
    def send_json_response(self, data, status=200):
        """Send a JSON response."""
        response = json.dumps(data, indent=2)
        
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        # Add GitHub API headers
        self.send_header("X-RateLimit-Limit", "5000")
        self.send_header("X-RateLimit-Remaining", "4999")
        self.send_header("X-RateLimit-Reset", str(int(time.time()) + 3600))
        self.end_headers()
        
        self.wfile.write(response.encode("utf-8"))
    
    def send_error(self, code, message=None):
        """Send an error response in GitHub API format."""
        if code == 401:
            error_response = {
                "message": "Bad credentials",
                "documentation_url": "https://docs.github.com/rest"
            }
        elif code == 404:
            error_response = {
                "message": "Not Found",
                "documentation_url": "https://docs.github.com/rest"
            }
        else:
            error_response = {
                "message": message or "Internal Server Error",
                "documentation_url": "https://docs.github.com/rest"
            }
        
        self.send_json_response(error_response, code)
    
    def log_message(self, format, *args):
        """Override to provide cleaner logging."""
        print(f"{self.client_address[0]} - - [{self.log_date_time_string()}] {format % args}")


def main():
    """Start the fake GitHub API server."""
    # Pre-populate some workflow runs
    for repo in ["owner/repo", "dpdk/dpdk"]:
        for series_id in [1000, 1001, 1002]:
            branch = f"series_{series_id}"
            for i in range(3):
                run_id = series_id * 1000 + i + 1
                WORKFLOW_RUNS[run_id] = generate_workflow_run(run_id, repo, branch)
    
    server_address = ("", 8001)
    httpd = HTTPServer(server_address, GitHubHandler)
    
    print("Starting fake GitHub API server on http://localhost:8001")
    print("Available endpoints:")
    print("  GET /repos/{owner}/{repo}/actions/runs?branch=series_1000")
    print("  GET /repos/{owner}/{repo}/actions/runs/{run_id}")
    print("  GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs")
    print("  GET /repos/{owner}/{repo}")
    print()
    print("Example repositories: owner/repo, dpdk/dpdk, openvswitch/ovs")
    print("Example branches: series_1000, series_1001, series_1002")
    print("Authorization: Include 'Authorization: token fake_token' header")
    print("\nPress Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    main()