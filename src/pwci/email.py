"""Email generation and sending functionality."""

import smtplib
import subprocess
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Optional

from jinja2 import Template


class EmailReporter:
    """Generate and send CI result emails."""

    def __init__(self, from_addr: str, to_addr: str, dry_run: bool = False):
        self.from_addr = from_addr
        self.to_addr = to_addr
        self.dry_run = dry_run

        # Report status mappings
        self.status_map = {
            'passed': 'SUCCESS',
            'failed': 'FAILURE',
            'warning': 'WARNING'
        }

    def generate_report_email(self, build_result: Dict, patch_data: Dict, 
                            cc_author: bool = False) -> str:
        """Generate a CI report email."""

        result_status = self.status_map.get(build_result['result'], 'WARNING')
        patch_id = build_result.get('patch_id', '')
        series_name = build_result.get('patch_name', '')
        ci_name = build_result.get('test_name', 'ci-robot')

        # Email headers
        email_lines = [
            f"To: {self.to_addr}",
            f"From: {self.from_addr}",
        ]

        # Add CC if build failed and we have patch author email
        if cc_author and build_result['result'] != 'passed' and patch_data.get('email'):
            email_lines.append(f"Cc: {patch_data['email']}")

        email_lines.extend([
            f"Subject: |{result_status}| pw{patch_id} {series_name}",
            f"Date: {datetime.now().strftime('%a, %e %b %Y %T %z')}",
        ])

        # Add threading headers if we have message ID
        if patch_data.get('message_id'):
            email_lines.extend([
                f"In-Reply-To: {patch_data['message_id']}",
                f"References: {patch_data['message_id']}",
            ])

        # Empty line before body
        email_lines.append("")

        # Email body
        test_label = ci_name
        if build_result.get('test_name'):
            test_label = f"{build_result['test_name']}-robot"

        email_lines.extend([
            f"Test-Label: {test_label}",
            f"Test-Status: {result_status}",
            patch_data.get('url', ''),
            "",
            f"_{ci_name} build: {build_result['result']}_",
            f"Build URL: {build_result['build_url']}",
        ])

        return "\n".join(email_lines)

    def generate_post_result_email(self, build_result: Dict, patch_data: Dict,
                                  post_result: Dict) -> str:
        """Generate a post-result submission email."""

        patch_id = build_result.get('patch_id', '')
        series_name = build_result.get('patch_name', '')
        ci_name = build_result.get('test_name', 'ci-robot')

        email_lines = [
            f"To: {self.to_addr}",
            f"From: {self.from_addr}",
            f"Subject: |SUCCESS| pw{patch_id} {series_name}",
            f"Date: {datetime.now().strftime('%a, %e %b %Y %T %z')}",
        ]

        if patch_data.get('message_id'):
            email_lines.extend([
                f"In-Reply-To: {patch_data['message_id']}",
                f"References: {patch_data['message_id']}",
            ])

        email_lines.extend([
            "",
            f"Test-Label: {ci_name}-robot-post",
            f"Test-Status: SUCCESS",
            patch_data.get('url', ''),
            "",
            f"_{ci_name} post: success_",
        ])

        # Add URL information
        if post_result.get('html_url'):
            email_lines.append(f"HTML Link: {post_result['html_url']}")
        elif post_result.get('url'):
            email_lines.append(f"Submitted URL: {post_result['url']}")

        return "\n".join(email_lines)

    def send_email_via_git(self, email_content: str, cc_recipients: Optional[List[str]] = None) -> bool:
        """Send email using git send-email."""
        # Write email to temporary file
        email_file = Path("report.eml")
        email_file.write_text(email_content)

        # Build git send-email command
        cmd = ["git", "send-email"]

        if self.dry_run:
            cmd.append("--dry-run")

        cmd.extend([
            "--suppress-from",
            f"--to={self.to_addr}"
        ])

        # Add CC recipients
        if cc_recipients:
            for cc in cc_recipients:
                cmd.append(f"--cc={cc}")

        cmd.append(str(email_file))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"git send-email failed: {result.stderr}")
                return False

            print(f"Email sent successfully")
            return True

        except subprocess.SubprocessError as e:
            print(f"Error running git send-email: {e}")
            return False
        finally:
            # Clean up temporary file
            if email_file.exists():
                email_file.unlink()

    def send_smtp_email(self, email_content: str, smtp_server: str = "localhost",
                       smtp_port: int = 25) -> bool:
        """Send email via SMTP server."""
        try:
            # Parse the email content
            lines = email_content.split('\n')
            headers = {}
            body_start = 0

            for i, line in enumerate(lines):
                if line.strip() == "":
                    body_start = i + 1
                    break
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()

            body = '\n'.join(lines[body_start:])

            # Create email message
            msg = MIMEText(body)
            msg['Subject'] = headers.get('Subject', 'CI Report')
            msg['From'] = headers.get('From', self.from_addr)
            msg['To'] = headers.get('To', self.to_addr)

            if 'Cc' in headers:
                msg['Cc'] = headers['Cc']

            # Send email
            if not self.dry_run:
                with smtplib.SMTP(smtp_server, smtp_port) as server:
                    recipients = [self.to_addr]
                    if 'Cc' in headers:
                        recipients.extend(headers['Cc'].split(','))

                    server.send_message(msg, to_addrs=recipients)

            print(f"Email sent via SMTP: {headers.get('Subject', 'CI Report')}")
            return True

        except Exception as e:
            print(f"Error sending SMTP email: {e}")
            return False
