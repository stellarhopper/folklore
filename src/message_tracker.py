import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class MessageTracker:
    """Tracks mapping between lore message IDs and Discord message IDs"""

    def __init__(self, storage_path: str = "message_map.json"):
        self.storage_path = Path(storage_path)
        self.message_map: Dict[str, int] = {}
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

    def store(self, lore_message_id: str, discord_message_id: int):
        """Store a mapping from lore message ID to Discord message ID"""
        self.message_map[lore_message_id] = discord_message_id
        self._save()
        logger.debug(f"Stored mapping: {lore_message_id} -> {discord_message_id}")

    def get_discord_message_id(self, lore_message_id: str) -> Optional[int]:
        """Get Discord message ID for a lore message ID"""
        return self.message_map.get(lore_message_id)

    def get_discord_message_id_by_refs(self, refs: list) -> Optional[int]:
        """Get Discord message ID by checking message references"""
        if not refs:
            return None

        # Check each reference to see if we have a mapping
        for ref in refs:
            discord_msg_id = self.message_map.get(ref)
            if discord_msg_id:
                logger.debug(f"Found Discord message via ref: {ref} -> {discord_msg_id}")
                return discord_msg_id

        return None

    def cleanup_old_entries(self, max_entries: int = 1000):
        """Keep only the most recent N entries to prevent unbounded growth"""
        if len(self.message_map) > max_entries:
            # Keep the last max_entries items
            # Note: This assumes dict maintains insertion order (Python 3.7+)
            items = list(self.message_map.items())
            self.message_map = dict(items[-max_entries:])
            self._save()
            logger.info(f"Cleaned up message map, kept {max_entries} entries")
