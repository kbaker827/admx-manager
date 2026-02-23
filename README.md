# ADMX Manager

**A Windows GUI tool to browse, download, and import ADMX/ADML administrative templates for Group Policy (Active Directory) or Microsoft Intune.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()

---

## 🎯 What is ADMX Manager?

ADMX (Administrative Template) files define the policies available in Group Policy. Managing these files across multiple products (Windows, Office, Edge, Chrome, etc.) is tedious. **ADMX Manager simplifies this process** by providing a unified interface to:

- Browse available ADMX templates from multiple vendors
- Download selected templates with one click
- Import templates into Microsoft Intune
- Install templates to Active Directory SYSVOL
- Install templates locally for Local Group Policy

---

## ✨ Features

### 📋 Built-in Template Catalog
Pre-configured sources for popular products:

| Product | Publisher | Category |
|---------|-----------|----------|
| Windows 11 2024 | Microsoft | Operating System |
| Windows 10 22H2 | Microsoft | Operating System |
| Microsoft Office 2021/365 | Microsoft | Productivity |
| Microsoft Edge | Microsoft | Browser |
| Google Chrome | Google | Browser |
| Mozilla Firefox | Mozilla | Browser |
| Adobe Acrobat Reader | Adobe | Productivity |
| Citrix Workspace | Citrix | Virtualization |
| VMware Horizon | VMware | Virtualization |
| Zoom | Zoom | Communication |

### 🎨 User-Friendly Interface
- **Search and filter** templates by name, publisher, or category
- **Select multiple** templates for batch download
- **Detailed preview** of each template
- **Progress tracking** for downloads
- **Activity logging** with export capability

### 📥 Download Options
- **Automatic extraction** of ZIP archives
- **Organized storage** by publisher/category
- **Custom download locations**
- **Add custom sources** for internal/proprietary ADMX files

### 📤 Import Destinations

#### Microsoft Intune
Import ADMX templates for use in Windows configuration profiles:
1. Download templates
2. Navigate to Endpoint Manager
3. Import ADMX files
4. Create custom configuration profiles

#### Active Directory (SYSVOL)
Copy templates to your domain's Group Policy central store:
```
\\your-domain\SYSVOL\your-domain\Policies\PolicyDefinitions
```

#### Local Computer
Install templates locally for use with `gpedit.msc` (Local Group Policy Editor).

---

## 🚀 Getting Started

### Option 1: Run from Python (Easiest)

1. **Install Python 3.7+** on Windows
   - Download from [python.org](https://python.org)
   - Check "Add Python to PATH" during installation

2. **Download this repository**
   ```batch
   git clone https://github.com/kbaker827/admx-manager.git
   cd admx-manager
   ```

3. **Run the application**
   ```batch
   run_admx_manager.bat
   ```
   Or directly:
   ```batch
   python admx_manager.py
   ```

### Option 2: Build Standalone EXE

Build a standalone executable that doesn't require Python on the target machine:

```batch
# Install PyInstaller
pip install pyinstaller

# Build executable
python build_exe.py
```

The executable will be created at `dist/ADMXManager.exe`.

---

## 📖 Usage Guide

### Downloading Templates

1. **Select templates** from the list (check the checkbox or use "Select All")
2. **Choose download location** (default: `%USERPROFILE%\ADMX`)
3. **Click "Download Selected"**
4. Templates are automatically extracted and organized

### Importing to Intune

1. **Download** desired templates
2. Click **"Import to Intune"** button for instructions
3. Navigate to [Microsoft Endpoint Manager](https://endpoint.microsoft.com)
4. Go to **Devices > Configuration profiles > Import ADMX**
5. Upload the `.admx` and corresponding `.adml` files

### Installing to Active Directory

1. **Download** templates
2. Enter your **SYSVOL path**:
   ```
   \\your-domain.com\SYSVOL\your-domain.com\Policies\PolicyDefinitions
   ```
3. Click **"Import to SYSVOL"**
4. Templates are copied with proper language folder structure

### Installing Locally

1. **Download** templates
2. Click **"Install Locally"**
3. Templates are copied to:
   ```
   C:\Windows\PolicyDefinitions
   ```
4. Open `gpedit.msc` to use the new templates

### Adding Custom Sources

Have proprietary or internal ADMX files?

1. Click **"Add Custom Source"**
2. Enter name, URL, publisher, and category
3. Save and it appears in the list

---

## 📁 ADMX File Structure

After downloading, files are organized as:

```
ADMX/
├── Microsoft/
│   ├── Operating System/
│   │   ├── windows11.admx
│   │   └── en-US/
│   │       └── windows11.adml
│   └── Browser/
│       ├── edge.admx
│       └── en-US/
│           └── edge.adml
├── Google/
│   └── Browser/
│       ├── chrome.admx
│       └── en-US/
│           └── chrome.adml
└── ...
```

---

## 🔧 System Requirements

- **OS:** Windows 10/11 (primary target), works on macOS/Linux with limitations
- **Python:** 3.7+ (if running from source)
- **Network:** Internet connection for downloading templates
- **Permissions:** 
  - Administrator rights for local installation
  - Domain admin rights for SYSVOL import
  - Intune admin rights for cloud import

---

## 🛠️ Technical Details

### Architecture
- **GUI Framework:** Python tkinter (standard library)
- **HTTP Client:** urllib (standard library)
- **File Operations:** shutil, pathlib (standard library)
- **Threading:** threading module for non-blocking downloads

### No External Dependencies
ADMX Manager uses only Python standard library modules. No `pip install` required for basic operation.

### Supported File Types
- `.admx` - Administrative template files
- `.adml` - Language-specific resource files
- `.zip` - Compressed archives (auto-extracted)
- `.msi` - Windows installers (downloaded, manual extraction)

---

## 🐛 Troubleshooting

### "Python is not installed"
Install Python 3.7+ from [python.org](https://python.org) and check "Add Python to PATH".

### "Permission denied" errors
Run as Administrator when:
- Installing templates locally
- Importing to SYSVOL

### Download failures
- Check internet connection
- Verify URL is accessible
- Some corporate networks block direct downloads

### ADMX not showing in Group Policy
- Restart Group Policy Editor
- Verify ADMX and ADML files are in correct folders
- Check that language folder matches your system language

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- Additional ADMX sources
- Better error handling
- Batch import features
- Automatic Intune API integration
- Support for additional languages

---

## 📝 License

MIT License - Free to use, modify, and distribute.

---

## 🙏 Credits

Created for IT Administrators managing Group Policy across:
- Active Directory Domain Services
- Microsoft Intune
- Hybrid identity environments

---

## 🔗 Links

- **Repository:** https://github.com/kbaker827/admx-manager
- **Issues:** https://github.com/kbaker827/admx-manager/issues
- **Releases:** https://github.com/kbaker827/admx-manager/releases

---

**Simplify your ADMX management! 🚀**

*Star this repo if it saves you time ⭐*
