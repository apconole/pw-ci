"""CI provider monitoring implementations."""

import json
from abc import ABC, abstractmethod
from typing import Dict, Iterator, List, Optional, Tuple

import requests
from github import Github, UnknownObjectException


class CIProvider(ABC):
    """Base class for CI providers."""
    
    def __init__(self, name: str, token: str, database):
        self.name = name
        self.token = token
        self.db = database
        self.sync_column = f"{name}_sync"

    @abstractmethod
    def get_build_results(self, pw_instance: str, pw_project: Optional[str] = None) -> Iterator[Dict]:
        """Get build results for unsynced builds."""
        pass


class GitHubActionsProvider(CIProvider):
    """GitHub Actions CI provider."""
    
    def __init__(self, token: str, database, api_base: str = "https://api.github.com"):
        super().__init__("gap", token, database)
        self.api_base = api_base
        self.github = Github(token, base_url=api_base) if api_base == "https://api.github.com" else None
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': '(pw-ci) github-actions-monitor'
        })

    def get_build_results(self, pw_instance: str, pw_project: Optional[str] = None) -> Iterator[Dict]:
        """Get GitHub Actions build results."""
        unsynced_builds = self.db.get_unsynced_builds(pw_instance, self.sync_column)

        prev_series = None
        all_runs = None
        prev_url = None

        for build in unsynced_builds:
            series_id = build['series_id']
            patch_id = build['patch_id']
            patch_url = build['patch_url']
            patch_name = build['patch_name']
            sha = build['sha']
            patchwork_instance = build['patchwork_instance']
            patchwork_project = build['patchwork_project']
            repo_name = build['repo_name']

            # Skip if project filter specified and doesn't match
            if pw_project and pw_project != patchwork_project:
                continue

            # Fetch workflow runs for this series if not cached
            if series_id != prev_series:
                prev_series = series_id
                api_url = f"{self.api_base}/repos/{repo_name}/actions/runs"
                params = {
                    'branch': f'series_{series_id}',
                    'per_page': 100
                }

                if api_url != prev_url:
                    prev_url = api_url
                    try:
                        response = self.session.get(api_url, params=params)
                        response.raise_for_status()
                        all_runs = response.json()
                    except requests.RequestException as e:
                        print(f"Error fetching GitHub Actions runs: {e}")
                        continue

            if not all_runs or 'workflow_runs' not in all_runs:
                continue

            # Process workflow runs
            workflow_runs = all_runs['workflow_runs']
            if not workflow_runs:
                continue

            # Group runs by workflow name, sorted by start time (newest first)
            workflow_groups = {}
            for run in workflow_runs:
                workflow_name = run['name']
                if workflow_name not in workflow_groups:
                    workflow_groups[workflow_name] = []
                workflow_groups[workflow_name].append(run)

            # Sort each group by start time (newest first)
            for workflow_name in workflow_groups:
                workflow_groups[workflow_name].sort(
                    key=lambda x: x['run_started_at'], 
                    reverse=True
                )

            # Get results for each workflow (using the latest run)
            for workflow_name, runs in workflow_groups.items():
                latest_run = runs[0]  # Most recent run

                status = latest_run['status']
                conclusion = latest_run['conclusion']
                build_url = latest_run['html_url']

                # Skip incomplete runs
                if status != 'completed':
                    print(f"patch_id={patch_id} series_id={series_id} not completed. Skipping")
                    continue

                # Map GitHub conclusion to our result format
                if conclusion == 'success':
                    result = 'passed'
                else:
                    result = 'failed'

                yield {
                    'pw_instance': pw_instance,
                    'series_id': series_id,
                    'sha': sha,
                    'result': result,
                    'build_url': build_url,
                    'patch_name': patch_name,
                    'repo_name': repo_name,
                    'test_name': workflow_name,
                    'patch_id': patch_id
                }

            # Mark this patch as synced
            self.db.set_build_synced(pw_instance, patch_id, self.sync_column)


class TravisProvider(CIProvider):
    """Travis CI provider."""

    def __init__(self, token: str, database):
        super().__init__("travis", token, database)
        self.api_base = "https://api.travis-ci.com"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'token {token}',
            'Travis-API-Version': '3',
            'User-Agent': '(pw-ci) travis-monitor'
        })

    def get_build_results(self, pw_instance: str, pw_project: Optional[str] = None) -> Iterator[Dict]:
        """Get Travis CI build results."""
        active_branches = self.db.get_active_branches(pw_instance)

        for series_id, project, series_url, branchname, travis_repo in active_branches:
            if pw_project and pw_project != project:
                continue

            # Get builds for this branch
            try:
                builds = self._get_builds_for_branch(travis_repo, branchname)
                for build in builds:
                    if build['state'] in ['created', 'canceled']:
                        continue

                    if build['state'] in ['failed', 'passed', 'errored']:
                        result = build['state']
                        if result == 'errored':
                            result = 'failed'

                        build_url = f"https://travis-ci.com/{travis_repo}/builds/{build['id']}"

                        yield {
                            'pw_instance': pw_instance,
                            'series_id': series_id,
                            'sha': build.get('commit', {}).get('sha', ''),
                            'result': result,
                            'build_url': build_url,
                            'patch_name': series_url,
                            'repo_name': travis_repo,
                            'test_name': '',
                            'patch_id': None
                        }

                        # Clear the branch since build is complete
                        self.db.clear_series_branch(pw_instance, series_id)
                        break

            except requests.RequestException as e:
                print(f"Error fetching Travis builds for {travis_repo}/{branchname}: {e}")
                continue

    def _get_builds_for_branch(self, repo: str, branch: str) -> List[Dict]:
        """Get builds for a specific repository branch."""
        url = f"{self.api_base}/repos/{repo}/builds"
        params = {
            'branch.name': branch,
            'limit': 10
        }

        response = self.session.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        return data.get('builds', [])


class CirrusProvider(CIProvider):
    """Cirrus CI provider."""

    def __init__(self, token: str, database):
        super().__init__("cirrus", token, database)
        self.api_base = "https://api.cirrus-ci.com/graphql"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': '(pw-ci) cirrus-monitor'
        })

    def get_build_results(self, pw_instance: str, pw_project: Optional[str] = None) -> Iterator[Dict]:
        """Get Cirrus CI build results."""
        unsynced_builds = self.db.get_unsynced_builds(pw_instance, self.sync_column)

        for build in unsynced_builds:
            if pw_project and pw_project != build['patchwork_project']:
                continue

            try:
                # Query Cirrus CI GraphQL API for build status
                query = """
                query BuildStatus($owner: String!, $name: String!, $branch: String!) {
                    ownerRepository(platform: "github", owner: $owner, name: $name) {
                        builds(branch: $branch, last: 10) {
                            edges {
                                node {
                                    id
                                    branch
                                    status
                                    buildCreatedTimestamp
                                    durationInSeconds
                                    repository {
                                        owner
                                        name
                                    }
                                    tasks {
                                        name
                                        status
                                    }
                                }
                            }
                        }
                    }
                }
                """

                repo_parts = build['repo_name'].split('/')
                if len(repo_parts) != 2:
                    continue

                variables = {
                    'owner': repo_parts[0],
                    'name': repo_parts[1],
                    'branch': f"series_{build['series_id']}"
                }

                response = self.session.post(
                    self.api_base,
                    json={'query': query, 'variables': variables}
                )
                response.raise_for_status()

                data = response.json()
                builds_data = data.get('data', {}).get('ownerRepository', {}).get('builds', {}).get('edges', [])

                for edge in builds_data:
                    node = edge['node']
                    status = node['status']

                    if status == 'COMPLETED':
                        # Check if any tasks failed
                        failed_tasks = [task for task in node.get('tasks', []) if task['status'] == 'FAILED']
                        result = 'failed' if failed_tasks else 'passed'

                        build_url = f"https://cirrus-ci.com/build/{node['id']}"

                        yield {
                            'pw_instance': pw_instance,
                            'series_id': build['series_id'],
                            'sha': build['sha'],
                            'result': result,
                            'build_url': build_url,
                            'patch_name': build['patch_name'],
                            'repo_name': build['repo_name'],
                            'test_name': 'cirrus-ci',
                            'patch_id': build['patch_id']
                        }

                        self.db.set_build_synced(pw_instance, build['patch_id'], self.sync_column)
                        break

            except requests.RequestException as e:
                print(f"Error fetching Cirrus CI build for series {build['series_id']}: {e}")
                continue


class DummyProvider(CIProvider):
    """Dummy CI provider for testing."""

    def __init__(self, token: str, database):
        super().__init__("dummy", token, database)

    def get_build_results(self, pw_instance: str, pw_project: Optional[str] = None) -> Iterator[Dict]:
        """Get dummy build results - always returns success."""
        unsynced_builds = self.db.get_unsynced_builds(pw_instance, self.sync_column)

        for build in unsynced_builds:
            if pw_project and pw_project != build['patchwork_project']:
                continue

            yield {
                'pw_instance': pw_instance,
                'series_id': build['series_id'],
                'sha': build['sha'],
                'result': 'passed',
                'build_url': 'https://example.com/dummy-build',
                'patch_name': build['patch_name'],
                'repo_name': build['repo_name'],
                'test_name': 'dummy-test',
                'patch_id': build['patch_id']
            }

            self.db.set_build_synced(pw_instance, build['patch_id'], self.sync_column)


def create_provider(name: str, token: str, database, **kwargs) -> Optional[CIProvider]:
    """Factory function to create CI providers."""
    providers = {
        'github': GitHubActionsProvider,
        'travis': TravisProvider,
        'cirrus': CirrusProvider,
        'dummy': DummyProvider,
    }

    provider_class = providers.get(name.lower())
    if provider_class:
        # Pass additional kwargs to the provider (e.g., api_base for GitHub)
        if name.lower() == 'github':
            # GitHub provider accepts api_base parameter
            api_base = kwargs.get('api_base', 'https://api.github.com')
            return provider_class(token, database, api_base)
        else:
            return provider_class(token, database)

    return None
