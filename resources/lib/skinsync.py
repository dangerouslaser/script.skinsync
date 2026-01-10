#!/usr/bin/env python3
"""
SkinSync - Main library for skin synchronization
"""

import xbmc
import xbmcgui
import xbmcaddon
import subprocess
import socket
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


class SkinSync:
    """Main class for skin synchronization between CoreELEC devices."""
    
    SSH_DIR = "/storage/.ssh"
    KEY_FILE = "/storage/.ssh/id_ed25519"
    KEY_FILE_PUB = "/storage/.ssh/id_ed25519.pub"
    KODI_ADDON_DATA = "/storage/.kodi/userdata/addon_data"
    
    def __init__(self, addon):
        self.addon = addon
        self.username = addon.getSetting('ssh_username') or 'root'
        self.network_prefix = addon.getSetting('network_prefix') or None
        self.dialog = xbmcgui.Dialog()
        self.progress = None
        
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
                self.dialog.notification("Skin Sync", f"Added {ip}", xbmcgui.NOTIFICATION_INFO)
            else:
                self.dialog.notification("Skin Sync", f"Added {ip} (key copy failed)", xbmcgui.NOTIFICATION_WARNING)
        else:
            self.dialog.notification("Skin Sync", f"Added {ip}", xbmcgui.NOTIFICATION_INFO)

        return device

    def scan_network(self, password=None, progress_callback=None):
        """Scan network for CoreELEC devices."""
        prefix = self.get_network_prefix()
        if not prefix:
            self.log("Could not determine network prefix", xbmc.LOGERROR)
            return []

        local_ip = self.get_local_ip()
        self.log(f"Scanning network {prefix}.0/24 (local: {local_ip})")
        
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
            elif password and self.is_coreelec_with_password(ip, password):
                devices.append({"ip": ip, "key_installed": False})
        
        self.log(f"Found {len(devices)} CoreELEC devices")
        return devices
    
    def sync_skin_to_device(self, target_ip):
        """Sync current skin settings to target device."""
        skin_path = self.get_skin_path()
        skin_name = self.get_current_skin()
        
        if not os.path.exists(skin_path):
            self.dialog.notification("Skin Sync", "No skin settings to sync", xbmcgui.NOTIFICATION_WARNING)
            return False
        
        self.log(f"Syncing {skin_name} to {target_ip}")
        
        # Create target directory
        remote_path = f"{self.KODI_ADDON_DATA}/{skin_name}"
        
        try:
            # Ensure target directory exists
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 f"{self.username}@{target_ip}", f"mkdir -p {remote_path}"],
                capture_output=True,
                timeout=10
            )
            
            # Sync files using scp
            result = subprocess.run(
                ["scp", "-r", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 f"{skin_path}/.", f"{self.username}@{target_ip}:{remote_path}/"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                self.log(f"SCP failed: {result.stderr}", xbmc.LOGERROR)
                return False
            
            # Restart Kodi on target
            self.log(f"Restarting Kodi on {target_ip}")
            subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 f"{self.username}@{target_ip}", "systemctl restart kodi"],
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
        
        # Scan for devices
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", "Scanning for devices...")
        
        def update_progress(pct, msg):
            progress.update(pct, msg)
        
        devices = self.scan_network(progress_callback=update_progress)
        progress.close()
        
        if not devices:
            # Offer manual entry or setup
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

        # Show device selection with option to add more
        skin_name = self.get_current_skin()
        device_list = [f"{d['ip']}" for d in devices]
        device_list.append("+ Add device manually...")

        selected = self.dialog.select(
            f"Push '{skin_name}' to:",
            device_list
        )

        if selected < 0:
            return

        # Handle "Add device manually" option
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
        if not self.dialog.yesno(
            "Confirm Sync",
            f"Push skin settings to {target['ip']}?\n\n"
            "Kodi will restart on the target device."
        ):
            return
        
        # Do the sync
        progress = xbmcgui.DialogProgress()
        progress.create("Skin Sync", f"Syncing to {target['ip']}...")
        
        success = self.sync_skin_to_device(target['ip'])
        
        progress.close()
        
        if success:
            self.dialog.notification("Skin Sync", "Sync complete!", xbmcgui.NOTIFICATION_INFO)
        else:
            self.dialog.ok("Skin Sync", "Sync failed. Check the log for details.")
