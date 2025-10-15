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
from .github_monitor import GitHubMonitor
from .message_tracker import MessageTracker
from version import __version__

logger = logging.getLogger(__name__)

class KernelBot(commands.Bot):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='/', intents=intents)

        self.config = config
        self.subscriptions = []  # List of {channel, subsystems} objects
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
        pending_cmd = discord.app_commands.Command(
            name="pending",
            description="List unmerged pull requests",
            callback=self.pending_callback
        )
        self.tree.add_command(ver_cmd)
        self.tree.add_command(phb_cmd)
        self.tree.add_command(info_cmd)
        self.tree.add_command(pending_cmd)

        # Initialize monitors
        self.kernel_monitor = KernelMonitor()
        self.lore_monitor = LoreMonitor(self.config['kernel']['subsystems'])

        # Initialize GitHub monitor if projects are configured
        github_projects = self.config.get('github_projects', [])
        if github_projects:
            self.github_monitor = GitHubMonitor(github_projects)
        else:
            self.github_monitor = None

        # Start monitoring tasks with configured interval
        interval_minutes = self.config['kernel']['check_interval_minutes']
        self.check_kernel_releases.change_interval(minutes=interval_minutes)
        self.check_subsystem_activity.change_interval(minutes=interval_minutes)
        self.check_kernel_releases.start()
        self.check_subsystem_activity.start()

        # Start GitHub monitoring if configured
        if self.github_monitor:
            self.check_github_releases.change_interval(minutes=interval_minutes)
            self.check_github_releases.start()

    async def on_ready(self):
        """Called when the bot is ready"""
        logger.info(f'{self.user} has connected to Discord!')

        # Find channels based on subscriptions
        self.subscriptions = []
        for sub_config in self.config['discord']['subscriptions']:
            guild_id = sub_config['guild_id']
            channel_name = sub_config['channel']
            subsystems = sub_config['subsystems']

            # Find the guild
            guild = self.get_guild(guild_id)
            if not guild:
                logger.warning(f"Guild {guild_id} not found (not in guild or invalid ID)")
                continue

            # Find the channel in this guild
            channel = discord.utils.get(guild.channels, name=channel_name)
            if channel and hasattr(channel, 'send'):
                self.subscriptions.append({
                    'channel': channel,
                    'subsystems': subsystems
                })
                logger.info(f"Subscribed {guild.name}#{channel.name} to {', '.join(subsystems)}")
            else:
                logger.warning(f"Channel '{channel_name}' not found in guild {guild.name}")

        if not self.subscriptions:
            logger.warning("No valid subscriptions found")
        else:
            logger.info(f"Monitoring {len(self.subscriptions)} channel subscriptions")

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
        logger.info("Note: Update config.json subscriptions and restart to monitor channels in this guild")

    async def send_to_subscribed_channels(self, subsystem: str, content=None, embed=None):
        """Send a message to channels subscribed to this subsystem, return dict of {channel_id: message_id}"""
        if not self.subscriptions:
            logger.warning("No subscriptions available for sending message")
            return {}

        message_map = {}
        for sub in self.subscriptions:
            # Check if channel is subscribed to this subsystem
            # "*" means subscribed to all subsystems
            if "*" in sub['subsystems'] or subsystem in sub['subsystems']:
                channel = sub['channel']
                try:
                    if embed:
                        msg = await channel.send(embed=embed)
                    else:
                        msg = await channel.send(content)
                    message_map[channel.id] = msg.id
                    logger.debug(f"Sent {subsystem} message to {channel.guild.name}#{channel.name}")
                except Exception as e:
                    logger.error(f"Failed to send {subsystem} message to {channel.guild.name}#{channel.name}: {e}")

        return message_map

    async def edit_channel_message(self, channel_id: int, message_id: int, content=None, embed=None):
        """Edit a specific message in a specific channel"""
        # Find the channel from subscriptions
        channel = None
        for sub in self.subscriptions:
            if sub['channel'].id == channel_id:
                channel = sub['channel']
                break

        if not channel:
            logger.warning(f"Channel {channel_id} not found in subscriptions")
            return

        try:
            msg = await channel.fetch_message(message_id)
            if msg:
                if embed:
                    await msg.edit(embed=embed, content=content)
                else:
                    await msg.edit(content=content)
                logger.debug(f"Edited message {message_id} in {channel.guild.name}#{channel.name}")
        except discord.NotFound:
            logger.debug(f"Message {message_id} not found in {channel.guild.name}#{channel.name}")
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} in {channel.guild.name}#{channel.name}: {e}")

    @tasks.loop(minutes=30)
    async def check_kernel_releases(self):
        """Periodically check for new kernel releases"""
        try:
            async with self.kernel_monitor as monitor:
                new_release = await monitor.check_for_new_release()

                if new_release:
                    tag_info = new_release['new_tag']

                    # Build git.kernel.org commit URL for this tag
                    tag_url = f"https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?h={tag_info['tag']}"

                    embed = discord.Embed(
                        title="🐧 New Linux Kernel Release!",
                        description=f"**[{tag_info['tag']}]({tag_url})** has been released",
                        color=0x008800 if not tag_info['is_rc'] else 0xffaa00,
                        url=tag_url,
                        timestamp=tag_info['timestamp']
                    )

                    embed.add_field(
                        name="Type",
                        value="Release Candidate" if tag_info['is_rc'] else "Stable Release",
                        inline=True
                    )

                    # Send to channels subscribed to "kernel-release" (or "*")
                    await self.send_to_subscribed_channels('kernel-release', embed=embed)

        except Exception as e:
            logger.error(f"Error checking kernel releases: {e}")

    @tasks.loop(minutes=30)
    async def check_github_releases(self):
        """Periodically check for new GitHub releases"""
        if not self.github_monitor:
            return

        try:
            async with self.github_monitor as monitor:
                new_releases = await monitor.check_for_new_releases()

                for release_info in new_releases:
                    project = release_info['project']
                    release = release_info['release']

                    # Build embed
                    embed = discord.Embed(
                        title=f"📦 {project['description']}",
                        description=f"**[{release['tag']}]({release['html_url']})** has been released",
                        color=0x008800,  # Dark green (same as kernel stable releases)
                        url=release['html_url'],
                        timestamp=datetime.fromisoformat(release['published_at'].replace('Z', '+00:00'))
                    )

                    embed.add_field(
                        name="Release Name",
                        value=release['name'],
                        inline=True
                    )

                    embed.add_field(
                        name="Author",
                        value=release['author'],
                        inline=True
                    )

                    embed.add_field(
                        name="Previous",
                        value=release_info['previous_tag'],
                        inline=True
                    )

                    # Truncate release notes to first 5 lines
                    body = release.get('body', '')
                    if body:
                        lines = body.split('\n')
                        truncated = '\n'.join(lines[:5])
                        if len(lines) > 5:
                            truncated += f"\n\n[more...]({release['html_url']})"
                        notes_value = truncated[:1024]
                    else:
                        notes_value = "No release notes"

                    embed.add_field(
                        name="Release Notes",
                        value=notes_value,
                        inline=False
                    )

                    # Send to channels subscribed to this project's subsystem name
                    await self.send_to_subscribed_channels(project['name'], embed=embed)

        except Exception as e:
            logger.error(f"Error checking GitHub releases: {e}")

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

                    # Parse and format submit date
                    try:
                        submit_date = datetime.fromisoformat(pull['date'])
                        submit_date_str = submit_date.strftime('%Y-%m-%d %H:%M UTC')
                    except:
                        submit_date_str = pull.get('date', 'Unknown')

                    embed.add_field(
                        name="Submit Date",
                        value=submit_date_str,
                        inline=True
                    )
                    embed.add_field(
                        name="Merge Date",
                        value="—",
                        inline=True
                    )
                    embed.set_footer(text="Waiting to be merged")

                    # Send to subscribed channels and store message IDs
                    channel_messages = await self.send_to_subscribed_channels(
                        pull['subsystem'], embed=embed
                    )
                    # Store the mapping from lore message ID to channel message IDs
                    if channel_messages:
                        self.message_tracker.store(pull['id'], channel_messages)
                        # Add to pending PR tracking
                        self.message_tracker.add_pending_pr(pull['id'], pull)

                # Now check for merged PRs
                merged_prs = await monitor.check_pr_bot_messages()
                for pr in merged_prs:
                    # Check if we have Discord messages for the original PR submission
                    channel_messages = self.message_tracker.get_channel_messages_by_refs(pr.get('refs', []))

                    # Try to get the original PR details from the refs
                    original_pr = None
                    if pr.get('refs'):
                        # Look through the git_pulls we just processed to find the matching one
                        for ref in pr['refs']:
                            matching_pull = next((p for p in git_pulls if p['id'] == ref), None)
                            if matching_pull:
                                original_pr = matching_pull
                                break

                    # Build the merged embed
                    embed = discord.Embed(
                        title="✅ PR Merged",
                        description=f"**{pr['subsystem']}**: {pr['subject']}",
                        color=0x00ff00,
                        url=pr['url']
                    )

                    # Preserve the "From" field if we found the original PR
                    if original_pr:
                        embed.add_field(
                            name="From",
                            value=original_pr.get('from', 'Unknown'),
                            inline=True
                        )

                    # Add dates - preserve submit date from original PR if available
                    submit_date_obj = None
                    if original_pr:
                        try:
                            submit_date_obj = datetime.fromisoformat(original_pr['date'])
                            submit_date_str = submit_date_obj.strftime('%Y-%m-%d %H:%M UTC')
                        except:
                            submit_date_str = original_pr.get('date', 'Unknown')
                    else:
                        submit_date_str = "Unknown"

                    # Format merge date and calculate duration
                    merge_date_obj = None
                    try:
                        merge_date_obj = datetime.fromisoformat(pr['date'])
                        merge_date_str = merge_date_obj.strftime('%Y-%m-%d %H:%M UTC')
                    except:
                        merge_date_str = pr.get('date', 'Unknown')

                    embed.add_field(
                        name="Submit Date",
                        value=submit_date_str,
                        inline=True
                    )
                    embed.add_field(
                        name="Merge Date",
                        value=merge_date_str,
                        inline=True
                    )

                    # Calculate and display merge duration
                    if submit_date_obj and merge_date_obj:
                        duration = merge_date_obj - submit_date_obj
                        days = duration.days
                        hours = duration.seconds // 3600
                        minutes = (duration.seconds % 3600) // 60

                        if days > 0:
                            duration_str = f"{days}d {hours}h"
                        elif hours > 0:
                            duration_str = f"{hours}h {minutes}m"
                        else:
                            duration_str = f"{minutes}m"

                        embed.add_field(
                            name="Time to Merge",
                            value=duration_str,
                            inline=True
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

                    if channel_messages:
                        # Edit existing messages in each channel
                        for channel_id, message_id in channel_messages.items():
                            await self.edit_channel_message(channel_id, message_id, embed=embed)
                    else:
                        # Post new messages to subscribed channels
                        await self.send_to_subscribed_channels(pr['subsystem'], embed=embed)

                    # Mark PR as merged (remove from pending list)
                    if pr.get('refs'):
                        for ref in pr['refs']:
                            self.message_tracker.mark_pr_merged(ref)

                # Cleanup old pending PRs (older than 21 days)
                self.message_tracker.cleanup_old_pending_prs(max_age_days=21)

        except Exception as e:
            logger.error(f"Error checking subsystem activity: {e}")

    async def ver_callback(self, interaction: discord.Interaction):
        """Slash command to get latest kernel version"""
        await interaction.response.defer()

        try:
            async with KernelMonitor() as monitor:
                tag_info = await monitor.get_latest_kernel_tag()

                if tag_info:
                    # Build git.kernel.org commit URL for this tag
                    tag_url = f"https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?h={tag_info['tag']}"

                    embed = discord.Embed(
                        title="🐧 Latest Linux Kernel",
                        color=0x008800 if not tag_info['is_rc'] else 0xffaa00,
                        url=tag_url
                    )

                    embed.add_field(
                        name="Version",
                        value=f"[{tag_info['tag']}]({tag_url})",
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

    async def pending_callback(self, interaction: discord.Interaction):
        """Slash command to list pending (unmerged) PRs"""
        await interaction.response.defer()

        try:
            from datetime import datetime, timezone

            # Find subscriptions for this guild/channel
            guild_id = interaction.guild_id
            channel_name = interaction.channel.name if interaction.channel else None

            # Get subscribed subsystems for this channel
            subscribed_subsystems = None
            for sub in self.subscriptions:
                # Match by channel object (guild_id and name already matched during setup)
                if sub['channel'].guild.id == guild_id and sub['channel'].name == channel_name:
                    subscribed_subsystems = sub['subsystems']
                    break

            # If no subscription found, default to all subsystems
            if subscribed_subsystems is None:
                logger.warning(f"No subscription found for guild {guild_id} channel {channel_name}, showing all PRs")
                subscribed_subsystems = ["*"]

            # Get all pending PRs
            all_pending = self.message_tracker.get_pending_prs()

            # Filter by subscribed subsystems
            pending_prs = []
            for pr in all_pending:
                pr_subsystem = pr.get('subsystem', 'unknown')
                # Include if wildcard or subsystem matches
                if "*" in subscribed_subsystems or pr_subsystem in subscribed_subsystems:
                    pending_prs.append(pr)

            if not pending_prs:
                await interaction.followup.send("✅ No pending PRs! All caught up.")
                return

            # Create embed
            embed = discord.Embed(
                title="📋 Pending Pull Requests",
                description=f"Found {len(pending_prs)} unmerged PR(s)",
                color=0x0066cc
            )

            # Group by subsystem
            by_subsystem = {}
            for pr in pending_prs:
                subsystem = pr.get('subsystem', 'unknown')
                if subsystem not in by_subsystem:
                    by_subsystem[subsystem] = []
                by_subsystem[subsystem].append(pr)

            # Add field for each subsystem
            for subsystem, prs in sorted(by_subsystem.items()):
                pr_list = []
                for pr in prs:
                    # Calculate age
                    try:
                        pr_date = datetime.fromisoformat(pr['date'])
                        age_days = (datetime.now(pr_date.tzinfo) - pr_date).days
                        age_str = f"{age_days}d" if age_days > 0 else "today"
                    except Exception:
                        age_str = "?"

                    # Truncate subject to fit
                    subject = pr.get('subject', 'Unknown')
                    if len(subject) > 60:
                        subject = subject[:57] + "..."

                    pr_list.append(f"[{subject}]({pr.get('url', '#')}) ({age_str})")

                # Add field (Discord limit: 1024 chars per field)
                field_value = "\n".join(pr_list[:10])  # Limit to 10 PRs per subsystem
                if len(prs) > 10:
                    field_value += f"\n_...and {len(prs) - 10} more_"

                embed.add_field(
                    name=f"**{subsystem}** ({len(prs)})",
                    value=field_value,
                    inline=False
                )

            # Add footer with warning for old PRs
            old_prs = [pr for pr in pending_prs
                      if (datetime.now(timezone.utc) - datetime.fromisoformat(pr['date'])).days >= 7]
            if old_prs:
                embed.set_footer(text=f"⚠️  {len(old_prs)} PR(s) older than 7 days")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"Error in pending command: {e}")
            await interaction.followup.send("❌ Error fetching pending PRs")

    async def close(self):
        """Clean up when bot shuts down"""
        await super().close()