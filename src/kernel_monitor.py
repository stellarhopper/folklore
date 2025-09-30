import aiohttp
import asyncio
import re
import json
from datetime import datetime
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class KernelMonitor:
    def __init__(self):
        self.session = None
        self.last_known_tag = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_latest_kernel_tag(self) -> Optional[Dict]:
        """Fetch the latest kernel tag from git.kernel.org"""
        try:
            url = "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/refs/tags"
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch kernel tags: {response.status}")
                    return None

                text = await response.text()

                # Parse the tags page to find version tags
                version_pattern = r'v(\d+\.\d+(?:\.\d+)?(?:-rc\d+)?)'
                matches = re.findall(version_pattern, text)

                if not matches:
                    return None

                # Sort versions to get the latest
                def version_key(version):
                    parts = version.split('-')
                    base = parts[0].split('.')

                    # For stable releases, use a high number (999) so they sort after RCs
                    # For RC versions, use the RC number directly (rc7 > rc6)
                    if len(parts) > 1 and parts[1].startswith('rc'):
                        rc = int(parts[1][2:])  # rc7=7, rc6=6, etc.
                    else:
                        rc = 999  # Stable release gets highest priority

                    return (int(base[0]), int(base[1]), int(base[2]) if len(base) > 2 else 0, rc)

                latest_version = max(matches, key=version_key)

                return {
                    'tag': f'v{latest_version}',
                    'version': latest_version,
                    'is_rc': '-rc' in latest_version,
                    'timestamp': datetime.now().isoformat()
                }

        except Exception as e:
            logger.error(f"Error fetching kernel tags: {e}")
            return None

    async def check_for_new_release(self) -> Optional[Dict]:
        """Check if there's a new kernel release since last check"""
        current_tag = await self.get_latest_kernel_tag()

        if not current_tag:
            return None

        if self.last_known_tag != current_tag['tag']:
            old_tag = self.last_known_tag
            self.last_known_tag = current_tag['tag']

            if old_tag:  # Don't notify on first run
                return {
                    'new_tag': current_tag,
                    'previous_tag': old_tag
                }

        return None