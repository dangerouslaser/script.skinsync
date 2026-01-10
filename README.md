# Skin Sync

A Kodi add-on for CoreELEC that synchronizes skin settings, widget configurations, and keymaps between devices via SSH.

## Features

- **Push & Pull Sync** - Push settings to another device or pull from another device
- **Multi-Device Sync** - Push to all paired devices at once
- **Selective Sync** - Choose what to sync: skin settings, widgets, keymaps
- **Automatic Backups** - Creates timestamped backups before any sync operation
- **Widget Sync** - Syncs widget configurations from script.skinvariables
- **Keymaps Sync** - Optionally sync keyboard and remote mappings
- **SSH Key Management** - Generates ED25519 SSH keys for secure passwordless authentication
- **Avahi/mDNS Discovery** - Fast device discovery using Zeroconf, with IP scan fallback
- **Manual Device Entry** - Add devices manually by IP address
- **Paired Devices** - Remembers devices you've synced with for quick access

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

### Main Menu

After setup, the main menu offers:

| Option | Description |
|--------|-------------|
| **Push to device...** | Send your settings to another device |
| **Push to ALL paired devices** | Sync to all remembered devices at once |
| **Pull from device...** | Copy settings FROM another device to yours |
| **Create backup** | Manually create a backup of your current settings |
| **Settings** | Manage paired devices, reset SSH keys |

### Syncing

1. Choose Push or Pull from the main menu
2. Select a target device from the list
3. Choose what to sync (multiselect):
   - Skin settings
   - Widget configurations
   - Keymaps
4. Confirm the operation
5. A backup is created automatically before syncing
6. Settings are copied and Kodi restarts on the affected device

## What Gets Synced

| Component | Location | Description |
|-----------|----------|-------------|
| Skin Settings | `/storage/.kodi/userdata/addon_data/skin.xxx/` | All skin-specific settings and customizations |
| Widget Configs | `/storage/.kodi/userdata/addon_data/script.skinvariables/nodes/skin.xxx/` | Custom widget configurations |
| Keymaps | `/storage/.kodi/userdata/keymaps/` | Keyboard and remote mappings |

## Backups

Backups are stored in:
```
/storage/.kodi/userdata/addon_data/script.skinsync/backups/
```

Each backup is timestamped and contains:
- `skin_settings/` - Skin configuration files
- `widgets/` - Widget JSON configurations
- `keymaps/` - Keymap XML files

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

## Troubleshooting

**No devices found during scan**
- Ensure target devices are powered on and connected to the network
- Check that SSH is enabled on target devices
- Use "Add device manually..." to enter the IP address directly

**Authentication failed**
- Use the "Reset SSH Keys" option in settings to start fresh
- Ensure you're using the correct password (default CoreELEC password is `coreelec`)

**Sync completed but settings not applied**
- Kodi restarts automatically after sync
- If settings don't appear, try restarting Kodi manually

**Widgets not syncing**
- Widget configs are stored separately in `script.skinvariables`
- Ensure you select "Widget configurations" in the sync options

## License

MIT License - see [LICENSE](LICENSE) for details.
