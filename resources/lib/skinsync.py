#!/usr/bin/env python3
"""
SkinSync - Main library for skin synchronization
"""

import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import subprocess
import socket
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed


class SkinSync:
    """Main class for skin synchronization between CoreELEC devices."""

    SSH_DIR = "/storage/.ssh"
    KEY_FILE = "/storage/.ssh/id_ed25519"
    KEY_FILE_PUB = "/storage/.ssh/id_ed25519.pub"
    KODI_ADDON_DATA = "/storage/.kodi/userdata/addon_data"
    KODI_USERDATA = "/storage/.kodi/userdata"
    KEYMAPS_PATH = "/storage/.kodi/userdata/keymaps"

    def __init__(self, addon):
        self.addon = addon
        self.addon_data_path = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
        self.paired_devices_file = os.path.join(self.addon_data_path, 'paired_devices.json')
        self.backup_dir = os.path.join(self.addon_data_path, 'backups')
        self.username = addon.getSetting('ssh_username') or 'root'
        self.network_prefix = addon.getSetting('network_prefix') or None
        self.dialog = xbmcgui.Dialog()
        self.progress = None

        # Ensure addon data directory exists
        if not os.path.exists(self.addon_data_path):
            os.makedirs(self.addon_data_path)
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

    def load_paired_devices(self):
        """Load paired devices from storage."""
        try:
            if os.path.exists(self.paired_devices_file):
                with open(self.paired_devices_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            self.log(f"Error loading paired devices: {e}", xbmc.LOGERROR)
        return []

    def save_paired_devices(self, devices):
        """Save paired devices to storage."""
        try:
            with open(self.paired_devices_file, 'w') as f:
                json.dump(devices, f, indent=2)
            self.log(f"Saved {len(devices)} paired devices")
        except Exception as e:
            self.log(f"Error saving paired devices: {e}", xbmc.LOGERROR)

    def add_paired_device(self, ip, name=None):
        """Add a device to the paired devices list."""
        devices = self.load_paired_devices()
        # Check if already exists
        for d in devices:
            if d.get('ip') == ip:
                return  # Already paired
        devices.append({
            'ip': ip,
            'name': name or ip,
            'added': time.strftime('%Y-%m-%d %H:%M:%S')
        })
        self.save_paired_devices(devices)

    def remove_paired_device(self, ip):
        """Remove a device from the paired devices list."""
        devices = self.load_paired_devices()
        devices = [d for d in devices if d.get('ip') != ip]
        self.save_paired_devices(devices)

    def get_paired_devices_string(self):
        """Get a formatted string of paired devices for settings display."""
        devices = self.load_paired_devices()
        if not devices:
            return "No paired devices"
        return ", ".join([d.get('ip', 'unknown') for d in devices])

    def view_paired_devices(self):
        """Show a dialog with all paired devices."""
        devices = self.load_paired_devices()
        if not devices:
            self.dialog.ok("Paired Devices", "No devices have been paired yet.\n\nRun Skin Sync and add a device to pair with it.")
            return

        lines = []
        for d in devices:
            ip = d.get('ip', 'unknown')
            added = d.get('added', 'unknown')
            lines.append(f"{ip}  (added: {added})")

        self.dialog.ok("Paired Devices", "\n".join(lines))

    def remove_paired_device_dialog(self):
        """Show a dialog to select and remove a paired device."""
        devices = self.load_paired_devices()
        if not devices:
            self.dialog.ok("Remove Device", "No paired devices to remove.")
            return

        device_list = [d.get('ip', 'unknown') for d in devices]
        selected = self.dialog.select("Select device to remove", device_list)

        if selected >= 0:
            ip = device_list[selected]
            if self.dialog.yesno("Confirm Removal", f"Remove {ip} from paired devices?"):
                self.remove_paired_device(ip)
                self.dialog.notification("Skin Sync", f"Removed {ip}", xbmcgui.NOTIFICATION_INFO)

    def log(self, message, level=xbmc.LOGINFO):
        """Log message to Kodi log."""
        xbmc.log(f"[SkinSync] {message}", level)
    
    def get_current_skin(self):
        """Get the currently active skin directory name."""
        return xbmc.getSkinDir()
    
    def get_skin_path(self):
        """Get the full path to current skin's addon_data."""
        skin = self.get_current_skin()
        return os.path.join(self.KODI_ADDON_DATA, skin)
    
    def get_local_ip(self):
        """Get this device's local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            self.log(f"Error getting local IP: {e}", xbmc.LOGERROR)
            return None
    
    def get_network_prefix(self):
        """Get the network prefix (e.g., 192.168.1)."""
        if self.network_prefix:
            return self.network_prefix
        
        local_ip = self.get_local_ip()
        if local_ip:
            parts = local_ip.split('.')
            return '.'.join(parts[:3])
        return None
    
    def keys_exist(self):
        """Check if SSH keys already exist."""
        return os.path.exists(self.KEY_FILE) and os.path.exists(self.KEY_FILE_PUB)
    
    def generate_keys(self):
        """Generate SSH key pair."""
        self.log("Generating SSH keys...")
        
        # Create .ssh directory if it doesn't exist
        os.makedirs(self.SSH_DIR, mode=0o700, exist_ok=True)
        
        # Remove existing keys if present
        for f in [self.KEY_FILE, self.KEY_FILE_PUB]:
            if os.path.exists(f):
                os.remove(f)
        
        # Generate new key pair
        result = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", self.KEY_FILE, "-N", ""],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            self.log("SSH keys generated successfully")
            return True
        else:
            self.log(f"Failed to generate keys: {result.stderr}", xbmc.LOGERROR)
            return False
    
    def get_public_key(self):
        """Read the public key."""
        try:
            with open(self.KEY_FILE_PUB, 'r') as f:
                return f.read().strip()
        except Exception as e:
            self.log(f"Error reading public key: {e}", xbmc.LOGERROR)
            return None
    
    def check_port(self, ip, port=22, timeout=0.5):
        """Check if a port is open on an IP."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except:
            return False

    def discover_via_avahi(self):
        """Discover CoreELEC devices using Avahi/mDNS (Zeroconf)."""
        self.log("Discovering devices via Avahi/mDNS...")
        devices = []

        try:
            # Use avahi-browse to find SSH services
            # -t = terminate after getting results
            # -r = resolve (get IP addresses)
            # -p = parseable output
            result = subprocess.run(
                ['avahi-browse', '-t', '-r', '-p', '_ssh._tcp'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                self.log(f"avahi-browse failed: {result.stderr}")
                return None  # Return None to indicate fallback needed

            local_ip = self.get_local_ip()
            seen_ips = set()

            # Parse output - format is:
            # =;interface;protocol;name;type;domain;hostname;address;port;txt
            for line in result.stdout.strip().split('\n'):
                if not line or not line.startswith('='):
                    continue

                parts = line.split(';')
                if len(parts) >= 8:
                    hostname = parts[6]  # e.g., "CoreELEC.local"
                    ip = parts[7]

                    # Skip our own device and duplicates
                    if ip == local_ip or ip in seen_ips:
                        continue

                    # Skip IPv6 addresses
                    if ':' in ip:
                        continue

                    seen_ips.add(ip)

                    # Check if it looks like a CoreELEC device by hostname
                    is_coreelec_host = 'coreelec' in hostname.lower()

                    if is_coreelec_host:
                        self.log(f"Found CoreELEC device via Avahi: {hostname} ({ip})")
                        devices.append({
                            'ip': ip,
                            'hostname': hostname.replace('.local', ''),
                            'discovered_via': 'avahi'
                        })
                    else:
                        # Not obviously CoreELEC, but has SSH - we'll verify later
                        self.log(f"Found SSH device via Avahi: {hostname} ({ip})")
                        devices.append({
                            'ip': ip,
                            'hostname': hostname.replace('.local', ''),
                            'discovered_via': 'avahi',
                            'needs_verification': True
                        })

            self.log(f"Avahi discovery found {len(devices)} SSH devices")
            return devices

        except FileNotFoundError:
            self.log("avahi-browse not available")
            return None
        except subprocess.TimeoutExpired:
            self.log("avahi-browse timed out")
            return None
        except Exception as e:
            self.log(f"Avahi discovery error: {e}", xbmc.LOGERROR)
            return None
    
    def is_coreelec(self, ip):
        """Check if a device is a CoreELEC box by testing SSH."""
        try:
            result = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=2", 
                 "-o", "StrictHostKeyChecking=no",
                 f"{self.username}@{ip}", "test -d /storage/.kodi"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False
    
    def run_ssh_with_password(self, ip, password, remote_cmd, timeout=15):
        """Run SSH command with password authentication using SSH_ASKPASS."""
        import tempfile
        import stat

        self.log(f"Running SSH to {ip}: {remote_cmd[:50]}...")

        # Create a temporary script that outputs the password
        askpass_script = None
        try:
            # Create askpass script
            askpass_script = tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False)
            askpass_script.write(f'#!/bin/sh\necho "{password}"\n')
            askpass_script.close()
            os.chmod(askpass_script.name, stat.S_IRWXU)

            env = os.environ.copy()
            env['SSH_ASKPASS'] = askpass_script.name
            env['SSH_ASKPASS_REQUIRE'] = 'force'
            env['DISPLAY'] = ':0'

            cmd = [
                'ssh',
                '-o', 'ConnectTimeout=5',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'PreferredAuthentications=keyboard-interactive,password',
                '-o', 'PubkeyAuthentication=no',
                '-o', 'NumberOfPasswordPrompts=1',
                f'{self.username}@{ip}',
                remote_cmd
            ]

            self.log(f"Running command: {' '.join(cmd[:5])}...")

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                env=env,
                stdin=subprocess.DEVNULL
            )

            output = result.stdout + result.stderr
            self.log(f"SSH output from {ip}: {output}")
            self.log(f"SSH return code: {result.returncode}")

            return output, True

        except subprocess.TimeoutExpired:
            self.log(f"SSH to {ip} timed out")
            return b"", False
        except Exception as e:
            self.log(f"SSH error: {e}")
            return b"", False
        finally:
            # Clean up askpass script
            if askpass_script:
                try:
                    os.unlink(askpass_script.name)
                except:
                    pass

    def is_coreelec_with_password(self, ip, password):
        """Check if device is CoreELEC using password auth."""
        try:
            output, password_sent = self.run_ssh_with_password(
                ip, password,
                "test -d /storage/.kodi && echo COREELEC_OK",
                timeout=15
            )

            if b"COREELEC_OK" in output:
                self.log(f"CoreELEC verified on {ip}")
                return True

            if password_sent and b"permission denied" in output.lower():
                self.log(f"Auth failed on {ip} - wrong password?")

            return False

        except Exception as e:
            self.log(f"Error checking {ip}: {e}", xbmc.LOGERROR)
            return False
    
    def copy_key_to_device(self, ip, password):
        """Copy SSH public key to a remote device."""
        self.log(f"Copying SSH key to {ip}...")

        public_key = self.get_public_key()
        if not public_key:
            return False

        try:
            remote_cmd = f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '{public_key}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && sort -u -o ~/.ssh/authorized_keys ~/.ssh/authorized_keys && echo KEY_COPIED_OK"

            output, password_sent = self.run_ssh_with_password(
                ip, password, remote_cmd, timeout=30
            )

            if b"KEY_COPIED_OK" in output:
                self.log(f"Successfully copied key to {ip}")
                return True

            if password_sent and b"permission denied" in output.lower():
                self.log(f"Auth failed copying key to {ip}")

            self.log(f"Failed to copy key to {ip}", xbmc.LOGERROR)
            return False

        except Exception as e:
            self.log(f"Error copying key to {ip}: {e}", xbmc.LOGERROR)
            return False
    
    def manual_add_device(self, password=None):
        """Manually add a device by IP address."""
        ip = self.dialog.input("Enter Device IP Address", type=xbmcgui.INPUT_ALPHANUM)

        if not ip:
            return None

        # Validate IP format
        parts = ip.split('.')
        if len(parts) != 4:
            self.dialog.notification("Skin Sync", "Invalid IP address", xbmcgui.NOTIFICATION_ERROR)
            return None

        try:
            for part in parts:
                if not 0 <= int(part) <= 255:
                    raise ValueError()
        except ValueError:
            self.dialog.notification("Skin Sync", "Invalid IP address", xbmcgui.NOTIFICATION_ERROR)
            return None

        # Check if SSH port is open
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", f"Checking {ip}...")

        if not self.check_port(ip, 22, timeout=2):
            progress.close()
            self.dialog.ok("Skin Sync", f"Cannot connect to {ip}\n\nMake sure:\n- The device is powered on\n- SSH is enabled\n- The IP address is correct")
            return None

        progress.update(50, f"Verifying CoreELEC on {ip}...")

        # Check if it's CoreELEC
        is_coreelec = False
        key_installed = False

        # Try with key first
        if self.keys_exist() and self.is_coreelec(ip):
            is_coreelec = True
            key_installed = True
        elif password and self.is_coreelec_with_password(ip, password):
            is_coreelec = True
            key_installed = False
        else:
            # Try with password prompt if no password provided
            if not password:
                progress.close()
                password = self.dialog.input(
                    f"Enter SSH password for {ip}",
                    type=xbmcgui.INPUT_ALPHANUM,
                    option=xbmcgui.ALPHANUM_HIDE_INPUT
                )
                if password:
                    progress.create("Skin Sync", f"Verifying CoreELEC on {ip}...")
                    if self.is_coreelec_with_password(ip, password):
                        is_coreelec = True
                        key_installed = False

        progress.close()

        if not is_coreelec:
            self.dialog.ok("Skin Sync", f"Could not verify {ip} as a CoreELEC device.\n\nMake sure the password is correct.")
            return None

        device = {"ip": ip, "key_installed": key_installed}

        # Copy key if needed
        if not key_installed and password:
            if self.copy_key_to_device(ip, password):
                device["key_installed"] = True
                self.add_paired_device(ip)
                self.dialog.notification("Skin Sync", f"Paired with {ip}", xbmcgui.NOTIFICATION_INFO)
            else:
                self.dialog.notification("Skin Sync", f"Added {ip} (key copy failed)", xbmcgui.NOTIFICATION_WARNING)
        else:
            self.add_paired_device(ip)
            self.dialog.notification("Skin Sync", f"Paired with {ip}", xbmcgui.NOTIFICATION_INFO)

        return device

    def scan_network_ip_fallback(self, password=None, progress_callback=None):
        """Fallback: Scan network for CoreELEC devices by IP range."""
        prefix = self.get_network_prefix()
        if not prefix:
            self.log("Could not determine network prefix", xbmc.LOGERROR)
            return []

        local_ip = self.get_local_ip()
        self.log(f"IP scan fallback: Scanning {prefix}.0/24 (local: {local_ip})")

        devices = []
        ips_to_check = [f"{prefix}.{i}" for i in range(1, 255)]

        # First pass: quick port scan
        open_ports = []

        def check_ip(ip):
            if ip != local_ip and self.check_port(ip, 22):
                return ip
            return None

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(check_ip, ip): ip for ip in ips_to_check}
            completed = 0
            for future in as_completed(futures):
                completed += 1
                if progress_callback:
                    progress_callback(int(completed / len(ips_to_check) * 50), "Scanning network...")
                result = future.result()
                if result:
                    open_ports.append(result)

        self.log(f"Found {len(open_ports)} devices with SSH open")

        # Second pass: check if they're CoreELEC
        for i, ip in enumerate(open_ports):
            if progress_callback:
                progress_callback(50 + int((i + 1) / len(open_ports) * 50), f"Checking {ip}...")

            # Try without password first (if keys are set up)
            if self.keys_exist() and self.is_coreelec(ip):
                devices.append({"ip": ip, "key_installed": True})
                self.add_paired_device(ip)
            elif password and self.is_coreelec_with_password(ip, password):
                devices.append({"ip": ip, "key_installed": False})

        return devices

    def scan_network(self, password=None, progress_callback=None):
        """Scan network for CoreELEC devices using Avahi (with IP scan fallback)."""
        devices = []
        local_ip = self.get_local_ip()

        # Try Avahi/mDNS discovery first (fast)
        if progress_callback:
            progress_callback(5, "Discovering devices via Avahi...")

        avahi_devices = self.discover_via_avahi()

        if avahi_devices is not None and len(avahi_devices) > 0:
            # Avahi found devices - verify they're CoreELEC
            self.log(f"Avahi found {len(avahi_devices)} devices, verifying...")

            for i, device in enumerate(avahi_devices):
                ip = device['ip']
                hostname = device.get('hostname', ip)

                if progress_callback:
                    progress_callback(10 + int((i + 1) / len(avahi_devices) * 40), f"Checking {hostname}...")

                # Skip verification for devices with CoreELEC in hostname
                if not device.get('needs_verification'):
                    # Trust the hostname, just check if keys work
                    if self.keys_exist() and self.is_coreelec(ip):
                        devices.append({"ip": ip, "hostname": hostname, "key_installed": True})
                        self.add_paired_device(ip, hostname)
                    elif password and self.is_coreelec_with_password(ip, password):
                        devices.append({"ip": ip, "hostname": hostname, "key_installed": False})
                    else:
                        # Can't verify but hostname says CoreELEC - add anyway
                        devices.append({"ip": ip, "hostname": hostname, "key_installed": False})
                else:
                    # Verify it's actually CoreELEC
                    if self.keys_exist() and self.is_coreelec(ip):
                        devices.append({"ip": ip, "hostname": hostname, "key_installed": True})
                        self.add_paired_device(ip, hostname)
                    elif password and self.is_coreelec_with_password(ip, password):
                        devices.append({"ip": ip, "hostname": hostname, "key_installed": False})

        elif avahi_devices is None:
            # Avahi not available or failed - fall back to IP scanning
            self.log("Avahi not available, falling back to IP scan...")
            if progress_callback:
                progress_callback(10, "Avahi unavailable, scanning by IP...")
            devices = self.scan_network_ip_fallback(password, progress_callback)

        # Include paired devices that weren't found in scan
        if progress_callback:
            progress_callback(60, "Checking paired devices...")

        found_ips = {d['ip'] for d in devices}
        paired = self.load_paired_devices()

        for i, pd in enumerate(paired):
            ip = pd.get('ip')
            if ip not in found_ips:
                if progress_callback:
                    progress_callback(60 + int((i + 1) / max(len(paired), 1) * 30), f"Checking {ip}...")

                # Check if this paired device is reachable
                if self.keys_exist() and self.is_coreelec(ip):
                    devices.append({
                        "ip": ip,
                        "hostname": pd.get('name', ip),
                        "key_installed": True,
                        "paired": True
                    })
                    self.log(f"Added paired device {ip} from saved list")

        if progress_callback:
            progress_callback(100, "Done")

        self.log(f"Found {len(devices)} CoreELEC devices total")
        return devices

    def create_backup(self):
        """Create a backup of current skin settings, widgets, and keymaps."""
        skin_name = self.get_current_skin()
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        backup_path = os.path.join(self.backup_dir, f"{skin_name}_{timestamp}")

        self.log(f"Creating backup at {backup_path}")

        try:
            os.makedirs(backup_path, exist_ok=True)

            # Backup skin settings
            skin_path = self.get_skin_path()
            if os.path.exists(skin_path):
                skin_backup = os.path.join(backup_path, 'skin_settings')
                os.makedirs(skin_backup, exist_ok=True)
                for item in os.listdir(skin_path):
                    src = os.path.join(skin_path, item)
                    dst = os.path.join(skin_backup, item)
                    if os.path.isfile(src):
                        import shutil
                        shutil.copy2(src, dst)

            # Backup skinvariables nodes
            skinvariables_nodes = os.path.join(self.KODI_ADDON_DATA, "script.skinvariables", "nodes", skin_name)
            if os.path.exists(skinvariables_nodes):
                widgets_backup = os.path.join(backup_path, 'widgets')
                os.makedirs(widgets_backup, exist_ok=True)
                for item in os.listdir(skinvariables_nodes):
                    src = os.path.join(skinvariables_nodes, item)
                    dst = os.path.join(widgets_backup, item)
                    if os.path.isfile(src):
                        import shutil
                        shutil.copy2(src, dst)

            # Backup keymaps
            if os.path.exists(self.KEYMAPS_PATH):
                keymaps_backup = os.path.join(backup_path, 'keymaps')
                os.makedirs(keymaps_backup, exist_ok=True)
                for item in os.listdir(self.KEYMAPS_PATH):
                    src = os.path.join(self.KEYMAPS_PATH, item)
                    dst = os.path.join(keymaps_backup, item)
                    if os.path.isfile(src):
                        import shutil
                        shutil.copy2(src, dst)

            self.log(f"Backup created successfully at {backup_path}")
            return backup_path

        except Exception as e:
            self.log(f"Backup failed: {e}", xbmc.LOGERROR)
            return None

    def get_sync_options(self):
        """Show dialog to select what to sync."""
        options = [
            ("Skin Settings", "settings"),
            ("Widget Configurations", "widgets"),
            ("Keymaps", "keymaps"),
        ]

        # Use multiselect
        selected = self.dialog.multiselect(
            "Select what to sync",
            [o[0] for o in options],
            preselect=[0, 1]  # Default: settings and widgets
        )

        if selected is None:
            return None

        return [options[i][1] for i in selected]

    def sync_skin_to_device(self, target_ip, sync_options=None, do_backup=True):
        """Sync current skin settings to target device."""
        if sync_options is None:
            sync_options = ["settings", "widgets"]  # Default options

        skin_path = self.get_skin_path()
        skin_name = self.get_current_skin()

        if "settings" in sync_options and not os.path.exists(skin_path):
            self.dialog.notification("Skin Sync", "No skin settings to sync", xbmcgui.NOTIFICATION_WARNING)
            return False

        self.log(f"Syncing {skin_name} to {target_ip} (options: {sync_options})")

        # Paths for skin settings
        remote_skin_path = f"{self.KODI_ADDON_DATA}/{skin_name}"

        # Paths for skinvariables (widget configurations)
        skinvariables_path = os.path.join(self.KODI_ADDON_DATA, "script.skinvariables")
        skinvariables_nodes_path = os.path.join(skinvariables_path, "nodes", skin_name)
        skinvariables_viewtypes = os.path.join(skinvariables_path, f"{skin_name}-viewtypes.json")

        try:
            # Stop Kodi on target first (prevents it from overwriting settings)
            self.log(f"Stopping Kodi on {target_ip}")
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 f"{self.username}@{target_ip}", "systemctl stop kodi"],
                capture_output=True,
                timeout=60  # Kodi can take a while to stop, especially if busy
            )
            time.sleep(2)

            # Ensure target directories exist
            mkdir_cmd = f"mkdir -p {remote_skin_path}"
            if "widgets" in sync_options:
                mkdir_cmd += f" {self.KODI_ADDON_DATA}/script.skinvariables/nodes/{skin_name}"
            if "keymaps" in sync_options:
                mkdir_cmd += f" {self.KEYMAPS_PATH}"

            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 f"{self.username}@{target_ip}", mkdir_cmd],
                capture_output=True,
                timeout=10
            )

            # Sync skin settings
            if "settings" in sync_options:
                self.log(f"Copying skin settings to {target_ip}")
                result = subprocess.run(
                    ["scp", "-r", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                     f"{skin_path}/.", f"{self.username}@{target_ip}:{remote_skin_path}/"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    self.log(f"SCP skin settings failed: {result.stderr}", xbmc.LOGERROR)

            # Sync skinvariables nodes (widget configurations) if they exist
            if "widgets" in sync_options:
                if os.path.exists(skinvariables_nodes_path):
                    self.log(f"Copying widget configurations to {target_ip}")
                    result = subprocess.run(
                        ["scp", "-r", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                         f"{skinvariables_nodes_path}/.",
                         f"{self.username}@{target_ip}:{self.KODI_ADDON_DATA}/script.skinvariables/nodes/{skin_name}/"],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode != 0:
                        self.log(f"SCP widget configs failed: {result.stderr}", xbmc.LOGERROR)

                # Sync viewtypes.json if it exists
                if os.path.exists(skinvariables_viewtypes):
                    self.log(f"Copying viewtypes to {target_ip}")
                    subprocess.run(
                        ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                         skinvariables_viewtypes,
                         f"{self.username}@{target_ip}:{self.KODI_ADDON_DATA}/script.skinvariables/"],
                        capture_output=True,
                        timeout=30
                    )

            # Sync keymaps
            if "keymaps" in sync_options:
                if os.path.exists(self.KEYMAPS_PATH) and os.listdir(self.KEYMAPS_PATH):
                    self.log(f"Copying keymaps to {target_ip}")
                    result = subprocess.run(
                        ["scp", "-r", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                         f"{self.KEYMAPS_PATH}/.",
                         f"{self.username}@{target_ip}:{self.KEYMAPS_PATH}/"],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode != 0:
                        self.log(f"SCP keymaps failed: {result.stderr}", xbmc.LOGERROR)

            # Start Kodi on target
            self.log(f"Starting Kodi on {target_ip}")
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 f"{self.username}@{target_ip}", "systemctl start kodi"],
                capture_output=True,
                timeout=10
            )

            return True

        except subprocess.TimeoutExpired:
            self.log("Sync timed out", xbmc.LOGERROR)
            return False
        except Exception as e:
            self.log(f"Sync error: {e}", xbmc.LOGERROR)
            return False

    def pull_from_device(self, source_ip, sync_options=None, do_backup=True):
        """Pull skin settings FROM another device to this one."""
        if sync_options is None:
            sync_options = ["settings", "widgets"]

        skin_name = self.get_current_skin()
        self.log(f"Pulling {skin_name} from {source_ip} (options: {sync_options})")

        # Create backup before pulling
        if do_backup:
            self.log("Creating backup before pull...")
            self.create_backup()

        # Paths
        skin_path = self.get_skin_path()
        skinvariables_path = os.path.join(self.KODI_ADDON_DATA, "script.skinvariables")
        skinvariables_nodes_path = os.path.join(skinvariables_path, "nodes", skin_name)

        try:
            # Ensure local directories exist
            os.makedirs(skin_path, exist_ok=True)
            os.makedirs(skinvariables_nodes_path, exist_ok=True)
            os.makedirs(self.KEYMAPS_PATH, exist_ok=True)

            # Pull skin settings
            if "settings" in sync_options:
                self.log(f"Pulling skin settings from {source_ip}")
                result = subprocess.run(
                    ["scp", "-r", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                     f"{self.username}@{source_ip}:{self.KODI_ADDON_DATA}/{skin_name}/.",
                     f"{skin_path}/"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    self.log(f"SCP skin settings failed: {result.stderr}", xbmc.LOGERROR)

            # Pull widget configurations
            if "widgets" in sync_options:
                self.log(f"Pulling widget configurations from {source_ip}")
                result = subprocess.run(
                    ["scp", "-r", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                     f"{self.username}@{source_ip}:{self.KODI_ADDON_DATA}/script.skinvariables/nodes/{skin_name}/.",
                     f"{skinvariables_nodes_path}/"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    self.log(f"SCP widget configs failed: {result.stderr}", xbmc.LOGERROR)

                # Pull viewtypes.json
                viewtypes_file = f"{skin_name}-viewtypes.json"
                subprocess.run(
                    ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                     f"{self.username}@{source_ip}:{self.KODI_ADDON_DATA}/script.skinvariables/{viewtypes_file}",
                     f"{skinvariables_path}/"],
                    capture_output=True,
                    timeout=30
                )

            # Pull keymaps
            if "keymaps" in sync_options:
                self.log(f"Pulling keymaps from {source_ip}")
                result = subprocess.run(
                    ["scp", "-r", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                     f"{self.username}@{source_ip}:{self.KEYMAPS_PATH}/.",
                     f"{self.KEYMAPS_PATH}/"],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    self.log(f"SCP keymaps failed: {result.stderr}", xbmc.LOGERROR)

            return True

        except subprocess.TimeoutExpired:
            self.log("Pull timed out", xbmc.LOGERROR)
            return False
        except Exception as e:
            self.log(f"Pull error: {e}", xbmc.LOGERROR)
            return False

    def sync_to_all_devices(self, sync_options=None, do_backup=True):
        """Sync to all paired devices."""
        devices = self.load_paired_devices()
        if not devices:
            self.dialog.ok("Skin Sync", "No paired devices found.")
            return False

        # Verify which devices are reachable
        reachable = []
        for d in devices:
            ip = d.get('ip')
            if self.keys_exist() and self.is_coreelec(ip):
                reachable.append(d)

        if not reachable:
            self.dialog.ok("Skin Sync", "No paired devices are currently reachable.")
            return False

        # Confirm
        device_names = [d.get('ip') for d in reachable]
        if not self.dialog.yesno(
            "Sync to All Devices",
            f"Push settings to {len(reachable)} device(s)?\n\n" +
            "\n".join(device_names) +
            "\n\nKodi will restart on each device."
        ):
            return False

        # Sync to each device
        success_count = 0
        for d in reachable:
            ip = d.get('ip')
            self.log(f"Syncing to {ip}...")
            if self.sync_skin_to_device(ip, sync_options, do_backup=False):
                success_count += 1
            else:
                self.log(f"Failed to sync to {ip}", xbmc.LOGERROR)

        self.dialog.notification(
            "Skin Sync",
            f"Synced to {success_count}/{len(reachable)} devices",
            xbmcgui.NOTIFICATION_INFO
        )
        return success_count > 0
    
    def run_setup(self):
        """Run first-time setup wizard."""
        self.dialog.ok(
            "Skin Sync - Setup",
            "SSH keys need to be set up for secure communication between devices.\n\n"
            "You'll be asked for your CoreELEC password (default: coreelec). "
            "This is only needed once."
        )
        
        # Get password
        password = self.dialog.input(
            "Enter CoreELEC SSH Password",
            type=xbmcgui.INPUT_ALPHANUM,
            option=xbmcgui.ALPHANUM_HIDE_INPUT
        )
        
        if not password:
            self.dialog.notification("Skin Sync", "Setup cancelled", xbmcgui.NOTIFICATION_WARNING)
            return False
        
        # Generate keys
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync Setup", "Generating SSH keys...")
        
        if not self.generate_keys():
            progress.close()
            self.dialog.ok("Skin Sync", "Failed to generate SSH keys")
            return False
        
        # Scan for devices
        progress.update(10, "Scanning network for CoreELEC devices...")
        
        def update_progress(pct, msg):
            progress.update(10 + int(pct * 0.8), msg)
        
        devices = self.scan_network(password=password, progress_callback=update_progress)
        progress.close()

        if not devices:
            # Offer manual entry
            if self.dialog.yesno(
                "No Devices Found",
                "No CoreELEC devices were found automatically.\n\n"
                "Would you like to add a device manually by IP address?"
            ):
                device = self.manual_add_device(password)
                if device:
                    devices.append(device)

        if not devices:
            self.dialog.ok("Skin Sync", "No devices configured. Setup incomplete.")
            return False

        # Copy keys to devices that don't have them yet
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync Setup", "Installing SSH keys on devices...")
        
        success_count = 0
        for device in devices:
            if not device.get("key_installed"):
                if self.copy_key_to_device(device["ip"], password):
                    success_count += 1
            else:
                success_count += 1
        
        progress.close()
        
        self.dialog.ok(
            "Skin Sync - Setup Complete",
            f"SSH keys installed on {success_count} device(s).\n\n"
            "You can now sync your skin settings!"
        )
        
        return True
    
    def reset_keys(self):
        """Reset SSH keys and start fresh."""
        if self.dialog.yesno("Reset SSH Keys", "This will remove existing SSH keys. You'll need to run setup again.\n\nContinue?"):
            for f in [self.KEY_FILE, self.KEY_FILE_PUB]:
                if os.path.exists(f):
                    os.remove(f)
            self.dialog.notification("Skin Sync", "SSH keys removed", xbmcgui.NOTIFICATION_INFO)
    
    def run(self):
        """Main entry point."""
        # Check if setup is needed
        if not self.keys_exist():
            if not self.run_setup():
                return

        # Show main menu
        skin_name = self.get_current_skin()
        menu_options = [
            f"Push to device...",
            f"Push to ALL paired devices",
            f"Pull from device...",
            "Create backup",
            "Settings"
        ]

        choice = self.dialog.select(f"Skin Sync - {skin_name}", menu_options)

        if choice < 0:
            return

        if choice == 0:
            # Push to device
            self.run_push_to_device()
        elif choice == 1:
            # Push to all devices
            self.run_push_to_all()
        elif choice == 2:
            # Pull from device
            self.run_pull_from_device()
        elif choice == 3:
            # Create backup
            self.run_create_backup()
        elif choice == 4:
            # Settings submenu
            self.run_settings_menu()

    def run_push_to_device(self):
        """Push settings to a single device."""
        # Get sync options
        sync_options = self.get_sync_options()
        if sync_options is None:
            return

        # Scan for devices
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", "Scanning for devices...")

        def update_progress(pct, msg):
            progress.update(pct, msg)

        devices = self.scan_network(progress_callback=update_progress)
        progress.close()

        if not devices:
            choice = self.dialog.select(
                "No Devices Found",
                ["Add device manually by IP", "Run setup again", "Cancel"]
            )
            if choice == 0:
                device = self.manual_add_device()
                if device:
                    devices.append(device)
            elif choice == 1:
                self.run_setup()
                return
            else:
                return

        if not devices:
            return

        # Show device selection
        skin_name = self.get_current_skin()
        device_list = []
        for d in devices:
            if d.get('hostname') and d['hostname'] != d['ip']:
                device_list.append(f"{d['hostname']} ({d['ip']})")
            else:
                device_list.append(d['ip'])
        device_list.append("+ Add device manually...")

        selected = self.dialog.select(f"Push '{skin_name}' to:", device_list)

        if selected < 0:
            return

        if selected == len(devices):
            device = self.manual_add_device()
            if device:
                devices.append(device)
                target = device
            else:
                return
        else:
            target = devices[selected]

        # Confirm
        sync_items = ", ".join(sync_options)
        if not self.dialog.yesno(
            "Confirm Sync",
            f"Push to {target['ip']}?\n\n"
            f"Syncing: {sync_items}\n\n"
            "Kodi will restart on the target device."
        ):
            return

        # Do the sync
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", f"Syncing to {target['ip']}...")

        success = self.sync_skin_to_device(target['ip'], sync_options)

        progress.close()

        if success:
            self.dialog.notification("Skin Sync", "Sync complete!", xbmcgui.NOTIFICATION_INFO)
        else:
            self.dialog.ok("Skin Sync", "Sync failed. Check the log for details.")

    def run_push_to_all(self):
        """Push settings to all paired devices."""
        # Get sync options
        sync_options = self.get_sync_options()
        if sync_options is None:
            return

        # Check for paired devices
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", "Checking paired devices...")

        devices = self.load_paired_devices()
        if not devices:
            progress.close()
            self.dialog.ok("Skin Sync", "No paired devices. Add devices first using 'Push to device'.")
            return

        # Check which are reachable
        reachable = []
        for i, d in enumerate(devices):
            progress.update(int((i + 1) / len(devices) * 100), f"Checking {d.get('ip')}...")
            ip = d.get('ip')
            if self.keys_exist() and self.is_coreelec(ip):
                reachable.append(d)

        progress.close()

        if not reachable:
            self.dialog.ok("Skin Sync", "No paired devices are currently reachable.")
            return

        # Confirm
        sync_items = ", ".join(sync_options)
        device_list = "\n".join([d.get('ip') for d in reachable])
        if not self.dialog.yesno(
            "Push to All Devices",
            f"Push to {len(reachable)} device(s)?\n\n"
            f"{device_list}\n\n"
            f"Syncing: {sync_items}\n\n"
            "Kodi will restart on each device."
        ):
            return

        # Sync to each device
        progress = xbmcgui.DialogProgress()
        success_count = 0

        for i, d in enumerate(reachable):
            ip = d.get('ip')
            progress.create("Skin Sync", f"Syncing to {ip} ({i+1}/{len(reachable)})...")
            if self.sync_skin_to_device(ip, sync_options, do_backup=False):
                success_count += 1
            progress.close()

        self.dialog.notification(
            "Skin Sync",
            f"Synced to {success_count}/{len(reachable)} devices",
            xbmcgui.NOTIFICATION_INFO
        )

    def run_pull_from_device(self):
        """Pull settings from another device."""
        # Get sync options
        sync_options = self.get_sync_options()
        if sync_options is None:
            return

        # Scan for devices
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", "Scanning for devices...")

        def update_progress(pct, msg):
            progress.update(pct, msg)

        devices = self.scan_network(progress_callback=update_progress)
        progress.close()

        if not devices:
            choice = self.dialog.select(
                "No Devices Found",
                ["Add device manually by IP", "Cancel"]
            )
            if choice == 0:
                device = self.manual_add_device()
                if device:
                    devices.append(device)
            else:
                return

        if not devices:
            return

        # Show device selection
        skin_name = self.get_current_skin()
        device_list = []
        for d in devices:
            if d.get('hostname') and d['hostname'] != d['ip']:
                device_list.append(f"{d['hostname']} ({d['ip']})")
            else:
                device_list.append(d['ip'])

        selected = self.dialog.select(f"Pull '{skin_name}' from:", device_list)

        if selected < 0:
            return

        source = devices[selected]

        # Confirm
        sync_items = ", ".join(sync_options)
        if not self.dialog.yesno(
            "Confirm Pull",
            f"Pull from {source['ip']}?\n\n"
            f"Syncing: {sync_items}\n\n"
            "This will overwrite your current settings.\n"
            "A backup will be created first."
        ):
            return

        # Create backup and pull
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", "Creating backup...")

        backup_path = self.create_backup()

        progress.update(30, f"Pulling from {source['ip']}...")

        success = self.pull_from_device(source['ip'], sync_options, do_backup=False)

        progress.close()

        if success:
            # Prompt to reload skin
            if self.dialog.yesno(
                "Pull Complete",
                "Settings pulled successfully.\n\n"
                "Reload skin now to apply changes?"
            ):
                xbmc.executebuiltin("ReloadSkin()")
        else:
            self.dialog.ok("Skin Sync", "Pull failed. Check the log for details.")

    def run_create_backup(self):
        """Create a manual backup."""
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", "Creating backup...")

        backup_path = self.create_backup()

        progress.close()

        if backup_path:
            self.dialog.ok("Backup Created", f"Backup saved to:\n\n{backup_path}")
        else:
            self.dialog.ok("Backup Failed", "Failed to create backup. Check the log for details.")

    def run_settings_menu(self):
        """Show settings submenu."""
        options = [
            "View paired devices",
            "Remove paired device",
            "Reset SSH keys",
            "Run setup again"
        ]

        choice = self.dialog.select("Settings", options)

        if choice == 0:
            self.view_paired_devices()
        elif choice == 1:
            self.remove_paired_device_dialog()
        elif choice == 2:
            self.reset_keys()
        elif choice == 3:
            self.run_setup()
