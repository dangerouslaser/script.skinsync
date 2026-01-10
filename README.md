# Skin Sync

A Kodi add-on for CoreELEC that synchronizes skin settings between devices via SSH.

## Features

- **SSH Key Management** - Generates ED25519 SSH keys for secure passwordless authentication
- **Avahi/mDNS Discovery** - Fast device discovery using Zeroconf, with IP scan fallback
- **Manual Device Entry** - Add devices manually by IP address if auto-discovery doesn't find them
- **Paired Devices** - Remembers devices you've synced with for quick access
- **One-Time Setup** - Enter your password once, then enjoy passwordless syncing
- **Skin Sync** - Copies your entire skin configuration to the target device
- **Remote Restart** - Automatically restarts Kodi on the target device after sync

## Requirements

- CoreELEC on all devices
- SSH enabled (default on CoreELEC)
- Devices on the same local network

## Installation

1. Download the latest release zip from the [Releases](https://github.com/dangerouslaser/script.skinsync/releases) page
2. In Kodi, go to **Add-ons → Install from zip file**
3. Navigate to the downloaded zip and install
4. The add-on will appear under **Program add-ons**

## Usage

### First Run (Setup)

1. Launch Skin Sync from Program add-ons
2. The setup wizard will:
   - Generate SSH keys on your device
   - Prompt for your CoreELEC password (root password, default: `coreelec`)
   - Scan your network for other CoreELEC devices
   - Copy your public key to discovered devices for passwordless access

### Syncing Skins

1. Launch Skin Sync
2. Select a target device from the list (shows hostname and IP)
3. Or choose "Add device manually..." to enter an IP address
4. Confirm the sync operation
5. Your skin settings will be copied and Kodi will restart on the target device

## Settings

Access via **Add-ons → Program add-ons → Skin Sync → Configure**

### Connection
| Setting | Description | Default |
|---------|-------------|---------|
| SSH Username | Username for SSH connections | `root` |
| Network Prefix | Network to scan (e.g., `192.168.1`) | Auto-detect |

### Paired Devices
| Setting | Description |
|---------|-------------|
| View Paired Devices | Shows all devices you've synced with |
| Remove Paired Device | Remove a device from the paired list |

### Advanced
| Setting | Description |
|---------|-------------|
| Reset SSH Keys | Regenerate keys and run setup again |

## How It Works

Skin Sync copies the contents of your current skin's `addon_data` directory:

```
/storage/.kodi/userdata/addon_data/skin.{your-skin}/
```

This includes all skin-specific settings, widget configurations, and customizations.

## Troubleshooting

**No devices found during scan**
- Ensure target devices are powered on and connected to the network
- Check that SSH is enabled on target devices
- Use "Add device manually..." to enter the IP address directly
- Try specifying your network prefix in settings if IP scan is slow

**Authentication failed**
- Use the "Reset SSH Keys" option in settings to start fresh
- Ensure you're using the correct password (default CoreELEC password is `coreelec`)

**Sync completed but settings not applied**
- The target Kodi should restart automatically
- If not, manually restart Kodi on the target device

## License

MIT License - see [LICENSE](LICENSE) for details.
