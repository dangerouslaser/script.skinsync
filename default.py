#!/usr/bin/env python3
"""
Skin Sync - Sync Kodi skin settings between CoreELEC devices
"""

import xbmc
import xbmcgui
import xbmcaddon
import sys
import os

# Add lib folder to path
ADDON = xbmcaddon.Addon()
ADDON_PATH = ADDON.getAddonInfo('path')
LIB_PATH = os.path.join(ADDON_PATH, 'resources', 'lib')
sys.path.insert(0, LIB_PATH)

from skinsync import SkinSync


def main():
    # Check for command line arguments
    args = sys.argv[1] if len(sys.argv) > 1 else None
    
    sync = SkinSync(ADDON)
    
    if args == "reset_keys":
        sync.reset_keys()
    else:
        sync.run()


if __name__ == "__main__":
    main()
