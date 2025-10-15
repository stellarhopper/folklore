import aiohttp
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class GitHubMonitor:
    """Monitor GitHub repositories for new releases"""

    def __init__(self, projects: List[Dict]):
        """
        Initialize with list of projects to monitor
        projects: [{"name": "ndctl-release", "repo": "pmem/ndctl", "description": "..."}]
        """
        self.session = None
        self.projects = projects
        # Track last known release per project
        self.last_known_releases: Dict[str, str] = {}

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_latest_release(self, repo: str) -> Optional[Dict]:
        """
        Fetch the latest release from GitHub API
        repo: "owner/repo" format (e.g., "pmem/ndctl")
        Returns release info or None
        """
        try:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'folklore-discord-bot'
            }

            async with self.session.get(url, headers=headers) as response:
                if response.status == 404:
                    logger.debug(f"No releases found for {repo}")
                    return None

                if response.status != 200:
                    logger.error(f"Failed to fetch releases for {repo}: {response.status}")
                    return None

                data = await response.json()

                # Skip prereleases and drafts
                if data.get('prerelease', False) or data.get('draft', False):
                    logger.debug(f"Skipping prerelease/draft for {repo}: {data.get('tag_name')}")
                    return None

                # Extract relevant info
                return {
                    'tag': data.get('tag_name', 'unknown'),
                    'name': data.get('name', data.get('tag_name', 'unknown')),
                    'published_at': data.get('published_at'),
                    'html_url': data.get('html_url'),
                    'body': data.get('body', ''),
                    'author': data.get('author', {}).get('login', 'unknown')
                }

        except Exception as e:
            logger.error(f"Error fetching releases for {repo}: {e}")
            return None

    async def check_for_new_releases(self) -> List[Dict]:
        """
        Check all configured projects for new releases
        Returns list of new releases with project info
        """
        new_releases = []

        for project in self.projects:
            project_name = project['name']
            repo = project['repo']

            latest_release = await self.get_latest_release(repo)

            if not latest_release:
                continue

            release_tag = latest_release['tag']

            # Check if this is a new release
            last_known = self.last_known_releases.get(project_name)

            if last_known != release_tag:
                self.last_known_releases[project_name] = release_tag

                # Don't notify on first run
                if last_known:
                    new_releases.append({
                        'project': project,
                        'release': latest_release
                    })
                    logger.info(f"New release for {project_name}: {release_tag} (was {last_known})")

        return new_releases
