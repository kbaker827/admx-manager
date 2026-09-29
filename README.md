# ADMX Manager

**A Windows GUI tool to browse, download, and import ADMX/ADML administrative templates for Group Policy (Active Directory) or Microsoft Intune.**

[![CI](https://github.com/kbaker827/admx-manager/actions/workflows/ci.yml/badge.svg)](https://github.com/kbaker827/admx-manager/actions/workflows/ci.yml)
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

| Product | Publisher | Category | Download |
|---------|-----------|----------|----------|
| Windows 11 | Microsoft | Operating System | Opens download page |
| Windows 10 | Microsoft | Operating System | Opens download page |
| Microsoft Office 2021/365 | Microsoft | Productivity | Opens download page |
| Microsoft Edge | Microsoft | Browser | Direct |
| Google Chrome | Google | Browser | Direct |
| Mozilla Firefox | Mozilla | Browser | Direct (latest GitHub release) |
| Adobe Acrobat Reader | Adobe | Productivity | Opens download page |
| Citrix Workspace | Citrix | Virtualization | Opens download page |
| VMware Horizon | VMware | Virtualization | Opens download page |
| Zoom | Zoom | Communication | Opens download page |

Microsoft and most vendors publish a new link for every release, so templates without a stable link open their official download page in your browser. Save (and extract) those files into your download folder and ADMX Manager will import them along with the rest.

### 🎨 User-Friendly Interface
- **Search and filter** templates by name, publisher, or category
- **Select multiple** templates for batch download
- **Detailed preview** of each template
- **Progress tracking** for downloads
- **Activity logging** with export capability

### 📥 Download Options
- **Automatic extraction** of ZIP archives (and CAB/MSI packages on Windows)
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

1. **Select templates** from the list (click the ✓ column, press Space, or use "Select All")
2. **Choose download location** (default: `%USERPROFILE%\ADMX`)
3. **Click "Download Selected"**
4. Templates are automatically extracted and organized; templates without a direct link open their download page

### Importing to Intune

1. **Download** desired templates
2. Click **"Import to Intune"** for instructions and the list of files to upload
3. Navigate to the [Microsoft Intune admin center](https://intune.microsoft.com)
4. Go to **Devices > Manage devices > Configuration > Import ADMX**
5. Upload each `.admx` with its **en-US** `.adml` (import files others depend on first, e.g. `google.admx` before `chrome.admx`)

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

After downloading, files are organized by publisher and category, with each archive extracted into its own folder:

```
ADMX/
├── Google/
│   └── Browser/
│       ├── policy_templates.zip
│       └── policy_templates/
│           └── windows/admx/
│               ├── chrome.admx
│               └── en-US/
│                   └── chrome.adml
├── Mozilla/
│   └── Browser/
│       └── policy_templates_v8.3/
│           └── windows/
│               ├── firefox.admx
│               └── en-US/
│                   └── firefox.adml
└── ...
```

When importing, ADMX files are copied to the root of `PolicyDefinitions` and ADML files to their language folder (`en-US`, `de-DE`, ...).

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
- `.cab` - Cabinet archives (auto-extracted on Windows)
- `.msi` - Windows installers (unpacked with an administrative install on Windows, nothing is installed)

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

## 🧪 Development

Tests use only the standard library:

```batch
python -m unittest discover -s tests -v
```

GitHub Actions runs the tests on Windows and Linux for every push and pull request, and builds `ADMXManager.exe` as a downloadable artifact.

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
