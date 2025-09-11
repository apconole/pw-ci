"""Main CI monitoring orchestration."""

import json
import re
import subprocess
from typing import Dict, List, Optional

import requests

from .ci_providers import CIProvider
from .email import EmailReporter
from .patchwork import PatchworkClient


class CIMonitor:
    """Main CI monitoring coordinator."""

    def __init__(self, database, patchwork_client: PatchworkClient, 
                 email_reporter: EmailReporter):
        self.db = database
        self.patchwork_client = patchwork_client
        self.email_reporter = email_reporter

        # Status strings
        self.status_success = "SUCCESS"
        self.status_failure = "FAILURE"
        self.status_warning = "WARNING"

    def set_status_strings(self, success: str, failure: str, warning: str) -> None:
        """Set custom status strings for reports."""
        self.status_success = success
        self.status_failure = failure
        self.status_warning = warning

    def get_series_data(self, pw_instance: str, series_id: int) -> Optional[Dict]:
        """Get series data from Patchwork."""
        try:
            return self.patchwork_client.get_series(series_id)
        except requests.RequestException as e:
            print(f"Error fetching series {series_id}: {e}")
            return None

    def get_patch_data(self, series_data: Dict, patch_id: Optional[int], 
                      shasum: str) -> Optional[Dict]:
        """Get patch data from series, trying to match by patch_id or SHA."""
        if not series_data or 'patches' not in series_data:
            return None

        patches = series_data['patches']

        # First try to find by patch_id if provided
        if patch_id:
            for patch in patches:
                if patch['id'] == patch_id:
                    try:
                        return self.patchwork_client.get_patch(patch['url'])
                    except requests.RequestException:
                        continue

        # If not found by patch_id, try to find by SHA or use last patch
        if patches:
            try:
                # For now, just use the last patch
                last_patch = patches[-1]
                return self.patchwork_client.get_patch(last_patch['url'])
            except requests.RequestException:
                pass

        return None

    def apply_patch_url_filter(self, patch_url: str, url_filter: Optional[str]) -> str:
        """Apply URL filter regex to patch URL."""
        if not url_filter or url_filter == 'q':
            return patch_url

        try:
            # Apply sed-like regex transformation
            if url_filter.startswith('s/') and url_filter.count('/') >= 2:
                parts = url_filter[2:].split('/')
                if len(parts) >= 2:
                    pattern, replacement = parts[0], parts[1]
                    return re.sub(pattern, replacement, patch_url)
        except re.error:
            print(f"Invalid URL filter regex: {url_filter}")

        return patch_url

    def get_log_output(self, provider_name: str, repo_name: str, series_id: int,
                      shasum: str, token: str, test_name: str) -> str:
        """Get log output from CI provider if available."""
        log_script = f"./{provider_name}_get_logs.sh"

        try:
            result = subprocess.run([
                log_script, repo_name, str(series_id), shasum, token, test_name
            ], capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                return result.stdout
        except (subprocess.SubprocessError, subprocess.TimeoutExpired):
            pass

        return ""

    def run_post_result_submit(self, provider_name: str, build_result: Dict,
                              patch_id: int, pw_instance: str, extra_args: str,
                              dry_run: bool = False) -> Optional[Dict]:
        """Run post-result submission script."""
        script_name = f"./{provider_name}_post_result_submit"

        cmd = [
            script_name,
            f"--result={build_result['result']}",
            f"--series-id={build_result['series_id']}",
            f"--patch-id={patch_id}",
            f"--pw-instance={pw_instance}",
            f"--ci-type={provider_name}"
        ]

        if dry_run:
            cmd.append("--dry-run")

        if extra_args:
            cmd.extend(extra_args.split())

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                return json.loads(result.stdout)
        except (subprocess.SubprocessError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

        return None

    def process_build_result(self, provider: CIProvider, build_result: Dict,
                           pw_instance: str, patch_url_filter: Optional[str],
                           post_result: bool, post_result_extra: str) -> None:
        """Process a single build result and send emails."""

        series_id = build_result['series_id']
        patch_id = build_result.get('patch_id')
        shasum = build_result['sha']

        # Get series and patch data
        series_data = self.get_series_data(pw_instance, series_id)
        if not series_data:
            print(f"Series {series_id} not found for instance {pw_instance}")
            return

        patch_data = self.get_patch_data(series_data, patch_id, shasum)
        if not patch_data:
            print(f"Could not get patch data for series {series_id}")
            return

        # Apply patch URL filter
        patch_url = self.apply_patch_url_filter(patch_data['url'], patch_url_filter)
        if patch_url_filter and patch_url_filter != 'q':
            print(f"Patch URL '{patch_data['url']}' transformed by '{patch_url_filter}' to '{patch_url}'")

        # Update patch data with filtered URL
        patch_data['url'] = patch_url

        # Determine email settings
        cc_author = build_result['result'] != 'passed'

        print(f"Clear result for series_{series_id} with {build_result['result']} "
              f"at url {build_result['build_url']} on patch {patch_data['id']}")

        # Generate and send main result email
        email_content = self.email_reporter.generate_report_email(
            build_result, patch_data, cc_author
        )

        # Add logs if available
        log_output = self.get_log_output(
            provider.name, build_result['repo_name'], series_id,
            shasum, provider.token, build_result.get('test_name', '')
        )
        if log_output:
            email_content += "\n" + log_output

        # Send email
        cc_recipients = [patch_data['submitter']['email']] if cc_author else None
        self.email_reporter.send_email_via_git(email_content, cc_recipients)

        # Handle post-result submission
        if post_result:
            post_result_data = self.run_post_result_submit(
                provider.name, build_result, patch_data['id'],
                pw_instance, post_result_extra, self.email_reporter.dry_run
            )

            if post_result_data and post_result_data.get('url'):
                print(f"Post report URL: {post_result_data['url']}")

                # Generate post-result email
                post_email = self.email_reporter.generate_post_result_email(
                    build_result, patch_data, post_result_data
                )

                # Send post-result email
                self.email_reporter.send_email_via_git(post_email, cc_recipients)

    def monitor_ci_systems(self, providers: List[CIProvider], pw_instance: str,
                          pw_project: Optional[str] = None, 
                          patch_url_filter: Optional[str] = None,
                          post_result: bool = False,
                          post_result_extra: str = "") -> None:
        """Monitor all configured CI systems and process results."""

        for provider in providers:
            print(f"Scanning {provider.name}")

            try:
                for build_result in provider.get_build_results(pw_instance, pw_project):
                    self.process_build_result(
                        provider, build_result, pw_instance, patch_url_filter,
                        post_result, post_result_extra
                    )
            except Exception as e:
                print(f"Error monitoring {provider.name}: {e}")
                continue
