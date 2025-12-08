import asyncio
import json
import logging
import subprocess
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class LoreMonitor:
    def __init__(self, subsystems: List[Dict], query_window_days: int, seen_messages_path: str = "seen_messages.json"):
        self.subsystems = subsystems
        self.query_window_days = query_window_days
        self.seen_messages_path = seen_messages_path
        self.seen_messages: Dict[str, float] = self._load_seen_messages()
        self.lore_external = "https://lore.kernel.org/all/"

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def _load_seen_messages(self) -> Dict[str, float]:
        """Load seen messages from disk"""
        try:
            from pathlib import Path
            import time
            path = Path(self.seen_messages_path)
            if path.exists():
                with open(path, 'r') as f:
                    data = json.load(f)

                    # Handle both old format (list) and new format (dict with timestamps)
                    if isinstance(data.get('seen'), list):
                        # Old format: convert to dict with current timestamp
                        current_time = time.time()
                        seen = {msg_id: current_time for msg_id in data['seen']}
                        logger.info(f"Converted {len(seen)} message IDs from old format")
                    else:
                        # New format: dict with timestamps
                        seen = data.get('seen', {})
                        logger.info(f"Loaded {len(seen)} seen message IDs")

                    return seen
        except Exception as e:
            logger.error(f"Failed to load seen messages: {e}")
        return {}

    def _save_seen_messages(self):
        """Save seen messages to disk, cleaning up old entries"""
        try:
            from pathlib import Path
            import time

            # Clean up messages older than 3 days (well beyond 24h query window)
            current_time = time.time()
            three_days_ago = current_time - (3 * 24 * 60 * 60)

            old_count = len(self.seen_messages)
            self.seen_messages = {
                msg_id: timestamp
                for msg_id, timestamp in self.seen_messages.items()
                if timestamp > three_days_ago
            }

            if len(self.seen_messages) < old_count:
                logger.info(f"Cleaned up {old_count - len(self.seen_messages)} messages older than 3 days")

            path = Path(self.seen_messages_path)
            with open(path, 'w') as f:
                json.dump({'seen': self.seen_messages}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save seen messages: {e}")

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
        # First, check if mailing_list is explicitly configured
        if 'mailing_list' in subsystem:
            return subsystem['mailing_list']

        # Fallback: For search URLs like https://lore.kernel.org/all/?q=tc:x86@kernel.org
        lore_url = subsystem['lore_url']
        if '?q=tc:' in lore_url:
            import re
            match = re.search(r'tc:([^\s&]+)', lore_url)
            if match:
                return match.group(1)

        # If we get here, we couldn't determine the mailing list
        name = subsystem['name']
        logger.warning(f"Could not determine mailing list for {name} from {lore_url}. "
                      f"Consider adding 'mailing_list' field to config.")
        return None

    async def fetch_lore_messages(self, subsystem: Dict, days_back: int = None) -> List[Dict]:
        """Fetch recent messages from a lore mailing list using lei"""
        try:
            mailing_list = self._extract_mailing_list(subsystem)
            if not mailing_list:
                return []

            # Use configured query window if not explicitly specified
            if days_back is None:
                days_back = self.query_window_days

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
                        'from': sender,
                        'refs': msg.get('refs', [])  # Message references for threading
                    })
                except Exception as e:
                    logger.warning(f"Failed to parse message: {e}")
                    continue

            # Sort messages by date (oldest first) to ensure proper processing order
            # This is especially important on bot restart to handle PRs before their merges
            messages.sort(key=lambda m: m['date'])

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
                        import time
                        self.seen_messages[msg['id']] = time.time()
                        self._save_seen_messages()

                        # Try to fetch the git commit URL from the message
                        commit_url = await self.get_pr_tracker_commit_url(msg['id'])
                        if commit_url:
                            msg['commit_url'] = commit_url

                        new_messages.append(msg)
                        logger.info(f"New PR merged: {msg['subject']}")

        return new_messages

    async def check_pr_bot_messages_for_refs(self, ref_message_ids: List[str]) -> List[Dict]:
        """Check for pr-tracker-bot messages that reference specific message IDs"""
        if not ref_message_ids:
            return []

        merge_messages = []

        for subsystem in self.subsystems:
            # Query wider time range since we're looking for a specific merge
            messages = await self.fetch_lore_messages(subsystem, days_back=30)

            for msg in messages:
                sender = msg.get('from', '').lower()

                # Check if this is from pr-tracker-bot (merge confirmation)
                if 'pr-tracker-bot@kernel.org' in sender:
                    # Check if this message references any of the given message IDs
                    msg_refs = msg.get('refs', [])
                    for ref_id in ref_message_ids:
                        if ref_id in msg_refs:
                            # Try to fetch the git commit URL from the message
                            commit_url = await self.get_pr_tracker_commit_url(msg['id'])
                            if commit_url:
                                msg['commit_url'] = commit_url

                            merge_messages.append(msg)
                            logger.info(f"Found merge for {ref_id}: {msg['subject']}")
                            break

        return merge_messages

    async def fetch_message_by_id(self, message_id: str) -> Optional[Dict]:
        """Fetch a specific message from lore by its message ID"""
        try:
            # Query lore for this specific message
            query = f"m:{message_id}"
            logger.debug(f"Fetching message from lore: {query}")

            messages = await self._run_lei_query(query)

            if not messages or len(messages) == 0:
                logger.warning(f"Message not found in lore: {message_id}")
                return None

            msg = messages[0]

            # Parse message into our format
            msg_date = datetime.now()
            date_str = msg.get('dt', '')
            try:
                msg_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except:
                pass

            from_field = msg.get('f', [[None, '']])
            sender = from_field[0][1] if from_field and from_field[0] else ''

            lore_url = f"https://lore.kernel.org/all/{message_id}/"

            # Determine subsystem from subject or default to unknown
            subject = msg.get('s', '')
            subsystem = 'unknown'
            # Try to match against known subsystems
            for sub in self.subsystems:
                if sub['name'].lower() in subject.lower():
                    subsystem = sub['name']
                    break

            return {
                'id': message_id,
                'subject': subject,
                'date': msg_date.isoformat(),
                'url': lore_url,
                'subsystem': subsystem,
                'from': sender
            }

        except Exception as e:
            logger.error(f"Error fetching message {message_id} from lore: {e}")
            return None

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
                        import time
                        self.seen_messages[msg['id']] = time.time()
                        self._save_seen_messages()
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
