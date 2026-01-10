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
    
    def is_coreelec_with_password(self, ip, password):
        """Check if device is CoreELEC using password auth."""
        try:
            # Use Python's pty to handle password prompt
            import pty
            import select
            
            cmd = f"ssh -o ConnectTimeout=3 -o StrictHostKeyChecking=no {self.username}@{ip} 'test -d /storage/.kodi && echo COREELEC_OK'"
            
            master, slave = pty.openpty()
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True
            )
            os.close(slave)
            
            output = b""
            password_sent = False
            start_time = time.time()
            
            while time.time() - start_time < 10:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        data = os.read(master, 1024)
                        if not data:
                            break
                        output += data
                        
                        if b"password:" in output.lower() and not password_sent:
                            os.write(master, (password + "\n").encode())
                            password_sent = True
                        
                        if b"COREELEC_OK" in output:
                            process.terminate()
                            os.close(master)
                            return True
                            
                    except OSError:
                        break
                
                if process.poll() is not None:
                    break
            
            try:
                process.terminate()
                os.close(master)
            except:
                pass
            
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
            import pty
            import select
            
            # Command to append key to authorized_keys
            cmd = f"ssh -o StrictHostKeyChecking=no {self.username}@{ip} 'mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo \"{public_key}\" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && sort -u -o ~/.ssh/authorized_keys ~/.ssh/authorized_keys'"
            
            master, slave = pty.openpty()
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True
            )
            os.close(slave)
            
            output = b""
            password_sent = False
            start_time = time.time()
            
            while time.time() - start_time < 30:
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        data = os.read(master, 1024)
                        if not data:
                            break
                        output += data
                        
                        if b"password:" in output.lower() and not password_sent:
                            os.write(master, (password + "\n").encode())
                            password_sent = True
                            
                    except OSError:
                        break
                
                if process.poll() is not None:
                    break
            
            try:
                process.wait(timeout=5)
                os.close(master)
            except:
                process.terminate()
            
            success = process.returncode == 0
            if success:
                self.log(f"Successfully copied key to {ip}")
            else:
                self.log(f"Failed to copy key to {ip}", xbmc.LOGERROR)
            
            return success
            
        except Exception as e:
            self.log(f"Error copying key to {ip}: {e}", xbmc.LOGERROR)
            return False
    
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
        
        if not devices:
            progress.close()
            self.dialog.ok("Skin Sync", "No other CoreELEC devices found on the network")
            return False
        
        # Copy keys to devices
        progress.update(90, "Installing SSH keys on devices...")
        
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
            # Maybe keys aren't set up on some devices, offer setup again
            if self.dialog.yesno(
                "No Devices Found",
                "No CoreELEC devices found with SSH access.\n\n"
                "Would you like to run setup again?"
            ):
                self.run_setup()
            return
        
        # Show device selection
        skin_name = self.get_current_skin()
        device_list = [f"{d['ip']}" for d in devices]
        
        selected = self.dialog.select(
            f"Push '{skin_name}' to:",
            device_list
        )
        
        if selected < 0:
            return
        
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
