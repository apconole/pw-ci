"""Command-line interface for pw-ci."""

import os
import sys
from pathlib import Path
from typing import List, Optional

import click

from .ci_providers import create_provider
from .database import SeriesDatabase
from .email import EmailReporter
from .monitor import CIMonitor
from .patchwork import PatchworkClient, PatchworkMonitor


def load_config(config_file: Optional[str] = None) -> dict:
    """Load configuration from file."""
    config = {}

    # Default config files to check
    config_files = [
        Path.home() / ".pwmon-rc",
        Path.home() / ".cimon-rc",
        Path.home() / ".github_actions_mon_rc",
    ]

    if config_file:
        config_files.insert(0, Path(config_file))

    for config_path in config_files:
        if config_path.exists():
            # Simple bash-style config parsing
            with open(config_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Remove quotes if present
                        value = value.strip('"\'')
                        config[key.strip()] = value

    return config


@click.group()
@click.version_option()
@click.pass_context
def cli(ctx):
    """Patchwork CI monitoring and integration tool."""
    ctx.ensure_object(dict)


@cli.command()
@click.option('--pw-instance', help='Patchwork instance URL')
@click.option('--pw-project', help='Patchwork project name')
@click.option('--pw-credentials', help='Patchwork credentials (user:pass)')
@click.option('--config', help='Configuration file path')
@click.option('--add-filter-recheck', multiple=True, help='Add recheck filter')
@click.pass_context
def monitor(ctx, pw_instance, pw_project, pw_credentials, config, add_filter_recheck):
    """Monitor patchwork for new series and updates."""

    # Load configuration
    config_data = load_config(config)

    # Override with command line arguments
    if not pw_instance:
        pw_instance = config_data.get('pw_instance')
    if not pw_project:
        pw_project = config_data.get('pw_project')
    if not pw_credentials:
        pw_credentials = config_data.get('pw_credential')

    if not pw_instance or not pw_project:
        click.echo("Error: pw_instance and pw_project must be specified", err=True)
        sys.exit(1)

    # Create clients
    database = SeriesDatabase()
    patchwork_client = PatchworkClient(pw_instance, pw_credentials)
    monitor_client = PatchworkMonitor(patchwork_client, database, pw_project)

    # Run monitoring
    recheck_filters = list(add_filter_recheck) if add_filter_recheck else None
    monitor_client.run_full_check(recheck_filters)


@cli.command()
@click.option('--pw-instance', required=True, help='Patchwork instance URL')
@click.option('--pw-project', help='Patchwork project name')
@click.option('--from-addr', help='From email address')
@click.option('--to-addr', help='To email address')
@click.option('--dry-run', is_flag=True, help='Dry run mode')
@click.option('--github-token', help='GitHub token')
@click.option('--travis-token', help='Travis CI token')
@click.option('--cirrus-token', help='Cirrus CI token')
@click.option('--dummy-token', help='Dummy CI token (for testing)')
@click.option('--disable-github', is_flag=True, help='Disable GitHub monitoring')
@click.option('--disable-travis', is_flag=True, help='Disable Travis monitoring')
@click.option('--disable-cirrus', is_flag=True, help='Disable Cirrus monitoring')
@click.option('--enable-dummy', is_flag=True, help='Enable dummy CI monitoring')
@click.option('--patch-url-filter', help='Regex filter for patch URLs')
@click.option('--report-success', default='SUCCESS', help='Success report string')
@click.option('--report-failure', default='FAILURE', help='Failure report string')
@click.option('--report-warning', default='WARNING', help='Warning report string')
@click.option('--post-result', is_flag=True, help='Enable post-result submission')
@click.option('--post-result-extra', help='Extra arguments for post-result')
@click.option('--config', help='Configuration file path')
@click.pass_context
def ci_monitor(ctx, pw_instance, pw_project, from_addr, to_addr, dry_run,
               github_token, travis_token, cirrus_token, dummy_token,
               disable_github, disable_travis, disable_cirrus, enable_dummy,
               patch_url_filter, report_success, report_failure, report_warning,
               post_result, post_result_extra, config):
    """Monitor CI systems and send result emails."""

    # Load configuration
    config_data = load_config(config)

    # Apply config defaults
    if not from_addr:
        from_addr = config_data.get('from_addr')
    if not to_addr:
        to_addr = config_data.get('to_addr')
    if not github_token:
        github_token = config_data.get('github_token')
    if not travis_token:
        travis_token = config_data.get('travis_token')
    if not cirrus_token:
        cirrus_token = config_data.get('cirrus_token')
    if not dummy_token:
        dummy_token = config_data.get('dummy_token', '1111')

    if not from_addr or not to_addr:
        click.echo("Error: from_addr and to_addr must be specified", err=True)
        sys.exit(1)

    # Create database and email reporter
    database = SeriesDatabase()
    email_reporter = EmailReporter(from_addr, to_addr, dry_run)

    # Create patchwork client for patch data
    patchwork_client = PatchworkClient(pw_instance)

    # Create CI monitor
    monitor = CIMonitor(database, patchwork_client, email_reporter)
    monitor.set_status_strings(report_success, report_failure, report_warning)

    # Configure providers
    providers = []

    if not disable_github and github_token:
        # Support custom GitHub API base URL for testing
        github_api_base = os.environ.get('GITHUB_API_BASE', 'https://api.github.com')
        provider = create_provider('github', github_token, database, api_base=github_api_base)
        if provider:
            providers.append(provider)
            click.echo("Scanning github")
            if github_api_base != 'https://api.github.com':
                click.echo(f"  Using API base: {github_api_base}")
        else:
            click.echo("Failed to create GitHub provider")

    if not disable_travis and travis_token:
        provider = create_provider('travis', travis_token, database)
        if provider:
            providers.append(provider)
            click.echo("Scanning travis")
        else:
            click.echo("Failed to create Travis provider")

    if not disable_cirrus and cirrus_token:
        provider = create_provider('cirrus', cirrus_token, database)
        if provider:
            providers.append(provider)
            click.echo("Scanning cirrus")
        else:
            click.echo("Failed to create Cirrus provider")

    if enable_dummy:
        provider = create_provider('dummy', dummy_token, database)
        if provider:
            providers.append(provider)
            click.echo("Scanning dummy")
        else:
            click.echo("Failed to create dummy provider")

    if not providers:
        click.echo("No CI providers configured", err=True)
        sys.exit(1)

    # Run CI monitoring
    monitor.monitor_ci_systems(
        providers, pw_instance, pw_project, 
        patch_url_filter, post_result, post_result_extra
    )


@cli.command()
@click.option('--pw-instance', required=True, help='Patchwork instance URL')
@click.option('--series-id', required=True, type=int, help='Series ID')
@click.pass_context
def series_info(ctx, pw_instance, series_id):
    """Get information about a series."""

    database = SeriesDatabase()
    patchwork_client = PatchworkClient(pw_instance)

    try:
        series_data = patchwork_client.get_series(series_id)

        click.echo(f"Series ID: {series_data['id']}")
        click.echo(f"URL: {series_data['url']}")
        click.echo(f"Submitter: {series_data['submitter']['name']} <{series_data['submitter']['email']}>")
        click.echo(f"Subject: {series_data.get('name', 'N/A')}")
        click.echo(f"All received: {series_data.get('received_all', False)}")
        click.echo(f"Patches: {len(series_data.get('patches', []))}")

        # Check database status
        if database.series_exists(pw_instance, series_id):
            click.echo("Status: Tracked in database")
        else:
            click.echo("Status: Not in database")

    except Exception as e:
        click.echo(f"Error fetching series: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--pw-instance', required=True, help='Patchwork instance URL')
@click.option('--pw-project', help='Patchwork project name')
@click.pass_context
def list_series(ctx, pw_instance, pw_project):
    """List series in the database."""

    database = SeriesDatabase()

    if pw_project:
        unsubmitted = database.get_unsubmitted_series(pw_instance, pw_project)
        uncompleted = database.get_uncompleted_series(pw_instance, pw_project)
    else:
        # Would need to implement get_all_series methods
        click.echo("Project filter required for now")
        return

    if unsubmitted:
        click.echo("Unsubmitted series:")
        for series_id, url, submitter, email in unsubmitted:
            click.echo(f"  {series_id}: {submitter} - {url}")

    if uncompleted:
        click.echo("\nUncompleted series:")
        for series_id, url, submitter, email in uncompleted:
            click.echo(f"  {series_id}: {submitter} - {url}")


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()
