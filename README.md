# Birthday Sync Service

[![Build Status](https://github.com/anatosun/bdaysync/workflows/Build%20and%20Publish%20Docker%20Image/badge.svg)](https://github.com/anatosun/bdaysync/actions)
[![Docker Image](https://ghcr-badge.egpl.dev/anatosun/bdaysync/latest_by_date?trim=patch&label=latest)](https://github.com/anatosun/bdaysync/pkgs/container/bdaysync)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A containerized service that automatically syncs birthdays from CardDAV to CalDAV servers with built-in scheduling.

## Features

- **Automated Birthday Sync**: Fetches contacts from CardDAV and creates recurring birthday events in CalDAV
- **Multi-Server Support**: Compatible with Nextcloud, Baikal, Radicale, SOGo, and other CardDAV/CalDAV servers
- **Flexible Scheduling**: Cron-style scheduling or interval-based syncing
- **Customizable Events**: Template-based event titles, descriptions, and reminders
- **Container-Native**: Built for Docker with health checks and graceful shutdown
- **Multi-Architecture**: Supports AMD64 and ARM64 platforms

## Quick Start

### Using Pre-built Image

```bash
# Create environment file
cp .env.template .env
# Edit .env with your server credentials

# Run with docker-compose
docker-compose up -d

# Check logs
docker-compose logs -f birthday-sync
```

### Building Locally

```bash
git clone https://github.com/anatosun/bdaysync.git
cd bdaysync
docker-compose build
docker-compose up -d
```

## Configuration

### Environment Variables

| Variable            | Required | Default | Description        |
| ------------------- | -------- | ------- | ------------------ |
| `CARDAV_SERVER_URL` | ✅       | -       | CardDAV server URL |
| `CARDAV_USERNAME`   | ✅       | -       | CardDAV username   |
| `CARDAV_PASSWORD`   | ✅       | -       | CardDAV password   |
| `CALDAV_SERVER_URL` | ✅       | -       | CalDAV server URL  |
| `CALDAV_USERNAME`   | ✅       | -       | CalDAV username    |
| `CALDAV_PASSWORD`   | ✅       | -       | CalDAV password    |

### Scheduling Configuration

| Variable              | Default     | Description                       |
| --------------------- | ----------- | --------------------------------- |
| `RUN_MODE`            | `daemon`    | Run mode: `daemon`, `once`        |
| `SYNC_SCHEDULE`       | `0 6 * * *` | Cron schedule for sync            |
| `DIAGNOSTIC_SCHEDULE` | `0 7 * * 0` | Cron schedule for diagnostics     |
| `SYNC_INTERVAL_HOURS` | `0`         | Alternative: sync every N hours   |
| `STARTUP_DELAY`       | `30`        | Seconds to wait before first sync |

### Event Customization

| Variable                     | Default                                          | Description                     |
| ---------------------------- | ------------------------------------------------ | ------------------------------- |
| `BIRTHDAY_EVENT_TITLE`       | `🎂 {name}'s Birthday`                           | Event title template            |
| `BIRTHDAY_EVENT_DESCRIPTION` | `Birthday of {name}`                             | Event description template      |
| `BIRTHDAY_REMINDER_DAYS`     | `1,7`                                            | Reminder days (comma-separated) |
| `BIRTHDAY_REMINDER_MESSAGE`  | `Reminder: {name}'s birthday is in {days} days!` | Reminder message template       |
| `BIRTHDAY_EVENT_CATEGORY`    | `Birthday`                                       | Event category                  |
| `BIRTHDAY_UPDATE_EXISTING`   | `true`                                           | Update existing events          |

### Logging & Debug

| Variable      | Default | Description                             |
| ------------- | ------- | --------------------------------------- |
| `DEBUG`       | `false` | Enable debug logging                    |
| `LOG_LEVEL`   | `INFO`  | Log level (DEBUG, INFO, WARNING, ERROR) |
| `LOG_TO_FILE` | `false` | Write logs to file                      |
| `TZ`          | `UTC`   | Container timezone                      |

## Server Examples

### Nextcloud

```env
CARDAV_SERVER_URL=https://nextcloud.example.com/remote.php/dav/addressbooks/username/
CALDAV_SERVER_URL=https://nextcloud.example.com/remote.php/dav/calendars/username/personal/
```

### Baikal

```env
CARDAV_SERVER_URL=https://baikal.example.com/dav.php/addressbooks/username/
CALDAV_SERVER_URL=https://baikal.example.com/dav.php/calendars/username/default/
```

### Radicale

```env
CARDAV_SERVER_URL=https://radicale.example.com/username/
CALDAV_SERVER_URL=https://radicale.example.com/username/
```

## Usage

### Docker Run

```bash
docker run -d \
  --name birthday-sync \
  --env-file .env \
  -v birthday-logs:/var/log/birthday-sync \
  --restart unless-stopped \
  ghcr.io/anatosun/bdaysync:latest
```

### Management Commands

```bash
# Manual sync
docker exec birthday-sync python bdaysync/main.py --once

# Run diagnostics
docker exec birthday-sync python bdaysync/main.py --diagnose

# Health check
docker exec birthday-sync python bdaysync/main.py --health-check

# View logs
docker-compose logs -f birthday-sync

# Skip ASCII banner
docker exec birthday-sync python bdaysync/main.py --no-banner --once
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export CARDAV_SERVER_URL="https://your-server.com/dav/"
export CARDAV_USERNAME="username"
# ... other variables

# Run directly
cd bdaysync
python main.py --diagnose
python main.py --once
```

## Scheduling Examples

### Cron-Style Scheduling

```env
# Daily at 6 AM
SYNC_SCHEDULE=0 6 * * *

# Every 12 hours
SYNC_SCHEDULE=0 */12 * * *

# Weekdays at 9 AM
SYNC_SCHEDULE=0 9 * * 1-5

# Monthly on 1st at 6 AM
SYNC_SCHEDULE=0 6 1 * *
```

### Interval-Based Scheduling

```env
# Every 24 hours
SYNC_INTERVAL_HOURS=24

# Every 6 hours
SYNC_INTERVAL_HOURS=6
```

## Architecture

```
bdaysync/
├── main.py              # Entry point
├── config.py            # Environment validation & logging
├── cardav_client.py     # CardDAV operations
├── caldav_client.py     # CalDAV operations
├── scheduler.py         # Cron-like scheduling
└── __init__.py          # Package initialization
```

### Key Components

- **CardDAV Client**: Discovers addressbooks and fetches contacts with birthdays
- **CalDAV Client**: Creates/updates birthday events with customizable templates
- **Scheduler Service**: Handles cron-style or interval-based scheduling
- **Configuration Manager**: Validates environment and sets up logging

## Troubleshooting

### Debug Mode

```env
DEBUG=true
LOG_LEVEL=DEBUG
```

### Common Issues

**Authentication Failed:**

- Verify server URLs (check trailing slashes)
- Ensure credentials are correct
- Check if app passwords are required (Nextcloud, etc.)

**No Contacts Found:**

- Verify addressbook URL structure
- Check contacts have birthday fields populated
- Enable debug logging for detailed discovery info

**Events Not Created:**

- Verify calendar permissions
- Check CalDAV server supports event creation
- Review calendar URL format

**Template Errors:**

- Ensure proper escaping of special characters
- Use simple templates without complex formatting
- Check logs for format string errors

### Log Analysis

```bash
# View all logs
docker-compose logs birthday-sync

# Follow logs in real-time
docker-compose logs -f birthday-sync

# View last 50 lines
docker-compose logs --tail=50 birthday-sync

# Search for errors
docker-compose logs birthday-sync | grep -i error
```

## Multi-Architecture Support

Images are built for multiple architectures:

- `linux/amd64` (Intel/AMD 64-bit)
- `linux/arm64` (ARM 64-bit, Apple Silicon, Raspberry Pi 4+)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes using [Conventional commits](https://www.conventionalcommits.org/en/v1.0.0/) (`git commit -m 'feat: added amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Clone repository
git clone https://github.com/anatosun/bdaysync.git
cd bdaysync

# Install development dependencies
pip install -r requirements.txt

# Run the program
python -m bdaysync/main.py

```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/anatosun/bdaysync/issues)
- **Discussions**: [GitHub Discussions](https://github.com/anatosun/bdaysync/discussions)
- **Security**: Report security issues via [GitHub Security Advisories](https://github.com/anatosun/bdaysync/security/advisories)

## Acknowledgments

- Built with [caldav](https://github.com/python-caldav/caldav) and [vobject](https://github.com/eventable/vobject) libraries
