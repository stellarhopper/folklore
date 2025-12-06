# Linux Kernel Discord Bot

A Discord bot that monitors Linux kernel releases and subsystem activity, posting updates to Discord channels.

## Features

- **Kernel Release Monitoring**: Automatically detects new Linux kernel tags and releases from git.kernel.org
- **GitHub Project Monitoring**: Tracks new releases for configured GitHub repositories (e.g., ndctl)
- **Subsystem Activity Tracking**: Monitors specified mailing lists for:
  - Merged PR notifications from pr-bot
  - [GIT PULL] request emails
- **Discord Commands**:
  - `/ver` - Get the latest Linux kernel version
  - `/phb` - Get next 3 kernel release date predictions from PHB Crystal Ball
  - `/pending` - List all unmerged pull requests with age tracking
  - `/info` - Show bot version, git SHA, and features
- **Per-channel Subscriptions**: Configure which subsystems each channel monitors
- **Pending PR Tracking**: Automatically tracks unmerged PRs and warns about old ones
- **Manual Merge Check**: React to any pending PR message to manually check and update merge status

## Setup

### 1. Install Dependencies

First, install system dependencies:

**Fedora/RHEL/CentOS:**
```bash
sudo dnf install python3-devel gcc lei
pip install b4
```

**Ubuntu/Debian:**
```bash
sudo apt install python3-dev build-essential lei pipx
pipx install b4
```

**Note:** Debian's apt package for b4 (version 0.12.0) is too old and lacks the `--single-message` flag needed for extracting git commit URLs. Use pipx to install b4 >= 0.13.0 instead.

Then install Python dependencies:
```bash
pip install -r requirements.txt
```

**Required Tools:**
- `lei` - Local Email Interface for querying lore.kernel.org mailing lists
- `b4` - Tool for fetching kernel patches and mbox files from lore

### 2. Create Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the bot token
5. Enable "Message Content Intent" in bot settings
6. Invite bot to your server with appropriate permissions

### 3. Configure the Bot

First, copy the environment file and set your Discord token:

```bash
cp .env.example .env
# Edit .env and set your DISCORD_TOKEN
```

Then edit `config.json` with your settings:

```json
{
  "discord": {
    "subscriptions": [
      {
        "guild_id": 1234567890,
        "channel": "bot-spam",
        "subsystems": ["*"]
      },
      {
        "guild_id": 1234567890,
        "channel": "releases",
        "subsystems": ["kernel-release", "ndctl-release"]
      }
    ]
  },
  "kernel": {
    "check_interval_minutes": 60,
    "subsystems": [
      {
        "name": "linux-cxl",
        "lore_url": "https://lore.kernel.org/linux-cxl/"
      },
      {
        "name": "nvdimm",
        "lore_url": "https://lore.kernel.org/nvdimm/"
      },
      {
        "name": "x86",
        "lore_url": "https://lore.kernel.org/all/?q=tc:x86@kernel.org"
      }
    ]
  },
  "github_projects": [
    {
      "name": "ndctl-release",
      "repo": "pmem/ndctl",
      "description": "ndctl - Non-Volatile Memory Device Control"
    }
  ],
  "phb_url": "https://phb-crystal-ball.sipsolutions.net/"
}
```

**Notes**:
- `"*"` includes all subsystems and kernel releases (NOT GitHub releases)
- Use `"kernel-release"` to subscribe to kernel/RC announcements
- Use GitHub project names like `"ndctl-release"` to subscribe to GitHub releases

### 4. Run the Bot

```bash
python main.py
```

## Configuration

### Environment Variables

- `DISCORD_TOKEN`: Your Discord bot token (required)

### Discord Settings

- `subscriptions`: Array of subscription configurations
  - `guild_id`: Discord server/guild ID (required)
  - `channel`: Channel name where notifications will be posted (required)
  - `subsystems`: Array of subsystem names to monitor (required)
    - `["*"]` - Subscribe to all subsystems and kernel releases (NOT GitHub releases)
    - `["kernel-release"]` - Subscribe only to kernel/RC announcements
    - `["ndctl-release"]` - Subscribe to specific GitHub project releases
    - `["linux-cxl", "nvdimm"]` - Subscribe to specific subsystems only

### Kernel Monitoring

- `check_interval_minutes`: How often to check for updates (default: 30 minutes)
- `subsystems`: List of kernel subsystems to monitor

### Subsystem Configuration

Each subsystem entry should have:
- `name`: Display name for the subsystem
- `lore_url`: URL to the lore mailing list or search query

For subsystems without dedicated mailing lists, use search URLs like:
```
https://lore.kernel.org/all/?q=tc:subsystem@kernel.org
```

### GitHub Project Monitoring

- `github_projects`: Array of GitHub repositories to monitor for releases
  - `name`: Identifier for subscriptions (e.g., "ndctl-release")
  - `repo`: GitHub repository in "owner/repo" format (e.g., "pmem/ndctl")
  - `description`: Human-readable description for embed titles
- Only full published releases are monitored (prereleases and drafts are ignored)
- Release notes are truncated to first 5 lines with a "more..." link

## Commands

- `/ver` - Shows the latest Linux kernel version/tag
- `/phb` - Shows predicted release dates for the next 3 kernel versions
- `/pending` - Lists unmerged pull requests for channel's subscribed subsystems
- `/info` - Shows bot version, git commit SHA, and feature list

## Monitoring Features

### Kernel Releases
- Monitors git.kernel.org for new tags
- Distinguishes between stable releases and release candidates
- Posts embedded messages with version info and clickable links
- Subscription-based: use "kernel-release" in subsystems (included in "*")

### GitHub Project Releases
- Monitors configured GitHub repositories for new releases
- Filters out prereleases and drafts
- Shows release name, author, tag, and truncated release notes
- Subscription-based: use project name (e.g., "ndctl-release") in subsystems
- **Note**: GitHub releases are NOT included in "*" wildcard

### Subsystem Activity
- **Git Pull Requests**: Detects [GIT PULL] emails on mailing lists
  - Posts notification when PR is submitted
  - Updates message in-place when PR is merged by pr-tracker-bot
  - Shows submit date, merge date, and time-to-merge duration
  - Displays commit hash and link to torvalds/linux.git merge commit
- **Per-channel filtering**: Each subscription only receives notifications for its configured subsystems
- **Pending PR Tracking**: Automatically tracks unmerged PRs
  - Use `/pending` command to see all waiting PRs
  - Shows age of each PR in days
  - Warns about PRs older than 7 days
  - Filtered by channel's subscribed subsystems
- **Manual Merge Check**: React to any pending PR message with any emoji
  - Bot queries lore.kernel.org for merge status
  - Updates message in ALL channels if merge is found
  - Adds ✅ reaction on success, ❌ if no merge found
  - Useful for retroactively fixing missed merge updates

## Logs

The bot logs activity to both `bot.log` and stdout. Check logs for debugging and monitoring bot activity.

## Requirements

- Python 3.8+
- Discord.py 2.3+
- Internet connection for fetching kernel.org and lore.kernel.org data