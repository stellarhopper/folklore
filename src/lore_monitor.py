import asyncio
import json
import logging
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set

logger = logging.getLogger(__name__)

class LoreMonitor:
    def __init__(self, subsystems: List[Dict]):
        self.subsystems = subsystems
        self.seen_messages: Set[str] = set()
        self.lore_external = "https://lore.kernel.org/all/"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def _run_lei_query(self, query: str, timeout: int = 30) -> List[Dict]:
        """Run a lei query and return parsed JSON results"""
        try:
            # Build lei command
            # -I specifies the external source (lore.kernel.org)
            # -f json outputs JSON format
            # --no-save prevents saving the search
            cmd = [
                'lei', 'q',
                '-I', self.lore_external,
                '-f', 'json',
                '--no-save',
                query
            ]

            logger.debug(f"Running lei query: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=float(timeout)
            )

            if process.returncode != 0:
                stderr_text = stderr.decode().strip()
                if stderr_text:
                    logger.error(f"lei query failed: {stderr_text}")
                return []

            # Parse JSON output (array of messages)
            output = stdout.decode().strip()
            if not output or output == '[]':
                return []

            try:
                messages = json.loads(output)
                return messages if isinstance(messages, list) else []
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse lei JSON output: {e}")
                return []

        except asyncio.TimeoutError:
            logger.error(f"lei query timed out after {timeout}s: {query}")
            return []
        except Exception as e:
            logger.error(f"Error running lei query: {e}")
            return []

    def _extract_mailing_list(self, subsystem: Dict) -> Optional[str]:
        """Extract mailing list address from subsystem config"""
        lore_url = subsystem['lore_url']

        # For search URLs like https://lore.kernel.org/all/?q=tc:x86@kernel.org
        if '?q=tc:' in lore_url:
            import re
            match = re.search(r'tc:([^\s&]+)', lore_url)
            if match:
                return match.group(1)

        # Map subsystem names to known mailing list addresses
        list_mappings = {
            'linux-cxl': 'linux-cxl@vger.kernel.org',
            'nvdimm': 'nvdimm@lists.linux.dev',
            'x86': 'x86@kernel.org',
        }

        name = subsystem['name']
        if name in list_mappings:
            return list_mappings[name]

        logger.warning(f"Could not determine mailing list for {name} from {lore_url}")
        return None

    async def fetch_lore_messages(self, subsystem: Dict, days_back: int = 1) -> List[Dict]:
        """Fetch recent messages from a lore mailing list using lei"""
        try:
            mailing_list = self._extract_mailing_list(subsystem)
            if not mailing_list:
                return []

            # Build lei query
            # tc: is for "to or cc", dt: is for date range
            query = f"tc:{mailing_list} AND dt:{days_back}.days.ago.."

            logger.info(f"Querying {subsystem['name']}: {query}")
            raw_messages = await self._run_lei_query(query)

            logger.info(f"Found {len(raw_messages)} messages for {subsystem['name']}")

            # Convert lei format to our internal format
            messages = []
            for msg in raw_messages:
                try:
                    # Skip null entries that lei sometimes includes
                    if msg is None or not isinstance(msg, dict):
                        continue

                    # Extract message-id (removing angle brackets if present)
                    msg_id = msg.get('m', '').strip('<>')
                    if not msg_id:
                        continue

                    # Parse date (dt is Unix timestamp as string)
                    date_str = msg.get('dt', '')
                    try:
                        # lei returns ISO 8601 format like "2025-09-30T23:33:28Z"
                        msg_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    except:
                        msg_date = datetime.now()

                    # Extract sender (f is array of [name, email])
                    from_field = msg.get('f', [[None, '']])
                    sender = from_field[0][1] if from_field and from_field[0] else ''

                    # Build lore URL from message-id
                    lore_url = f"https://lore.kernel.org/all/{msg_id}/"

                    messages.append({
                        'id': msg_id,
                        'subject': msg.get('s', ''),
                        'date': msg_date.isoformat(),
                        'url': lore_url,
                        'subsystem': subsystem['name'],
                        'from': sender
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse message: {e}")
                    continue

            return messages

        except Exception as e:
            logger.error(f"Error fetching lore messages for {subsystem['name']}: {e}")
            return []

    async def check_pr_bot_messages(self) -> List[Dict]:
        """Check for pr-tracker-bot messages indicating merged PRs"""
        new_messages = []

        for subsystem in self.subsystems:
            messages = await self.fetch_lore_messages(subsystem)

            for msg in messages:
                sender = msg.get('from', '').lower()

                # Check if this is from pr-tracker-bot (merge confirmation)
                if 'pr-tracker-bot@kernel.org' in sender:
                    if msg['id'] not in self.seen_messages:
                        self.seen_messages.add(msg['id'])

                        # Try to fetch the git commit URL from the message
                        commit_url = await self.get_pr_tracker_commit_url(msg['id'])
                        if commit_url:
                            msg['commit_url'] = commit_url

                        new_messages.append(msg)
                        logger.info(f"New PR merged: {msg['subject']}")

        return new_messages

    async def check_git_pull_requests(self) -> List[Dict]:
        """Check for [GIT PULL] request emails (original requests, not pr-bot responses)"""
        new_messages = []

        for subsystem in self.subsystems:
            messages = await self.fetch_lore_messages(subsystem)

            for msg in messages:
                # Look for GIT PULL requests, but exclude pr-bot responses
                subject = msg['subject']
                sender = msg.get('from', '').lower()

                # Skip pr-tracker-bot responses (these are merge confirmations, handled separately)
                if 'pr-tracker-bot@kernel.org' in sender:
                    continue

                # Skip replies (Re:) - these are usually discussions, not original pull requests
                if subject.lower().startswith('re: '):
                    continue

                if ('[GIT PULL]' in subject or
                    '[git pull]' in subject.lower()):

                    if msg['id'] not in self.seen_messages:
                        self.seen_messages.add(msg['id'])
                        new_messages.append(msg)
                        logger.info(f"New GIT PULL: {msg['subject']}")

        return new_messages

    async def get_pr_tracker_commit_url(self, message_id: str) -> Optional[str]:
        """Extract git.kernel.org commit URL from pr-tracker-bot message"""
        try:
            import re

            # Use b4 mbox with --single-message to fetch just this message
            cmd = ['b4', 'mbox', '--single-message', '-o', '-', message_id]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=15.0
            )

            if process.returncode != 0:
                logger.warning(f"b4 fetch failed for {message_id}: {stderr.decode()}")
                return None

            # Parse email content for git.kernel.org commit URLs
            content = stdout.decode()
            logger.debug(f"b4 output length for {message_id}: {len(content)} bytes")

            # Look for the merge commit URL in torvalds/linux.git
            # Format: https://git.kernel.org/torvalds/c/COMMIT_HASH
            # This appears after "has been merged into torvalds/linux.git:" in the message body
            match = re.search(r'https://git\.kernel\.org/torvalds/c/[0-9a-f]+', content)
            if match:
                url = match.group(0)
                logger.info(f"Found merge commit URL for {message_id}: {url}")
                return url

            # Fallback: look for any git.kernel.org URL if the specific pattern isn't found
            match = re.search(r'https://git\.kernel\.org/[^\s]+', content)
            if match:
                url = match.group(0)
                logger.warning(f"Found non-standard git URL for {message_id}: {url}")
                return url

            logger.warning(f"No git.kernel.org URL found in b4 output for {message_id}")
            return None

        except asyncio.TimeoutError:
            logger.warning(f"b4 fetch timed out for {message_id}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching commit URL with b4: {e}")
            return None
