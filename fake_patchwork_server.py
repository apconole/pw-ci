#!/usr/bin/env python3
"""
Fake Patchwork HTTP server for testing pw-ci.

This server provides a mock Patchwork API with dummy data for testing
the Python pw-ci implementation.
"""

import json
import random
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# Sample data
PROJECTS = ["dpdk", "openvswitch", "testproject"]
STATES = ["new", "under-review", "accepted", "superseded", "rejected"]
SUBMITTERS = [
    {"name": "John Doe", "email": "john@example.com"},
    {"name": "Jane Smith", "email": "jane@example.com"},
    {"name": "Bob Wilson", "email": "bob@example.com"},
    {"name": "Alice Johnson", "email": "alice@example.com"},
]

# Global state for series/patches
SERIES_DATA = {}
PATCH_DATA = {}
EVENT_DATA = []


def generate_series(series_id: int, project: str = "testproject") -> dict:
    """Generate a fake series."""
    submitter = random.choice(SUBMITTERS)
    received_all = random.choice([True, False])
    created_date = datetime.now() - timedelta(days=random.randint(1, 30))
    
    # Generate patches for this series
    num_patches = random.randint(1, 5)
    patches = []
    
    for i in range(num_patches):
        patch_id = series_id * 100 + i + 1
        patch = generate_patch(patch_id, series_id, project, submitter, i)
        patches.append({
            "id": patch_id,
            "url": f"http://localhost:8000/api/patches/{patch_id}/",
            "name": patch["name"],
            "date": patch["date"]
        })
        PATCH_DATA[patch_id] = patch
    
    series = {
        "id": series_id,
        "url": f"http://localhost:8000/api/series/{series_id}/",
        "name": f"Test series {series_id}",
        "date": created_date.isoformat(),
        "submitter": submitter,
        "project": project,
        "version": 1,
        "total": num_patches,
        "received_total": num_patches if received_all else num_patches - 1,
        "received_all": received_all,
        "cover_letter": None,
        "patches": patches
    }
    
    return series


def generate_patch(patch_id: int, series_id: int, project: str, submitter: dict, index: int) -> dict:
    """Generate a fake patch."""
    state = random.choice(STATES)
    created_date = datetime.now() - timedelta(days=random.randint(1, 30))
    
    patch = {
        "id": patch_id,
        "url": f"http://localhost:8000/api/patches/{patch_id}/",
        "project": project,
        "msgid": f"<patch-{patch_id}-{int(time.time())}@example.com>",
        "date": created_date.isoformat(),
        "name": f"[PATCH {index+1}/{random.randint(1,5)}] Test patch {patch_id}",
        "commit_ref": f"abcdef{patch_id:06d}",
        "pull_url": None,
        "state": state,
        "archived": False,
        "hash": f"sha256:{patch_id:064d}",
        "submitter": submitter,
        "delegate": None,
        "mbox": f"http://localhost:8000/api/patches/{patch_id}/mbox/",
        "series": [{"id": series_id, "url": f"http://localhost:8000/api/series/{series_id}/"}],
        "comments": f"http://localhost:8000/api/patches/{patch_id}/comments/",
        "check": "pending",
        "checks": f"http://localhost:8000/api/patches/{patch_id}/checks/",
        "tags": []
    }
    
    return patch


def generate_comments(patch_id: int) -> list:
    """Generate fake comments for a patch."""
    comments = []
    num_comments = random.randint(0, 3)
    
    for i in range(num_comments):
        comment_date = datetime.now() - timedelta(days=random.randint(1, 10))
        comment = {
            "id": patch_id * 10 + i + 1,
            "msgid": f"<comment-{patch_id}-{i}@example.com>",
            "date": comment_date.isoformat(),
            "subject": f"Re: [PATCH] Test patch {patch_id}",
            "submitter": random.choice(SUBMITTERS),
            "content": f"This is comment {i+1} on patch {patch_id}.\n\nLooks good to me!"
        }
        
        # Occasionally add recheck requests
        if random.random() < 0.2:
            comment["content"] += "\n\nRecheck-request: github, travis"
        
        comments.append(comment)
    
    return comments


def generate_events(project: str, since: datetime = None) -> list:
    """Generate fake series creation events."""
    events = []
    
    if since is None:
        since = datetime.now() - timedelta(days=7)
    
    # Generate some events since the specified time
    num_events = random.randint(1, 5)
    for i in range(num_events):
        event_time = since + timedelta(hours=random.randint(1, 168))  # Up to 7 days
        series_id = random.randint(1000, 9999)
        
        # Create series if it doesn't exist
        if series_id not in SERIES_DATA:
            SERIES_DATA[series_id] = generate_series(series_id, project)
        
        event = {
            "id": len(EVENT_DATA) + 1,
            "category": "series-created",
            "project": project,
            "date": event_time.isoformat(),
            "actor": random.choice(SUBMITTERS),
            "payload": {
                "series": {
                    "id": series_id,
                    "url": f"http://localhost:8000/api/series/{series_id}/",
                    "name": f"Test series {series_id}"
                }
            }
        }
        
        events.append(event)
        EVENT_DATA.append(event)
    
    return events


class PatchworkHandler(BaseHTTPRequestHandler):
    """HTTP request handler for fake Patchwork API."""
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query_params = parse_qs(parsed_url.query)
        
        try:
            if path == "/api/events/":
                self.handle_events(query_params)
            elif path.startswith("/api/series/"):
                self.handle_series(path, query_params)
            elif path.startswith("/api/patches/"):
                self.handle_patches(path, query_params)
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            print(f"Error handling request {path}: {e}")
            self.send_error(500, "Internal Server Error")
    
    def handle_events(self, query_params):
        """Handle /api/events/ requests."""
        category = query_params.get("category", [None])[0]
        project = query_params.get("project", ["testproject"])[0]
        since_str = query_params.get("since", [None])[0]
        
        since = None
        if since_str:
            try:
                since = datetime.fromisoformat(since_str.replace("%20", " "))
            except ValueError:
                pass
        
        if category == "series-created":
            events = generate_events(project, since)
        else:
            events = []
        
        self.send_json_response(events)
    
    def handle_series(self, path, query_params):
        """Handle /api/series/ requests."""
        parts = path.strip("/").split("/")
        
        if len(parts) == 3 and parts[2].isdigit():
            # Individual series: /api/series/{id}/
            series_id = int(parts[2])
            
            if series_id not in SERIES_DATA:
                SERIES_DATA[series_id] = generate_series(series_id)
            
            self.send_json_response(SERIES_DATA[series_id])
        
        elif len(parts) == 2:
            # Series list: /api/series/
            project = query_params.get("project", ["testproject"])[0]
            states = query_params.get("state", ["new"])
            archived = query_params.get("archived", ["false"])[0].lower() == "true"
            order = query_params.get("order", ["-id"])[0]
            
            # Generate some series for the project
            series_list = []
            for i in range(5):
                series_id = random.randint(1000, 9999)
                if series_id not in SERIES_DATA:
                    SERIES_DATA[series_id] = generate_series(series_id, project)
                
                series = SERIES_DATA[series_id].copy()
                # Filter by state (check if any patches match the state)
                if any(PATCH_DATA.get(p["id"], {}).get("state") in states for p in series["patches"]):
                    series_list.append(series)
            
            # Sort by order
            if order.startswith("-"):
                series_list.sort(key=lambda x: x["id"], reverse=True)
            else:
                series_list.sort(key=lambda x: x["id"])
            
            self.send_json_response(series_list[:10])  # Limit to 10 results
        
        else:
            self.send_error(404, "Not Found")
    
    def handle_patches(self, path, query_params):
        """Handle /api/patches/ requests."""
        parts = path.strip("/").split("/")
        
        if len(parts) >= 3 and parts[2].isdigit():
            patch_id = int(parts[2])
            
            if len(parts) == 3:
                # Individual patch: /api/patches/{id}/
                if patch_id not in PATCH_DATA:
                    # Generate a patch if it doesn't exist
                    series_id = random.randint(1000, 9999)
                    submitter = random.choice(SUBMITTERS)
                    PATCH_DATA[patch_id] = generate_patch(patch_id, series_id, "testproject", submitter, 0)
                
                self.send_json_response(PATCH_DATA[patch_id])
            
            elif len(parts) == 4 and parts[3] == "comments":
                # Patch comments: /api/patches/{id}/comments/
                comments = generate_comments(patch_id)
                self.send_json_response(comments)
            
            elif len(parts) == 4 and parts[3] == "checks":
                # Patch checks: /api/patches/{id}/checks/
                checks = [
                    {
                        "id": 1,
                        "url": f"http://localhost:8000/api/checks/{patch_id}-1/",
                        "user": {"username": "github-ci"},
                        "date": datetime.now().isoformat(),
                        "state": random.choice(["pending", "success", "fail"]),
                        "target_url": f"https://github.com/example/repo/actions/runs/{random.randint(1000000, 9999999)}",
                        "context": "github-actions",
                        "description": "GitHub Actions CI"
                    }
                ]
                self.send_json_response(checks)
            
            else:
                self.send_error(404, "Not Found")
        else:
            self.send_error(404, "Not Found")
    
    def send_json_response(self, data):
        """Send a JSON response."""
        response = json.dumps(data, indent=2)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        self.wfile.write(response.encode("utf-8"))
    
    def log_message(self, format, *args):
        """Override to provide cleaner logging."""
        print(f"{self.client_address[0]} - - [{self.log_date_time_string()}] {format % args}")


def main():
    """Start the fake Patchwork server."""
    # Pre-populate some data
    for i in range(5):
        series_id = 1000 + i
        SERIES_DATA[series_id] = generate_series(series_id, "testproject")
    
    server_address = ("", 8000)
    httpd = HTTPServer(server_address, PatchworkHandler)
    
    print("Starting fake Patchwork server on http://localhost:8000")
    print("Available endpoints:")
    print("  GET /api/events/?category=series-created&project=testproject")
    print("  GET /api/series/{id}/")
    print("  GET /api/series/?project=testproject&state=new")
    print("  GET /api/patches/{id}/")
    print("  GET /api/patches/{id}/comments/")
    print("  GET /api/patches/{id}/checks/")
    print("\nPress Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    main()