import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class MessageTracker:
    """Tracks mapping between lore message IDs and Discord message IDs"""

    def __init__(self, storage_path: str = "message_map.json"):
        self.storage_path = Path(storage_path)
        # Map lore message ID to dict of {channel_id: discord_message_id}
        self.message_map: Dict[str, Dict[int, int]] = {}
        self._load()

    def _load(self):
        """Load message mappings from disk"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r') as f:
                    self.message_map = json.load(f)
                logger.info(f"Loaded {len(self.message_map)} message mappings")
        except Exception as e:
            logger.error(f"Failed to load message mappings: {e}")
            self.message_map = {}

    def _save(self):
        """Save message mappings to disk"""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.message_map, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save message mappings: {e}")

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

    def cleanup_old_entries(self, max_entries: int = 1000):
        """Keep only the most recent N entries to prevent unbounded growth"""
        if len(self.message_map) > max_entries:
            # Keep the last max_entries items
            # Note: This assumes dict maintains insertion order (Python 3.7+)
            items = list(self.message_map.items())
            self.message_map = dict(items[-max_entries:])
            self._save()
            logger.info(f"Cleaned up message map, kept {max_entries} entries")
