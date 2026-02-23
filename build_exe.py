#!/usr/bin/env python3
"""
Build standalone executable for ADMX Manager
Requires: pip install pyinstaller
"""

import subprocess
import sys
import os

def build():
    print("Building ADMX Manager standalone executable...")
    print()
    
    # Check for PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found. Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Build command
    cmd = [
        "pyinstaller",
        "--onefile",
        "--windowed",
        "--name", "ADMXManager",
        "--clean",
        "--noconfirm",
        "admx_manager.py"
    ]
    
    print(f"Running: {' '.join(cmd)}")
    print()
    
    result = subprocess.call(cmd)
    
    if result == 0:
        print()
        print("=" * 60)
        print("Build successful!")
        print("=" * 60)
        print()
        print("Executable location: dist/ADMXManager.exe")
        print()
        print("To distribute:")
        print("  1. Copy dist/ADMXManager.exe to target machine")
        print("  2. No Python installation needed on target")
        print()
    else:
        print()
        print("Build failed. Check error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    build()
