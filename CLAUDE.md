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
- **Subscription**: Uses special subsystem name `"kernel-release"` for filtering
  - Channels subscribed to `"*"` automatically receive kernel releases
  - Channels can explicitly subscribe to `"kernel-release"` without `"*"`
- **Fixed Issue**: Version sorting was broken - stable releases were sorting lower than RCs

### 2. GitHub Project Monitoring
- **Source**: GitHub API (api.github.com/repos/{owner}/{repo}/releases/latest)
- **Function**: Detects new GitHub releases for configured projects
- **Filtering**: Only monitors published releases (no prereleases or drafts)
- **Subscription**: Each project gets a unique subsystem name (e.g., `"ndctl-release"`)
- **Display**: Shows release tag, name, author, and truncated release notes (first 5 lines)
- **Configuration**: Projects defined in `github_projects` array with name, repo, and description

### 3. Subsystem Monitoring
- **Sources**: Configured lore.kernel.org mailing lists
- **Monitored**:
  - linux-cxl: https://lore.kernel.org/linux-cxl/
  - nvdimm: https://lore.kernel.org/nvdimm/
  - x86: https://lore.kernel.org/all/?q=tc:x86@kernel.org (search filter)
- **Detection**:
  - Merged PRs (pr-bot messages)
  - Git pull requests ([GIT PULL] emails)
- **Message Update Behavior**:
  - Posts PR submission message when [GIT PULL] email detected
  - Updates existing message in-place when pr-tracker-bot confirms merge
  - Preserves original sender info and adds merge details
  - Shows submit date, merge date, and time-to-merge duration
  - Displays commit hash and link to torvalds/linux.git merge commit

### 4. Discord Commands

#### `/ver` Command
- **Function**: Shows latest kernel version
- **Source**: Real-time fetch from git.kernel.org
- **Output**: Version, type (stable/RC), embedded message with clickable link to tag commit
- **Colors**: Dark green (0x008800) for stable, orange (0xffaa00) for RC

#### Color Scheme
- **PR Submitted**: Blue (0x0066cc)
- **PR Merged**: Bright green (0x00ff00)
- **/ver stable**: Dark green (0x008800)
- **/ver RC**: Orange (0xffaa00)
- **/phb**: Purple (0x9966ff)
- **GitHub releases**: Dark green (0x008800)

#### `/phb` Command
- **Function**: Kernel release predictions
- **Source**: https://phb-crystal-ball.sipsolutions.net/
- **Output**: Next 3 versions with merge window close dates and release dates
- **Fixed Issues**:
  - Was parsing reference table instead of predictions
  - Version formatting (removed "vv" prefix)
  - Now shows both merge window and release dates

#### `/pending` Command
- **Function**: List all unmerged pull requests
- **Output**: Grouped by subsystem, showing age in days
- **Filtering**: Only shows PRs for subsystems the channel is subscribed to (respects wildcard "*")
- **Features**:
  - Shows how long each PR has been waiting
  - Warning footer for PRs older than 7 days
  - Clickable links to lore.kernel.org
  - Limited to 10 PRs per subsystem for readability

#### `/info` Command
- **Function**: Show bot information
- **Output**: Version, git commit SHA, repository link, features list

### 5. Manual Merge Status Check (Reaction-Based)
- **Trigger**: React with any emoji to a pending PR message
- **Function**: Manually check if a PR has been merged and update the message
- **Behavior**:
  - Bot queries lore.kernel.org for pr-tracker-bot merge messages referencing the PR
  - If found: Updates message to merged status in ALL channels where PR was posted
  - If not found: Adds ❌ reaction to indicate no merge detected
  - If PR data missing: Adds ⚠️ reaction
  - On success: Adds ✅ reaction and updates embed with merge details
- **Use Case**: Retroactively fix missed merge updates or verify merge status on demand
- **Multi-channel**: One reaction updates the message in every channel where that PR was posted

### 6. Multi-Server and Multi-Channel Support
- **Subscription-based routing**: Each guild/channel can subscribe to specific subsystems
- **Wildcard support**: Use `["*"]` to subscribe to all subsystems and kernel releases (NOT GitHub releases)
- **Selective filtering**: Subscribe to specific subsystems like `["linux-cxl", "nvdimm"]`
- **Kernel release subscription**: Add `"kernel-release"` to receive kernel/RC announcements
- **GitHub release subscription**: Add project names like `"ndctl-release"` to receive GitHub releases
- **Commands**: Slash commands work in any channel
- **Per-channel message tracking**: PR submission messages update independently per channel when merged

## Technical Implementation

### Lore Monitoring with lei/b4
- **Replaced HTML scraping** with lei (Local Email Interface) for reliable mailing list queries
- **lei queries**: Use `-I https://lore.kernel.org/all/` with `-f json` for structured output
- **Query format**: `tc:MAILING_LIST AND dt:DAYS.days.ago..` for date-filtered searches
- **Message fetching**: Use `b4 mbox --single-message` to fetch individual pr-tracker-bot responses
  - Previously used `b4 am` which fetched entire threads (wrong messages)
- **Git URL extraction**: Regex match `https://git\.kernel\.org/torvalds/c/[0-9a-f]+` specifically for merge commits
  - Previously matched first URL which pointed to subsystem trees, not torvalds merge commits
- **PR detection logic**:
  - **Merged PRs**: sender matches `pr-tracker-bot@kernel.org` (these are merge confirmations)
  - **Submitted PRs**: subject contains `[GIT PULL]`, NOT from pr-tracker-bot, NOT starting with "re:" (case-insensitive)
- **Chronological processing**: Messages sorted by date (oldest first) to ensure PRs processed before merges
  - Critical for proper message editing on bot restart

### Message Tracking and Editing
- **MessageTracker class**: Persists lore message ID to Discord message ID mappings
- **Storage**: JSON file (`message_map.json`) with structure `{lore_msg_id: {channel_id: discord_msg_id}}`
- **Threading support**: Uses email `refs` field from pr-tracker-bot to link merges back to original PRs
- **Per-channel tracking**: Each subscription channel gets independent message ID for editing
- **Cleanup**: Automatically keeps only 1000 most recent entries to prevent unbounded growth
- **Type handling**: Converts JSON string keys back to int channel IDs on load (JSON serializes int keys as strings)
- **Edit flow**:
  1. PR submitted: Create Discord embed, post to subscribed channels, store message IDs
  2. PR merged: Lookup original message IDs via `refs`, edit messages in-place with merge details
  3. Manual check: React to any PR message to trigger merge status check across all channels

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
- **b4** >= 0.13.0 (pip/pipx package) - Tool for fetching kernel patches and email content
  - Note: Debian's apt package (0.12.0) is too old, use `pipx install b4` instead
  - The `--single-message` flag is required for git URL extraction

### File Structure
```
src/
├── __init__.py
├── discord_bot.py      # Main bot class, commands, monitoring, subscription routing
├── kernel_monitor.py   # Kernel release detection
├── lore_monitor.py     # Mailing list monitoring with lei/b4
└── message_tracker.py  # Discord message ID persistence, pending PR tracking
main.py                 # Entry point, config loading, subscription validation
config.json            # Bot configuration with subscriptions
message_map.json       # Runtime: lore↔Discord message mappings
pending_prs.json       # Runtime: unmerged PR tracking with metadata
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
    "subscriptions": [
      {
        "guild_id": 1420254013458223158,
        "channel": "bot-spam",
        "subsystems": ["*"]  // "*" for all subsystems + kernel releases
      },
      {
        "guild_id": 1420254013458223158,
        "channel": "bot-test1",
        "subsystems": ["linux-cxl", "nvdimm", "kernel-release", "ndctl-release"]
      }
    ]
  },
  "kernel": {
    "check_interval_minutes": 60,  // How often to check for updates
    "subsystems": [...]    // List of {name, lore_url} objects
  },
  "github_projects": [
    {
      "name": "ndctl-release",           // Subscription name
      "repo": "pmem/ndctl",               // GitHub repo (owner/name)
      "description": "ndctl - Non-Volatile Memory Device Control"
    }
  ],
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
- **Releases**: Posts to all subscribed channels when new kernel detected
- **Subsystems**: Posts to channels subscribed to each subsystem (filtered or wildcard)
- **Frequency**: Checks every interval configured in `kernel.check_interval_minutes` (default 60)
- **Startup**: Only notifies on changes after first run (no spam on restart)
- **Message lifecycle**:
  - PR submitted → posts "🔔 PR Submitted" with From, Subject, Submit Date
  - PR merged → edits existing message to "✅ PR Merged" with Merge Commit, Merge Date, Duration

## Testing Status

### ✅ Tested and Working
- **Bot startup and connection** - Successfully connects to Discord
- **Slash command registration** - Commands appear and sync properly
- **`/ver` command** - Returns correct kernel version (fixed sorting bug, shows v6.17 stable)
- **`/phb` command** - Returns correct predictions with merge window and release dates
- **`/info` command** - Shows bot version, git SHA, features, and repository link
- **Multi-server support** - Bot finds channels across multiple servers
- **Subscription-based routing** - Channels receive only subscribed subsystems
- **Wildcard subscriptions** - `["*"]` receives all subsystem messages
- **Environment variable loading** - Discord token loaded from DISCORD_TOKEN
- **Configuration loading** - config.json parsed correctly with subscription validation
- **Command permissions** - Works after proper bot invite with applications.commands scope
- **lei integration** - Successfully queries lore.kernel.org with JSON output
- **b4 integration** - Fetches individual pr-tracker-bot messages with --single-message (requires 0.13.0+)
- **PR merge detection** - Detects pr-tracker-bot@kernel.org messages indicating merges
- **Git commit URL extraction** - Extracts torvalds/linux.git merge commit URLs (not subsystem trees)
- **Commit hash display** - Shows first 12 chars of commit hash as clickable link
- **Original PR detection** - Detects [GIT PULL] requests, filters out "Re:" replies (case-insensitive)
- **Message editing** - Updates PR submitted messages in-place when merged
- **Message persistence** - MessageTracker stores and retrieves lore↔Discord mappings
- **Per-channel tracking** - Each subscribed channel's message edits independently
- **Date tracking** - Shows submit date, merge date, and time-to-merge duration (e.g., "2d 5h")
- **Sender preservation** - "From" field preserved during submitted→merged transition
- **Chronological processing** - Messages sorted by date, PRs processed before merges
- **Message deduplication** - Uses seen_messages set to avoid duplicate notifications
- **Mailing list queries** - Correctly handles linux-cxl, nvdimm, and x86 (with tc: filter)
- **Pending PR tracking** - Tracks unmerged PRs with metadata (subject, subsystem, from, date, URL)
- **/pending command** - Lists all pending PRs grouped by subsystem with age indicators
- **Timeout warnings** - Highlights PRs older than 7 days in footer
- **Channel ID type fix** - Correctly converts JSON string keys to int for message editing after bot restart
- **Reaction-based merge check** - React to any pending PR message to manually trigger merge status lookup
- **Multi-channel reaction update** - Single reaction updates PR status in all channels where posted

### ⚠️ Generated but Untested
- **Kernel release monitoring** - Automated detection of new releases (60min intervals)
  - `check_kernel_releases()` task scheduled but not verified with actual new release
  - Notification posting to channels when new release detected
  - Previous tag tracking to avoid duplicate notifications
- **Channel discovery on guild join** - `on_guild_join()` handler
- **Error handling** - Exception handling in monitoring tasks after network failures

### 🔍 Needs Verification
- **Subscription filtering correctness** - Verify x86 messages appear in bot-spam but not bot-test1
- **Message rate limiting** - Discord API limits with multiple channels/subscriptions
- **Monitoring task restart** - Behavior after network errors or Discord disconnections
- **Long-term stability** - 24-48 hour continuous operation with subscription model

### 📝 Testing Recommendations
1. **Monitor logs** for the next 24-48 hours to verify scheduled tasks work reliably
2. **Wait for actual kernel release** to test notification system (v6.18-rc1 expected soon)
3. **Test multi-server behavior** by inviting bot to another server
4. **Verify subscription filtering** with x86 messages (should appear in bot-spam only, not bot-test1)
5. **Verify error recovery** by simulating network issues
6. **Test message editing** with actual PR submission followed by merge

## Known Issues and Fixes

### Fixed: Channel ID Type Mismatch (v0.3+)
- **Issue**: After bot restart, all PR merge message edits failed silently
- **Cause**: JSON serializes dict keys as strings, but Discord channel.id is int, causing comparison failures
- **Fix**: Convert string channel IDs back to ints when loading message_map.json
- **Impact**: All merge updates now work correctly after restarts

### Fixed: Missed Merge Updates
- **Issue**: PRs submitted before bot restart wouldn't get merge updates
- **Cause**: Original PR details were looked up from in-memory git_pulls list, not persistent storage
- **Fix**: Look up original PR from pending_prs.json instead of current monitoring cycle
- **Workaround**: React to any pending PR message to manually trigger merge check

## Future Considerations
- Could add more subsystems to monitor
- Could add configuration commands to manage subsystems dynamically
- Could add filtering/alerting based on specific maintainers or topics
- Could add historical tracking/stats