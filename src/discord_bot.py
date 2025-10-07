import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime
from bs4 import BeautifulSoup

from .kernel_monitor import KernelMonitor
from .lore_monitor import LoreMonitor
from .message_tracker import MessageTracker
from version import __version__

logger = logging.getLogger(__name__)

class KernelBot(commands.Bot):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='/', intents=intents)

        self.config = config
        self.target_channels = []  # List of channels matching the configured name
        self.kernel_monitor = None
        self.lore_monitor = None
        self.message_tracker = MessageTracker()

    async def setup_hook(self):
        """Called when the bot is starting up"""
        logger.info("Bot is starting up...")

        # Register slash commands
        ver_cmd = discord.app_commands.Command(
            name="ver",
            description="Get the latest Linux kernel version",
            callback=self.ver_callback
        )
        phb_cmd = discord.app_commands.Command(
            name="phb",
            description="Predict next 3 kernel release dates",
            callback=self.phb_callback
        )
        info_cmd = discord.app_commands.Command(
            name="info",
            description="Display bot information and version",
            callback=self.info_callback
        )
        self.tree.add_command(ver_cmd)
        self.tree.add_command(phb_cmd)
        self.tree.add_command(info_cmd)

        # Initialize monitors
        self.kernel_monitor = KernelMonitor()
        self.lore_monitor = LoreMonitor(self.config['kernel']['subsystems'])

        # Start monitoring tasks with configured interval
        interval_minutes = self.config['kernel']['check_interval_minutes']
        self.check_kernel_releases.change_interval(minutes=interval_minutes)
        self.check_subsystem_activity.change_interval(minutes=interval_minutes)
        self.check_kernel_releases.start()
        self.check_subsystem_activity.start()

    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f'{self.user} has connected to Discord!')

        # Find target channels across all guilds
        self.target_channels = []
        channel_name = self.config['discord']['channel']

        for guild in self.guilds:
            for channel in guild.channels:
                if channel.name == channel_name and hasattr(channel, 'send'):
                    self.target_channels.append(channel)
                    logger.info(f"Found target channel: {channel.name} in {guild.name}")

        if not self.target_channels:
            logger.warning(f"No channels named '{channel_name}' found in any guild")
        else:
            logger.info(f"Monitoring {len(self.target_channels)} channels across {len(self.guilds)} guilds")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
            for cmd in synced:
                logger.info(f"  - {cmd.name}: {cmd.description}")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

        # Debug: Show available commands in tree
        logger.info(f"Commands in tree: {[cmd.name for cmd in self.tree.get_commands()]}")

    async def on_guild_join(self, guild):
        """Called when bot joins a new guild"""
        logger.info(f"Joined new guild: {guild.name}")

        # Look for the target channel in the new guild
        channel_name = self.config['discord']['channel']
        for channel in guild.channels:
            if channel.name == channel_name and hasattr(channel, 'send'):
                self.target_channels.append(channel)
                logger.info(f"Added target channel: {channel.name} in {guild.name}")
                break

    async def send_to_all_channels(self, content=None, embed=None):
        """Send a message to all target channels and return message IDs"""
        if not self.target_channels:
            logger.warning("No target channels available for sending message")
            return []

        message_ids = []
        for channel in self.target_channels:
            try:
                if embed:
                    msg = await channel.send(embed=embed)
                else:
                    msg = await channel.send(content)
                message_ids.append(msg.id)
            except Exception as e:
                logger.error(f"Failed to send message to {channel.name} in {channel.guild.name}: {e}")

        return message_ids

    async def edit_all_channels(self, message_id: int, content=None, embed=None):
        """Edit a message in all target channels by message ID"""
        if not self.target_channels:
            logger.warning("No target channels available for editing message")
            return

        for channel in self.target_channels:
            try:
                # Fetch the message from the channel
                msg = await channel.fetch_message(message_id)
                if msg:
                    if embed:
                        await msg.edit(embed=embed, content=content)
                    else:
                        await msg.edit(content=content)
                    logger.info(f"Edited message {message_id} in {channel.name}")
            except discord.NotFound:
                logger.debug(f"Message {message_id} not found in {channel.name}")
            except Exception as e:
                logger.error(f"Failed to edit message {message_id} in {channel.name}: {e}")

    @tasks.loop(minutes=30)
    async def check_kernel_releases(self):
        """Periodically check for new kernel releases"""
        try:
            async with self.kernel_monitor as monitor:
                new_release = await monitor.check_for_new_release()

                if new_release:
                    tag_info = new_release['new_tag']
                    embed = discord.Embed(
                        title="🐧 New Linux Kernel Release!",
                        description=f"**{tag_info['tag']}** has been released",
                        color=0x00ff00 if not tag_info['is_rc'] else 0xffaa00,
                        timestamp=datetime.fromisoformat(tag_info['timestamp'])
                    )

                    embed.add_field(
                        name="Version",
                        value=tag_info['version'],
                        inline=True
                    )

                    embed.add_field(
                        name="Type",
                        value="Release Candidate" if tag_info['is_rc'] else "Stable Release",
                        inline=True
                    )

                    embed.add_field(
                        name="Previous",
                        value=new_release['previous_tag'],
                        inline=True
                    )

                    await self.send_to_all_channels(embed=embed)

        except Exception as e:
            logger.error(f"Error checking kernel releases: {e}")

    @tasks.loop(minutes=30)
    async def check_subsystem_activity(self):
        """Check for subsystem activity (merged PRs and git pulls)"""
        try:
            async with self.lore_monitor as monitor:
                # Check for git pull requests FIRST (before merges)
                # This ensures we process original PRs before their merge confirmations
                # which is especially important on bot restarts
                git_pulls = await monitor.check_git_pull_requests()
                for pull in git_pulls:
                    embed = discord.Embed(
                        title="📥 Pull Request Submitted",
                        description=f"**{pull['subsystem']}**: {pull['subject']}",
                        color=0x0066cc,
                        url=pull['url']
                    )
                    embed.add_field(
                        name="From",
                        value=pull.get('from', 'Unknown'),
                        inline=True
                    )
                    embed.set_footer(text="Waiting to be merged")

                    # Send and store the Discord message ID
                    discord_msg_ids = await self.send_to_all_channels(embed=embed)
                    # Store the mapping from lore message ID to Discord message ID
                    # We'll use the first channel's message ID as the reference
                    if discord_msg_ids:
                        self.message_tracker.store(pull['id'], discord_msg_ids[0])

                # Now check for merged PRs
                merged_prs = await monitor.check_pr_bot_messages()
                for pr in merged_prs:
                    # Check if we have a Discord message for the original PR submission
                    discord_msg_id = self.message_tracker.get_discord_message_id_by_refs(pr.get('refs', []))

                    # Build the merged embed
                    embed = discord.Embed(
                        title="✅ PR Merged",
                        description=f"**{pr['subsystem']}**: {pr['subject']}",
                        color=0x00aa00,
                        url=pr['url']
                    )
                    # Add git commit URL if available
                    if 'commit_url' in pr:
                        # Extract commit hash from URL (last part after /)
                        commit_hash = pr['commit_url'].split('/')[-1]
                        embed.add_field(
                            name="Merge Commit",
                            value=f"[`{commit_hash[:12]}`]({pr['commit_url']})",
                            inline=False
                        )

                    if discord_msg_id:
                        # Edit the existing message
                        await self.edit_all_channels(discord_msg_id, embed=embed)
                    else:
                        # Post a new message
                        await self.send_to_all_channels(embed=embed)

        except Exception as e:
            logger.error(f"Error checking subsystem activity: {e}")

    async def ver_callback(self, interaction: discord.Interaction):
        """Slash command to get latest kernel version"""
        await interaction.response.defer()

        try:
            async with KernelMonitor() as monitor:
                tag_info = await monitor.get_latest_kernel_tag()

                if tag_info:
                    embed = discord.Embed(
                        title="🐧 Latest Linux Kernel",
                        color=0x00ff00 if not tag_info['is_rc'] else 0xffaa00
                    )

                    embed.add_field(
                        name="Version",
                        value=tag_info['tag'],
                        inline=True
                    )

                    embed.add_field(
                        name="Type",
                        value="Release Candidate" if tag_info['is_rc'] else "Stable Release",
                        inline=True
                    )

                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("❌ Could not fetch kernel version")

        except Exception as e:
            logger.error(f"Error in ver command: {e}")
            await interaction.followup.send("❌ Error fetching kernel version")

    async def phb_callback(self, interaction: discord.Interaction):
        """Slash command to get PHB crystal ball predictions"""
        await interaction.response.defer()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.config['phb_url']) as response:
                    if response.status == 200:
                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Parse the PHB prediction page
                        embed = discord.Embed(
                            title="🔮 PHB Crystal Ball Predictions",
                            description="Next 3 kernel release predictions",
                            color=0x9966ff,
                            url=self.config['phb_url']
                        )

                        # Look for predictions in the text content
                        predictions_found = False
                        text_content = soup.get_text()

                        # Find prediction lines using regex - capture both merge window and release dates
                        prediction_pattern = r'the (v\d+\.\d+) kernel predictions: merge window closes on.*?(\d{4}-\d{2}-\d{2}).*?release on.*?(\d{4}-\d{2}-\d{2})'
                        matches = re.findall(prediction_pattern, text_content)

                        if matches and len(matches) >= 3:
                            for i, (version, merge_close, release_date) in enumerate(matches[:3]):
                                embed.add_field(
                                    name=version,
                                    value=f"Merge window closes: {merge_close}\nRelease: {release_date}",
                                    inline=False
                                )
                            predictions_found = True
                        else:
                            # Fallback: try to find predictions in list items
                            for li in soup.find_all('li'):
                                li_text = li.get_text()
                                if 'kernel predictions:' in li_text and 'release on' in li_text:
                                    # Extract version and both dates from text
                                    version_match = re.search(r'(v\d+\.\d+)', li_text)
                                    merge_match = re.search(r'merge window closes on.*?(\d{4}-\d{2}-\d{2})', li_text)
                                    release_match = re.search(r'release on.*?(\d{4}-\d{2}-\d{2})', li_text)

                                    if version_match and merge_match and release_match:
                                        version = version_match.group(1)
                                        merge_date = merge_match.group(1)
                                        release_date = release_match.group(1)
                                        embed.add_field(
                                            name=version,
                                            value=f"Merge window closes: {merge_date}\nRelease: {release_date}",
                                            inline=False
                                        )
                                        predictions_found = True

                                        # Stop after 3 predictions
                                        if len(embed.fields) >= 3:
                                            break

                        if predictions_found:
                            await interaction.followup.send(embed=embed)
                        else:
                            await interaction.followup.send(f"📊 Check PHB predictions: {self.config['phb_url']}")
                    else:
                        await interaction.followup.send("❌ Could not fetch PHB predictions")

        except Exception as e:
            logger.error(f"Error in phb command: {e}")
            await interaction.followup.send("❌ Error fetching PHB predictions")

    async def info_callback(self, interaction: discord.Interaction):
        """Slash command to display bot info and version"""
        await interaction.response.defer()

        try:
            # Get git commit SHA
            git_sha = "unknown"
            try:
                result = subprocess.run(
                    ['git', 'rev-parse', '--short', 'HEAD'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    git_sha = result.stdout.strip()
            except Exception as e:
                logger.warning(f"Could not get git SHA: {e}")

            # Create info embed
            embed = discord.Embed(
                title="🤖 Folklore Discord Bot",
                description="Linux kernel monitoring and notification bot",
                color=0x00ff00,
                url="https://github.com/stellarhopper/folklore"
            )

            embed.add_field(
                name="Version",
                value=f"`{__version__}` (git: `{git_sha}`)",
                inline=False
            )

            embed.add_field(
                name="Repository",
                value="[github.com/stellarhopper/folklore](https://github.com/stellarhopper/folklore)",
                inline=False
            )

            embed.add_field(
                name="Features",
                value="• Kernel release monitoring\n• Subsystem activity tracking\n• PHB crystal ball predictions",
                inline=False
            )

            embed.set_footer(text="Auto-deployed via MQTT • Running on Raspberry Pi 5")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in info command: {e}")
            await interaction.followup.send("❌ Error fetching bot info")

    async def close(self):
        """Clean up when bot shuts down"""
        await super().close()