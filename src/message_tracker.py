import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

class MessageTracker:
    """Tracks mapping between lore message IDs and Discord message IDs, plus pending PR status"""

    def __init__(self, storage_path: str = "message_map.json", pending_path: str = "pending_prs.json"):
        self.storage_path = Path(storage_path)
        self.pending_path = Path(pending_path)
        # Map lore message ID to dict of {channel_id: discord_message_id}
        self.message_map: Dict[str, Dict[int, int]] = {}
        # Map lore message ID to pending PR metadata
        self.pending_prs: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        """Load message mappings and pending PRs from disk"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r') as f:
                    self.message_map = json.load(f)
                logger.info(f"Loaded {len(self.message_map)} message mappings")
        except Exception as e:
            logger.error(f"Failed to load message mappings: {e}")
            self.message_map = {}

        try:
            if self.pending_path.exists():
                with open(self.pending_path, 'r') as f:
                    self.pending_prs = json.load(f)
                logger.info(f"Loaded {len(self.pending_prs)} pending PRs")
        except Exception as e:
            logger.error(f"Failed to load pending PRs: {e}")
            self.pending_prs = {}

    def _save(self):
        """Save message mappings to disk"""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.message_map, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save message mappings: {e}")

    def _save_pending(self):
        """Save pending PRs to disk"""
        try:
            with open(self.pending_path, 'w') as f:
                json.dump(self.pending_prs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save pending PRs: {e}")

    def store(self, lore_message_id: str, channel_message_map: Dict[int, int]):
        """Store mappings from lore message ID to Discord message IDs per channel"""
        self.message_map[lore_message_id] = channel_message_map
        self._save()
        logger.debug(f"Stored mapping: {lore_message_id} -> {len(channel_message_map)} channels")

    def get_channel_messages(self, lore_message_id: str) -> Dict[int, int]:
        """Get dict of {channel_id: discord_message_id} for a lore message ID"""
        return self.message_map.get(lore_message_id, {})

    def get_channel_messages_by_refs(self, refs: list) -> Dict[int, int]:
        """Get channel message mappings by checking message references"""
        if not refs:
            return {}

        # Check each reference to see if we have a mapping
        for ref in refs:
            channel_messages = self.message_map.get(ref)
            if channel_messages:
                logger.debug(f"Found Discord messages via ref: {ref} -> {len(channel_messages)} channels")
                return channel_messages

        return {}

    def add_pending_pr(self, lore_message_id: str, pr_data: Dict):
        """Add a PR to pending tracking"""
        self.pending_prs[lore_message_id] = {
            'subject': pr_data.get('subject', ''),
            'subsystem': pr_data.get('subsystem', ''),
            'from': pr_data.get('from', ''),
            'date': pr_data.get('date', ''),
            'url': pr_data.get('url', '')
        }
        self._save_pending()
        logger.debug(f"Added pending PR: {lore_message_id}")

    def mark_pr_merged(self, lore_message_id: str):
        """Mark a PR as merged (remove from pending)"""
        if lore_message_id in self.pending_prs:
            del self.pending_prs[lore_message_id]
            self._save_pending()
            logger.debug(f"Marked PR as merged: {lore_message_id}")

    def get_pending_prs(self, subsystem: Optional[str] = None, older_than_days: Optional[int] = None) -> List[Dict]:
        """Get list of pending PRs, optionally filtered by subsystem or age"""
        pending = []

        for msg_id, pr_data in self.pending_prs.items():
            # Filter by subsystem if specified
            if subsystem and pr_data.get('subsystem') != subsystem:
                continue

            # Filter by age if specified
            if older_than_days is not None:
                try:
                    pr_date = datetime.fromisoformat(pr_data['date'])
                    age_days = (datetime.now(pr_date.tzinfo) - pr_date).days
                    if age_days < older_than_days:
                        continue
                except Exception:
                    pass

            pending.append({
                'id': msg_id,
                **pr_data
            })

        # Sort by date (oldest first)
        pending.sort(key=lambda x: x.get('date', ''))
        return pending

    def cleanup_old_entries(self, max_entries: int = 1000):
        """Keep only the most recent N entries to prevent unbounded growth"""
        if len(self.message_map) > max_entries:
            # Keep the last max_entries items
            # Note: This assumes dict maintains insertion order (Python 3.7+)
            items = list(self.message_map.items())
            self.message_map = dict(items[-max_entries:])
            self._save()
            logger.info(f"Cleaned up message map, kept {max_entries} entries")
