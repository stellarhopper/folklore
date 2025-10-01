# Linux Kernel Discord Bot - Development Context

This project is a Discord bot that monitors Linux kernel releases and subsystem activity, providing automated notifications and slash commands.

## Project Overview

**Purpose**: Monitor Linux kernel development and provide updates to Discord communities
**Language**: Python (discord.py)
**Architecture**: Async bot with scheduled monitoring tasks

## Key Features Implemented

### 1. Kernel Release Monitoring
- **Source**: git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/refs/tags
- **Function**: Detects new kernel tags/releases every 30 minutes
- **Logic**: Parses git tags page, sorts versions correctly (stable > RC7 > RC6...)
- **Fixed Issue**: Version sorting was broken - stable releases were sorting lower than RCs

### 2. Subsystem Monitoring
- **Sources**: Configured lore.kernel.org mailing lists
- **Monitored**:
  - linux-cxl: https://lore.kernel.org/linux-cxl/
  - nvdimm: https://lore.kernel.org/nvdimm/
  - x86: https://lore.kernel.org/all/?q=tc:x86@kernel.org (search filter)
- **Detection**:
  - Merged PRs (pr-bot messages)
  - Git pull requests ([GIT PULL] emails)

### 3. Discord Commands

#### `/ver` Command
- **Function**: Shows latest kernel version
- **Source**: Real-time fetch from git.kernel.org
- **Output**: Version, type (stable/RC), embedded message

#### `/phb` Command
- **Function**: Kernel release predictions
- **Source**: https://phb-crystal-ball.sipsolutions.net/
- **Output**: Next 3 versions with merge window close dates and release dates
- **Fixed Issues**:
  - Was parsing reference table instead of predictions
  - Version formatting (removed "vv" prefix)
  - Now shows both merge window and release dates

### 4. Multi-Server Support
- **Behavior**: Works across multiple Discord servers
- **Channel**: Sends to configured channel name in ALL servers bot is in
- **Commands**: Slash commands work in any channel
- **No Guild Config**: No server-specific configuration needed

## Technical Implementation

### Lore Monitoring with lei/b4
- **Replaced HTML scraping** with lei (Local Email Interface) for reliable mailing list queries
- **lei queries**: Use `-I https://lore.kernel.org/all/` with `-f json` for structured output
- **Query format**: `tc:MAILING_LIST AND dt:DAYS.days.ago..` for date-filtered searches
- **Message fetching**: Use `b4 mbox --single-message` to fetch individual pr-tracker-bot responses
  - Previously used `b4 am` which fetched entire threads (wrong messages)
- **Git URL extraction**: Regex match `https://git\.kernel\.org/[^\s]+` from pr-tracker-bot content
- **PR detection logic**:
  - **Merged PRs**: sender matches `pr-tracker-bot@kernel.org` (these are merge confirmations)
  - **Submitted PRs**: subject contains `[GIT PULL]`, NOT from pr-tracker-bot, NOT starting with "re:" (case-insensitive)

### Command Registration
- **Issue Resolved**: Slash commands had signature mismatch errors
- **Solution**: Use explicit `discord.app_commands.Command` objects with callbacks
- **Registration**: Commands added in `setup_hook()`, synced in `on_ready()`

### Security
- **Environment Variables**: Discord token stored in `DISCORD_TOKEN` env var
- **No Secrets in Files**: Sensitive data excluded from config.json

### Dependencies
- discord.py>=2.3.0
- aiohttp>=3.8.0
- beautifulsoup4>=4.12.0
- python-dotenv>=1.0.0
- **lei** (system tool) - Local Email Interface for querying lore.kernel.org
- **b4** (pip package) - Tool for fetching kernel patches and email content

### File Structure
```
src/
├── __init__.py
├── discord_bot.py      # Main bot class, commands, monitoring
├── kernel_monitor.py   # Kernel release detection
└── lore_monitor.py     # Mailing list monitoring
main.py                 # Entry point, config loading
config.json            # Bot configuration
requirements.txt       # Python dependencies
.env.example           # Environment template
```

## Configuration

### Environment Variables
- `DISCORD_TOKEN`: Bot token (required)

### config.json
```json
{
  "discord": {
    "channel": "bot-spam"  // Channel name in all servers
  },
  "kernel": {
    "check_interval_minutes": 60,  // How often to check for updates
    "subsystems": [...]    // List of {name, lore_url} objects
  },
  "phb_url": "https://phb-crystal-ball.sipsolutions.net/"
}
```

## Development Notes

### Bot Permissions Required
- Send Messages
- Use Slash Commands
- **Critical**: Bot must be invited with `applications.commands` scope

### Known Working Versions
- Python 3.13
- Fedora Linux (requires python3-devel for aiohttp compilation)

### Testing Commands
- `/ver` - Should show current stable kernel (v6.17 as of implementation)
- `/phb` - Should show v6.18, v6.19, v6.20 predictions with dates

### Monitoring Behavior
- **Releases**: Posts to all configured channels when new kernel detected
- **Subsystems**: Posts PR merges and git pulls to all configured channels
- **Frequency**: Checks every 30 minutes
- **Startup**: Only notifies on changes after first run (no spam on restart)

## Testing Status

### ✅ Tested and Working
- **Bot startup and connection** - Successfully connects to Discord
- **Slash command registration** - Commands appear and sync properly
- **`/ver` command** - Returns correct kernel version (fixed sorting bug, shows v6.17 stable)
- **`/phb` command** - Returns correct predictions with merge window and release dates
- **`/info` command** - Shows bot version, git SHA, features, and repository link
- **Multi-server support** - Bot finds channels across multiple servers
- **Environment variable loading** - Discord token loaded from DISCORD_TOKEN
- **Configuration loading** - config.json parsed correctly
- **Command permissions** - Works after proper bot invite with applications.commands scope
- **lei integration** - Successfully queries lore.kernel.org with JSON output
- **b4 integration** - Fetches individual pr-tracker-bot messages with --single-message
- **PR merge detection** - Detects pr-tracker-bot@kernel.org messages indicating merges
- **Git commit URL extraction** - Extracts and displays git.kernel.org commit URLs in Discord
- **Original PR detection** - Detects [GIT PULL] requests, filters out "Re:" replies (case-insensitive)
- **Message deduplication** - Uses seen_messages set to avoid duplicate notifications
- **Mailing list queries** - Correctly handles linux-cxl, nvdimm, and x86 (with tc: filter)

### ⚠️ Generated but Untested
- **Kernel release monitoring** - Automated detection of new releases (60min intervals)
  - `check_kernel_releases()` task scheduled but not verified with actual new release
  - Notification posting to channels when new release detected
  - Previous tag tracking to avoid duplicate notifications
- **Channel discovery on guild join** - `on_guild_join()` handler
- **Error handling** - Exception handling in monitoring tasks after network failures

### 🔍 Needs Verification
- **Message rate limiting** - Discord API limits with multiple channels
- **Monitoring task restart** - Behavior after network errors or Discord disconnections
- **Long-term stability** - 24-48 hour continuous operation

### 📝 Testing Recommendations
1. **Monitor logs** for the next 24-48 hours to verify scheduled tasks work reliably
2. **Wait for actual kernel release** to test notification system (v6.18-rc1 expected soon)
3. **Test multi-server behavior** by inviting bot to another server
4. **Verify error recovery** by simulating network issues

## Future Considerations
- Could add more subsystems to monitor
- Could add configuration commands to manage subsystems dynamically
- Could add filtering/alerting based on specific maintainers or topics
- Could add historical tracking/stats