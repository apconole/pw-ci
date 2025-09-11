"""Patchwork API client and monitoring functionality."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from dateutil.parser import parse as parse_date


class PatchworkClient:
    """Client for interacting with Patchwork instances."""

    def __init__(self, instance_url: str, credentials: Optional[str] = None):
        self.base_url = instance_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': '(pw-ci) python-client'
        })

        if credentials:
            username, password = credentials.split(':', 1)
            self.session.auth = (username, password)

    def _get(self, endpoint: str, params: Optional[Dict] = None) -> requests.Response:
        """Make a GET request to the Patchwork API."""
        url = urljoin(self.base_url + '/', endpoint.lstrip('/'))
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response

    def get_series_events(self, project: str, since: Optional[datetime] = None) -> List[Dict]:
        """Get series creation events from Patchwork."""
        params = {
            'category': 'series-created',
            'project': project
        }

        if since:
            params['since'] = since.strftime('%Y-%m-%d %H:%M:%S')

        response = self._get('/api/events/', params)
        return response.json()

    def get_series(self, series_id: int) -> Dict:
        """Get series details by ID."""
        response = self._get(f'/api/series/{series_id}/')
        return response.json()

    def get_series_list(self, project: str, state: List[str] = None, 
                       archived: bool = False, order: str = '-id') -> List[Dict]:
        """Get list of series matching criteria."""
        params = {
            'project': project,
            'archived': archived,
            'order': order
        }

        if state:
            for s in state:
                params[f'state'] = s

        response = self._get('/api/series/', params)
        return response.json()

    def get_patch(self, patch_url: str) -> Dict:
        """Get patch details from URL."""
        response = self.session.get(patch_url)
        response.raise_for_status()
        return response.json()

    def get_patch_comments(self, comments_url: str) -> List[Dict]:
        """Get comments for a patch."""
        response = self.session.get(comments_url)
        response.raise_for_status()
        return response.json()


class PatchworkMonitor:
    """Monitor Patchwork instances for new series and updates."""

    def __init__(self, client: PatchworkClient, database, project: str):
        self.client = client
        self.db = database
        self.project = project
        self.instance = client.base_url

        # Track timestamp files like the original bash script
        self.home = Path.home()
        self.timestamp_file = self.home / f".pwmon-{self.instance.replace('https://', '').replace('http://','')}-{project}-series"

    def _get_last_check_time(self) -> datetime:
        """Get the last time we checked for new series."""
        if not self.timestamp_file.exists():
            # Default to yesterday if no timestamp file exists
            return datetime.now() - timedelta(days=1)

        # Get modification time of timestamp file
        mtime = self.timestamp_file.stat().st_mtime
        return datetime.fromtimestamp(mtime)

    def _update_timestamp(self) -> None:
        """Update the timestamp file."""
        self.timestamp_file.touch()

    def emit_series(self, series_id: int, url: str, submitter_name: str,
                    submitter_email: str, all_received: bool) -> None:
        """Process and potentially add a series to the database."""
        if not self.db.series_exists(self.instance, series_id):
            print("=" * 45)
            print(f"Series instance: {self.instance}")
            print(f"Series id:       {series_id}")
            print(f"Series url:      {url}")
            print(f"submitter:       {submitter_name} <{submitter_email}>")
            print(f"all:             {all_received}")
            print(f"recording series ({series_id}, \"{url}\", \"{submitter_name}\", \"{submitter_email}\")")
            print()

            self.db.add_series(
                self.instance, self.project, series_id, url,
                submitter_name, submitter_email, all_received
            )

    def check_new_series(self) -> None:
        """Check for new series since last run."""
        last_check = self._get_last_check_time()

        try:
            events = self.client.get_series_events(self.project, since=last_check)
        except requests.RequestException as e:
            print(f"Error fetching series events: {e}")
            return

        for event in events:
            series_id = event['payload']['series']['id']

            try:
                series_data = self.client.get_series(series_id)
                self.emit_series(
                    series_id,
                    series_data['url'],
                    series_data['submitter']['name'],
                    series_data['submitter']['email'],
                    series_data.get('received_all', False)
                )
            except requests.RequestException as e:
                print(f"Error fetching series {series_id}: {e}")
                continue

        self._update_timestamp()

    def check_completed_series(self) -> None:
        """Check if previously incomplete series are now complete."""
        uncompleted = self.db.get_uncompleted_series(self.instance, self.project)

        for series_id, url, submitter_name, submitter_email in uncompleted:
            print(f"Checking on series: {series_id}")
            try:
                series_data = self.client.get_series(series_id)
                if series_data.get('received_all', False):
                    print(f"Setting series {series_id} to completed")
                    self.db.set_series_completed(self.instance, series_id)
            except requests.RequestException as e:
                print(f"Error checking series {series_id}: {e}")
                continue

    def check_superseded_series(self) -> None:
        """Check for superseded series and clean up branches."""
        active_branches = self.db.get_active_branches(self.instance)

        for series_id, project, url, branchname, repo in active_branches:
            try:
                series_data = self.client.get_series(series_id)
                if not series_data.get('patches'):
                    continue

                # Check the last patch state
                last_patch = series_data['patches'][-1]
                patch_data = self.client.get_patch(last_patch['url'])
                patch_state = patch_data.get('state', '')

                if patch_state in ['superseded', 'rejected', 'accepted', 
                                 'changes-requested', 'not-applicable']:
                    self.db.clear_series_branch(self.instance, series_id)
                    print(f"Cleared branch for series {series_id}: state {patch_state}")

            except requests.RequestException as e:
                print(f"Error checking series {series_id}: {e}")
                continue

    def check_recheck_requests(self, recheck_filters: List[str]) -> None:
        """Check for recheck requests in patch comments."""
        if not recheck_filters:
            return

        try:
            series_list = self.client.get_series_list(
                self.project,
                state=['new', 'rfc', 'under-review'],
                archived=False,
                order='-id'
            )
        except requests.RequestException as e:
            print(f"Error fetching series list: {e}")
            return

        for series in series_list:
            patches = series.get('patches', [])
            for patch in patches:
                self._check_patch_for_recheck(patch['url'], recheck_filters)

    def _check_patch_for_recheck(self, patch_url: str, recheck_filters: List[str]) -> None:
        """Check a single patch for recheck requests."""
        try:
            patch_data = self.client.get_patch(patch_url)

            # Skip patches in final states
            patch_state = patch_data.get('state', '')
            if patch_state in ['superseded', 'rejected', 'accepted', 
                             'changes-requested', 'not-applicable']:
                return

            comments_url = patch_data.get('comments')
            if not comments_url or comments_url == 'null':
                return

            comments = self.client.get_patch_comments(comments_url)
            for comment in comments:
                content = comment.get('content', '')
                if content.startswith('Recheck-request: '):
                    recheck_list = content.replace('Recheck-request: ', '').split(', ')

                    for filter_name in recheck_filters:
                        if filter_name in recheck_list:
                            print(f"Recheck matched: {patch_data['id']} {filter_name}")
                            # Here you would insert the recheck request into the database
                            # Implementation depends on your recheck handling logic

        except requests.RequestException as e:
            print(f"Error checking patch {patch_url}: {e}")

    def run_full_check(self, recheck_filters: Optional[List[str]] = None) -> None:
        """Run a complete monitoring cycle."""
        print(f"Monitoring {self.instance} project {self.project}")

        # Check for new series
        self.check_new_series()

        # Check completed series
        self.check_completed_series()

        # Check for superseded series
        self.check_superseded_series()

        # Check for recheck requests if filters provided
        if recheck_filters:
            self.check_recheck_requests(recheck_filters)
