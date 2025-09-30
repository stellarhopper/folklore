import aiohttp
import asyncio
import re
import json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Set
import logging

logger = logging.getLogger(__name__)

class LoreMonitor:
    def __init__(self, subsystems: List[Dict]):
        self.subsystems = subsystems
        self.session = None
        self.seen_messages: Set[str] = set()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_lore_messages(self, subsystem: Dict, hours_back: int = 1) -> List[Dict]:
        """Fetch recent messages from a lore mailing list"""
        try:
            url = subsystem['lore_url']

            # For filtered URLs (like x86), we need to handle differently
            if '?q=' in url:
                # This is a search URL, fetch recent messages with the filter
                async with self.session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch {subsystem['name']}: {response.status}")
                        return []

                    html = await response.text()
            else:
                # This is a direct mailing list URL
                async with self.session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch {subsystem['name']}: {response.status}")
                        return []

                    html = await response.text()

            soup = BeautifulSoup(html, 'html.parser')
            messages = []

            # Parse message list from lore HTML
            # Lore uses a specific structure for message listings
            for row in soup.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) >= 3:
                    # Extract date, subject, and message ID
                    date_cell = cells[0]
                    subject_cell = cells[1]

                    date_text = date_cell.get_text(strip=True)
                    subject_text = subject_cell.get_text(strip=True)

                    # Look for message link
                    link = subject_cell.find('a')
                    if link and link.get('href'):
                        message_id = link.get('href').split('/')[-1]

                        # Check if this is recent enough
                        try:
                            # Parse date (lore uses various formats)
                            msg_date = self._parse_lore_date(date_text)
                            if msg_date and msg_date > datetime.now() - timedelta(hours=hours_back):
                                messages.append({
                                    'id': message_id,
                                    'subject': subject_text,
                                    'date': msg_date.isoformat(),
                                    'url': f"{url.rstrip('/')}/{message_id}",
                                    'subsystem': subsystem['name']
                                })
                        except Exception as e:
                            logger.warning(f"Failed to parse date for message: {e}")

            return messages

        except Exception as e:
            logger.error(f"Error fetching lore messages for {subsystem['name']}: {e}")
            return []

    def _parse_lore_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats used by lore"""
        try:
            # Common lore date formats
            formats = [
                '%Y-%m-%d %H:%M',
                '%d %b %Y %H:%M',
                '%b %d %H:%M',
                '%Y-%m-%d',
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue

            # If we can't parse it, assume it's recent
            return datetime.now()
        except:
            return None

    async def check_pr_bot_messages(self) -> List[Dict]:
        """Check for pr-bot messages indicating merged PRs"""
        new_messages = []

        for subsystem in self.subsystems:
            messages = await self.fetch_lore_messages(subsystem)

            for msg in messages:
                # Look for pr-bot merge notifications
                if ('pr-bot' in msg['subject'].lower() or
                    'merged' in msg['subject'].lower() or
                    'applied' in msg['subject'].lower()):

                    if msg['id'] not in self.seen_messages:
                        self.seen_messages.add(msg['id'])
                        new_messages.append(msg)

        return new_messages

    async def check_git_pull_requests(self) -> List[Dict]:
        """Check for [GIT PULL] request emails"""
        new_messages = []

        for subsystem in self.subsystems:
            messages = await self.fetch_lore_messages(subsystem)

            for msg in messages:
                # Look for GIT PULL requests
                if ('[GIT PULL]' in msg['subject'] or
                    'git pull' in msg['subject'].lower()):

                    if msg['id'] not in self.seen_messages:
                        self.seen_messages.add(msg['id'])
                        new_messages.append(msg)

        return new_messages

    async def get_message_details(self, message_url: str) -> Optional[Dict]:
        """Fetch full details of a specific message"""
        try:
            async with self.session.get(message_url) as response:
                if response.status != 200:
                    return None

                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')

                # Extract message content
                content_div = soup.find('pre') or soup.find('div', class_='msg')
                content = content_div.get_text() if content_div else ""

                # Extract sender
                sender_elem = soup.find('b', string='From:')
                sender = ""
                if sender_elem and sender_elem.next_sibling:
                    sender = sender_elem.next_sibling.strip()

                return {
                    'content': content[:500],  # Truncate for Discord
                    'sender': sender
                }
        except Exception as e:
            logger.error(f"Error fetching message details: {e}")
            return None