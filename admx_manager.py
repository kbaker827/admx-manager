#!/usr/bin/env python3
"""
ADMX Manager - Windows Administrative Templates Download & Import Tool

A GUI application to browse, download, and import ADMX/ADML files
for Group Policy (local AD) or Microsoft Intune.

Supports:
- Windows 10/11 ADMX templates
- Microsoft Office ADMX templates
- Microsoft Edge ADMX templates
- Google Chrome ADMX templates
- Mozilla Firefox ADMX templates
- Custom ADMX sources
"""

import os
import re
import sys
import queue
import shutil
import zipfile
import threading
import subprocess
import webbrowser
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox, filedialog
except ImportError:  # Keep the helper functions importable (and testable) without Tk
    tk = None


USER_AGENT = "ADMX-Manager/1.1 (+https://github.com/kbaker827/admx-manager)"
DOWNLOAD_TIMEOUT = 60
CHUNK_SIZE = 64 * 1024
DEFAULT_LANGUAGE = "en-US"
SYSVOL_PLACEHOLDER = "\\\\your-domain\\SYSVOL\\your-domain\\Policies\\PolicyDefinitions"

# Language folders look like en-US, de-DE, sr-Latn-RS, zh-CN
LANGUAGE_FOLDER_RE = re.compile(r'^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){1,2}$')
INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

CHECKED = '☑'
UNCHECKED = '☐'


def safe_filename(name, fallback="download"):
    """Make a string safe to use as a Windows file name"""
    name = INVALID_FILENAME_CHARS_RE.sub('_', name).strip(' .')
    return name or fallback


def filename_from_response(url, content_disposition=None, fallback="download.zip"):
    """Work out a file name from a Content-Disposition header or the final URL"""
    if content_disposition:
        match = (re.search(r"filename\*\s*=\s*(?:UTF-8'')?\"?([^\";]+)\"?", content_disposition, re.I)
                 or re.search(r'filename\s*=\s*"?([^";]+)"?', content_disposition, re.I))
        if match:
            name = urllib.parse.unquote(match.group(1)).replace('\\', '/').split('/')[-1]
            if name.strip():
                return safe_filename(name, fallback)

    name = urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(url).path))
    if name and '.' in name:
        return safe_filename(name, fallback)
    return safe_filename(fallback)


def detect_file_type(path):
    """Identify a downloaded file by its content rather than its name"""
    with open(path, 'rb') as f:
        head = f.read(512)
    if head.startswith((b'PK\x03\x04', b'PK\x05\x06')):
        return 'zip'
    if head.startswith(b'MSCF'):
        return 'cab'
    if head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return 'msi'
    lowered = head.lower()
    if b'<!doctype html' in lowered or b'<html' in lowered:
        return 'html'
    return None


def is_language_folder(name):
    """True for ADML language folder names such as en-US"""
    return bool(LANGUAGE_FOLDER_RE.match(name))


def find_policy_files(root):
    """Return sorted (admx_files, adml_files) found under root"""
    admx_files = []
    adml_files = []
    for dirpath, _dirs, files in os.walk(root):
        for file in files:
            lower = file.lower()
            if lower.endswith('.admx'):
                admx_files.append(os.path.join(dirpath, file))
            elif lower.endswith('.adml'):
                adml_files.append(os.path.join(dirpath, file))
    return sorted(admx_files), sorted(adml_files)


def plan_policy_copy(admx_files, adml_files, dest):
    """Map each ADMX/ADML file to its destination in a PolicyDefinitions folder.

    ADMX files go in the root; ADML files go in their language folder
    (en-US when the source file is not inside one).
    """
    plan = [(src, os.path.join(dest, os.path.basename(src))) for src in admx_files]
    for src in adml_files:
        lang = os.path.basename(os.path.dirname(src))
        if not is_language_folder(lang):
            lang = DEFAULT_LANGUAGE
        plan.append((src, os.path.join(dest, lang, os.path.basename(src))))
    return plan


def duplicate_targets(plan):
    """Destination paths that more than one source file would be copied to"""
    seen = {}
    for _src, dst in plan:
        key = os.path.normcase(dst)
        seen[key] = seen.get(key, 0) + 1
    return sorted({dst for _src, dst in plan if seen[os.path.normcase(dst)] > 1})


def admx_missing_adml(admx_files, adml_files):
    """ADMX file names that have no matching ADML in any language"""
    adml_stems = {os.path.splitext(os.path.basename(f))[0].lower() for f in adml_files}
    return sorted({os.path.basename(f) for f in admx_files
                   if os.path.splitext(os.path.basename(f))[0].lower() not in adml_stems})


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Report redirects instead of following them"""

    def redirect_request(self, *args, **kwargs):
        return None


def github_tag_from_url(url):
    """Extract the tag from a .../releases/tag/<tag> or .../releases/download/<tag>/... URL"""
    match = re.search(r'/releases/(?:tag|download)/([^/?#]+)', url or '')
    return urllib.parse.unquote(match.group(1)) if match else None


def resolve_download_url(info, opener=None):
    """Return a direct download URL for a source, or None if it must be downloaded manually"""
    if info.get('direct_url'):
        return info['direct_url']

    release = info.get('github_release')
    if release:
        # .../releases/latest/download/<file> redirects to .../releases/download/<tag>/<file>.
        # Only the Location header is needed, so the redirect is not followed.
        opener = opener or urllib.request.build_opener(_NoRedirect).open
        probe = f"https://github.com/{release['repo']}/releases/latest/download/{release['asset'].format(tag='latest')}"
        request = urllib.request.Request(probe, headers={'User-Agent': USER_AGENT}, method='HEAD')
        try:
            with opener(request, timeout=DOWNLOAD_TIMEOUT) as response:
                location = response.headers.get('Location') or response.geturl()
        except urllib.error.HTTPError as e:
            location = e.headers.get('Location') if e.code in (301, 302, 303, 307, 308) else None
            if not location:
                raise
        tag = github_tag_from_url(location)
        if not tag or tag == 'latest':
            raise ValueError(f"Could not find the latest release of {release['repo']}")
        asset = release['asset'].format(tag=tag)
        return f"https://github.com/{release['repo']}/releases/download/{tag}/{asset}"

    return None


def extract_archive(archive_path, extract_dir, log, file_type=None, depth=0):
    """Extract a ZIP or CAB into extract_dir, including archives nested inside it.

    MSI packages are never run automatically: even an administrative install
    (msiexec /a) can execute custom actions embedded in the package.

    Returns True if anything was extracted.
    """
    file_type = file_type or detect_file_type(archive_path)

    if file_type == 'msi':
        log(f"  Note: MSI packages are not extracted automatically. If you trust it, install it or run:\n"
            f"    msiexec /a \"{os.path.abspath(archive_path)}\" TARGETDIR=\"{os.path.abspath(extract_dir)}\"")
        return False

    if file_type == 'zip':
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
    elif file_type == 'cab':
        if sys.platform != 'win32':
            log(f"  Note: CAB files can only be extracted on Windows: {archive_path}")
            return False
        os.makedirs(extract_dir, exist_ok=True)
        cmd = ['expand.exe', archive_path, '-F:*', extract_dir]
        result = subprocess.run(cmd, capture_output=True, timeout=600,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0:
            raise RuntimeError(f"{cmd[0]} exited with code {result.returncode}")
    else:
        return False

    log(f"  Extracted: {archive_path} -> {extract_dir}")

    # Some vendors ship a ZIP inside a CAB (e.g. Edge)
    if depth < 2:
        for dirpath, _dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower().endswith(('.zip', '.cab')):
                    nested = os.path.join(dirpath, file)
                    nested_type = detect_file_type(nested)
                    if nested_type in ('zip', 'cab'):
                        extract_archive(nested, os.path.splitext(nested)[0], log, nested_type, depth + 1)
    return True


class ADMXManager:
    """Main ADMX Manager application"""

    # Predefined ADMX sources
    #   url          - page with more information / manual download
    #   direct_url   - direct link to the template file
    #   github_release - resolve the latest GitHub release asset at download time
    # Sources with no direct link open their download page in the browser.
    DEFAULT_SOURCES = {
        "Windows 11": {
            "url": "https://learn.microsoft.com/en-us/troubleshoot/windows-client/group-policy/create-and-manage-central-store",
            "description": "Windows 11 Administrative Templates (download page lists each release)",
            "publisher": "Microsoft",
            "category": "Operating System"
        },
        "Windows 10": {
            "url": "https://learn.microsoft.com/en-us/troubleshoot/windows-client/group-policy/create-and-manage-central-store",
            "description": "Windows 10 Administrative Templates (download page lists each release)",
            "publisher": "Microsoft",
            "category": "Operating System"
        },
        "Microsoft Office 2021/365": {
            "url": "https://www.microsoft.com/en-us/download/details.aspx?id=49030",
            "description": "Microsoft Office 2021 and Microsoft 365 Apps ADMX templates",
            "publisher": "Microsoft",
            "category": "Productivity"
        },
        "Microsoft Edge": {
            "url": "https://www.microsoft.com/en-us/edge/business/download",
            "direct_url": "https://go.microsoft.com/fwlink/?linkid=2099616",
            "description": "Microsoft Edge browser ADMX templates",
            "publisher": "Microsoft",
            "category": "Browser"
        },
        "Google Chrome": {
            "url": "https://support.google.com/chrome/a/answer/187202",
            "direct_url": "https://dl.google.com/dl/edgedl/chrome/policy/policy_templates.zip",
            "description": "Google Chrome browser ADMX templates",
            "publisher": "Google",
            "category": "Browser"
        },
        "Mozilla Firefox": {
            "url": "https://github.com/mozilla/policy-templates/releases",
            "github_release": {"repo": "mozilla/policy-templates", "asset": "policy_templates_{tag}.zip"},
            "description": "Mozilla Firefox browser ADMX templates",
            "publisher": "Mozilla",
            "category": "Browser"
        },
        "Adobe Acrobat Reader": {
            "url": "https://www.adobe.com/devnet-docs/acrobatetk/tools/PrefRef/Windows/index.html",
            "description": "Adobe Acrobat Reader ADMX templates",
            "publisher": "Adobe",
            "category": "Productivity"
        },
        "Citrix Workspace": {
            "url": "https://docs.citrix.com/en-us/citrix-workspace-app-for-windows",
            "description": "Citrix Workspace app ADMX templates",
            "publisher": "Citrix",
            "category": "Virtualization"
        },
        "VMware Horizon": {
            "url": "https://docs.vmware.com/en/VMware-Horizon-Client/index.html",
            "description": "VMware Horizon client ADMX templates",
            "publisher": "VMware",
            "category": "Virtualization"
        },
        "Zoom": {
            "url": "https://support.zoom.us/hc/en-us/articles/360041100732",
            "description": "Zoom Desktop Client ADMX templates",
            "publisher": "Zoom",
            "category": "Communication"
        }
    }

    BASE_CATEGORIES = ["Operating System", "Browser", "Productivity", "Virtualization", "Communication", "Other"]

    def __init__(self, root):
        self.root = root
        self.root.title("ADMX Manager - Windows Administrative Templates")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        # Data storage
        self.admx_sources = {name: dict(info) for name, info in self.DEFAULT_SOURCES.items()}
        self.selected_sources = {}
        self.action_buttons = []
        self.busy = False

        # Worker threads must not touch Tk directly; they queue UI updates here
        self._ui_queue = queue.Queue()

        self.setup_ui()
        self.load_sources()
        self._ui_after_id = self.root.after(100, self._process_ui_queue)

    def setup_ui(self):
        """Setup the user interface"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        self.create_header(main_frame)

        # Bottom panel - Log and Status (packed before content so it keeps its space)
        self.create_log_panel(main_frame)

        # Content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # Left panel - ADMX Source List
        self.create_source_panel(content_frame)

        # Right panel - Details and Actions
        self.create_details_panel(content_frame)

    def create_header(self, parent):
        """Create header section"""
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(
            header,
            text="ADMX Manager",
            font=('Segoe UI', 16, 'bold')
        ).pack(side=tk.LEFT)

        ttk.Label(
            header,
            text="Download and Import Administrative Templates",
            font=('Segoe UI', 9)
        ).pack(side=tk.LEFT, padx=(10, 0))

        # Action buttons
        btn_frame = ttk.Frame(header)
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(
            btn_frame,
            text="➕ Add Custom Source",
            command=self.add_custom_source
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            btn_frame,
            text="🔄 Refresh List",
            command=self.refresh_sources
        ).pack(side=tk.LEFT, padx=5)

    def create_source_panel(self, parent):
        """Create left panel with ADMX source list"""
        left_frame = ttk.LabelFrame(parent, text="Available ADMX Templates", padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # Search/filter
        search_frame = ttk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', self.filter_sources)
        ttk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Category filter
        ttk.Label(search_frame, text="Category:").pack(side=tk.LEFT)
        self.category_var = tk.StringVar(value="All")
        self.category_combo = ttk.Combobox(
            search_frame,
            textvariable=self.category_var,
            values=["All"] + self.BASE_CATEGORIES,
            width=15,
            state="readonly"
        )
        self.category_combo.pack(side=tk.LEFT, padx=5)
        self.category_combo.bind('<<ComboboxSelected>>', lambda e: self.filter_sources())

        # Select all/none buttons
        select_frame = ttk.Frame(left_frame)
        select_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(
            select_frame,
            text=f"{CHECKED} Select All",
            command=self.select_all
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            select_frame,
            text=f"{UNCHECKED} Select None",
            command=self.select_none
        ).pack(side=tk.LEFT, padx=2)

        ttk.Label(
            select_frame,
            text="Click ✓ or press Space to select",
            foreground="gray"
        ).pack(side=tk.RIGHT, padx=2)

        # Treeview for sources
        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('selected', 'name', 'publisher', 'category', 'description')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='extended')

        self.tree.heading('selected', text='✓')
        self.tree.heading('name', text='Template Name')
        self.tree.heading('publisher', text='Publisher')
        self.tree.heading('category', text='Category')
        self.tree.heading('description', text='Description')

        self.tree.column('selected', width=30, anchor='center', stretch=False)
        self.tree.column('name', width=200)
        self.tree.column('publisher', width=100)
        self.tree.column('category', width=100)
        self.tree.column('description', width=300)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Bind checkbox toggle
        self.tree.bind('<ButtonRelease-1>', self.toggle_selection)
        self.tree.bind('<space>', self.toggle_focused)
        self.tree.bind('<<TreeviewSelect>>', self.show_details)

    def create_details_panel(self, parent):
        """Create right panel with details and import options"""
        right_frame = ttk.Notebook(parent)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Details tab
        details_tab = ttk.Frame(right_frame, padding="10")
        right_frame.add(details_tab, text="Details")

        self.details_text = scrolledtext.ScrolledText(
            details_tab,
            wrap=tk.WORD,
            width=40,
            height=15,
            font=('Segoe UI', 9)
        )
        self.details_text.pack(fill=tk.BOTH, expand=True)
        self.details_text.insert(tk.END, "Select an ADMX source to view details...")
        self.details_text.config(state=tk.DISABLED)

        self.open_page_button = ttk.Button(
            details_tab,
            text="🌐 Open Download Page",
            command=self.open_download_page,
            state=tk.DISABLED
        )
        self.open_page_button.pack(fill=tk.X, pady=(5, 0))
        self.details_source = None

        # Download tab
        download_tab = ttk.Frame(right_frame, padding="10")
        right_frame.add(download_tab, text="Download")

        ttk.Label(
            download_tab,
            text="Download Options",
            font=('Segoe UI', 10, 'bold')
        ).pack(anchor=tk.W, pady=(0, 10))

        self.download_path_var = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "ADMX"))

        path_frame = ttk.Frame(download_tab)
        path_frame.pack(fill=tk.X, pady=5)

        ttk.Label(path_frame, text="Download to:").pack(side=tk.LEFT)
        ttk.Entry(path_frame, textvariable=self.download_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Button(path_frame, text="Browse...", command=self.browse_download_path).pack(side=tk.LEFT)

        # Extract options
        self.extract_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            download_tab,
            text="Extract archives automatically (ZIP; CAB on Windows)",
            variable=self.extract_var
        ).pack(anchor=tk.W, pady=5)

        self.organize_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            download_tab,
            text="Organize by publisher/category",
            variable=self.organize_var
        ).pack(anchor=tk.W, pady=5)

        ttk.Separator(download_tab, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        self.add_action_button(
            download_tab,
            text="⬇️ Download Selected",
            command=self.download_selected
        ).pack(fill=tk.X, pady=5)

        ttk.Label(
            download_tab,
            text="Templates without a direct download link open their download page "
                 "in your browser. Save or extract those files into the download folder "
                 "above so they can be imported.",
            wraplength=350,
            foreground="gray"
        ).pack(anchor=tk.W, pady=5)

        # Import tab
        import_tab = ttk.Frame(right_frame, padding="10")
        right_frame.add(import_tab, text="Import")

        ttk.Label(
            import_tab,
            text="Import Destination",
            font=('Segoe UI', 10, 'bold')
        ).pack(anchor=tk.W, pady=(0, 10))

        # Import to Intune
        intune_frame = ttk.LabelFrame(import_tab, text="Microsoft Intune", padding="10")
        intune_frame.pack(fill=tk.X, pady=5)

        ttk.Label(
            intune_frame,
            text="Import ADMX templates into Intune for Windows configuration profiles."
        ).pack(anchor=tk.W)

        ttk.Button(
            intune_frame,
            text="Import to Intune",
            command=self.import_to_intune
        ).pack(fill=tk.X, pady=5)

        # Import to Local AD
        ad_frame = ttk.LabelFrame(import_tab, text="Active Directory (Local)", padding="10")
        ad_frame.pack(fill=tk.X, pady=5)

        ttk.Label(
            ad_frame,
            text="Copy ADMX files to SYSVOL for domain Group Policy."
        ).pack(anchor=tk.W)

        self.sysvol_var = tk.StringVar(value=SYSVOL_PLACEHOLDER)

        sysvol_frame = ttk.Frame(ad_frame)
        sysvol_frame.pack(fill=tk.X, pady=5)

        ttk.Entry(sysvol_frame, textvariable=self.sysvol_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(sysvol_frame, text="Browse...", command=self.browse_sysvol).pack(side=tk.LEFT)

        self.add_action_button(
            ad_frame,
            text="Import to SYSVOL",
            command=self.import_to_sysvol
        ).pack(fill=tk.X, pady=5)

        # Local Policy
        local_frame = ttk.LabelFrame(import_tab, text="Local Computer", padding="10")
        local_frame.pack(fill=tk.X, pady=5)

        ttk.Label(
            local_frame,
            text="Install ADMX templates on local machine for Local Group Policy."
        ).pack(anchor=tk.W)

        self.add_action_button(
            local_frame,
            text="Install Locally",
            command=self.install_locally
        ).pack(fill=tk.X, pady=5)

    def create_log_panel(self, parent):
        """Create bottom log panel"""
        log_frame = ttk.LabelFrame(parent, text="Activity Log", padding="5")
        log_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=False, pady=(10, 0))

        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            height=8,
            font=('Consolas', 9)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Log buttons
        btn_frame = ttk.Frame(log_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(
            btn_frame,
            text="📋 Copy Log",
            command=self.copy_log
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            btn_frame,
            text="💾 Save Log",
            command=self.save_log
        ).pack(side=tk.LEFT, padx=2)

        ttk.Button(
            btn_frame,
            text="🗑️ Clear",
            command=self.clear_log
        ).pack(side=tk.LEFT, padx=2)

        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            log_frame,
            variable=self.progress_var,
            maximum=100,
            mode='determinate'
        )
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(log_frame, textvariable=self.status_var).pack(anchor=tk.W, pady=(5, 0))

    def add_action_button(self, parent, **kwargs):
        """Create a button that is disabled while a background task runs"""
        button = ttk.Button(parent, **kwargs)
        self.action_buttons.append(button)
        return button

    # ------------------------------------------------------------------
    # Thread-safe UI helpers
    # ------------------------------------------------------------------

    def _ui(self, func, *args):
        """Run func on the Tk thread (immediately if already on it)"""
        if threading.current_thread() is threading.main_thread():
            func(*args)
        else:
            self._ui_queue.put((func, args))

    def _process_ui_queue(self):
        """Apply UI updates queued by worker threads"""
        try:
            while True:
                func, args = self._ui_queue.get_nowait()
                try:
                    func(*args)
                except Exception as e:
                    self._append_log(f"✗ UI update failed: {e}")
        except queue.Empty:
            pass
        self._ui_after_id = self.root.after(100, self._process_ui_queue)

    def _set_busy(self, busy):
        """Enable/disable action buttons while a task runs"""
        self.busy = busy
        for button in self.action_buttons:
            button.config(state=tk.DISABLED if busy else tk.NORMAL)
        self.root.config(cursor='watch' if busy else '')

    def _run_background(self, target, *args):
        """Run target(*args) on a worker thread with action buttons disabled"""
        if self.busy:
            messagebox.showinfo("Busy", "Please wait for the current operation to finish.")
            return
        self._set_busy(True)

        def runner():
            try:
                target(*args)
            except Exception as e:
                self.log(f"✗ Unexpected error: {e}")
                self._ui(messagebox.showerror, "Error", str(e))
            finally:
                self._ui(self._set_busy, False)

        threading.Thread(target=runner, daemon=True).start()

    # ------------------------------------------------------------------
    # Source list
    # ------------------------------------------------------------------

    def load_sources(self):
        """Load ADMX sources into treeview"""
        for name in self.admx_sources:
            self.selected_sources.setdefault(name, False)
        for name in list(self.selected_sources):
            if name not in self.admx_sources:
                del self.selected_sources[name]

        categories = list(self.BASE_CATEGORIES)
        for info in self.admx_sources.values():
            category = info.get('category', 'Other')
            if category not in categories:
                categories.append(category)
        self.category_combo.config(values=["All"] + categories)

        self.filter_sources()
        self.log(f"Loaded {len(self.admx_sources)} ADMX sources")

    def _row_values(self, name, info):
        """Treeview row values for a source"""
        description = info.get('description', '')
        if len(description) > 50:
            description = description[:50] + '...'
        return (
            CHECKED if self.selected_sources.get(name, False) else UNCHECKED,
            name,
            info.get('publisher', 'Unknown'),
            info.get('category', 'Other'),
            description
        )

    def filter_sources(self, *args):
        """Filter sources based on search and category"""
        search_term = self.search_var.get().lower()
        category = self.category_var.get()

        # Clear tree
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Add filtered sources
        for name, info in self.admx_sources.items():
            # Check search
            searchable = ' '.join((name, info.get('description', ''), info.get('publisher', ''))).lower()
            if search_term and search_term not in searchable:
                continue

            # Check category
            if category != "All" and info.get('category', 'Other') != category:
                continue

            # Source name is the item id
            self.tree.insert('', 'end', iid=name, values=self._row_values(name, info))

    def _set_selected(self, name, selected):
        """Update a source's checkbox state"""
        self.selected_sources[name] = selected
        if self.tree.exists(name):
            self.tree.item(name, values=self._row_values(name, self.admx_sources[name]))
        if self.details_source == name:
            self.update_details(name)

    def toggle_selection(self, event):
        """Toggle checkbox selection"""
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != '#1':  # Checkbox column
            return
        name = self.tree.identify_row(event.y)
        if name:
            self._set_selected(name, not self.selected_sources.get(name, False))
            self.log(f"{'Selected' if self.selected_sources[name] else 'Deselected'}: {name}")

    def toggle_focused(self, event=None):
        """Toggle the highlighted rows with the keyboard"""
        names = self.tree.selection()
        if not names:
            return 'break'
        new_state = not all(self.selected_sources.get(name, False) for name in names)
        for name in names:
            self._set_selected(name, new_state)
        return 'break'

    def select_all(self):
        """Select all visible sources"""
        for name in self.tree.get_children():
            self._set_selected(name, True)
        self.log("Selected all visible sources")

    def select_none(self):
        """Deselect all sources"""
        for name in list(self.selected_sources):
            self._set_selected(name, False)
        self.log("Deselected all sources")

    def show_details(self, event=None):
        """Show details for the highlighted item"""
        selection = self.tree.selection()
        if selection:
            self.update_details(selection[0])

    def update_details(self, name):
        """Update details panel"""
        info = self.admx_sources.get(name, {})
        self.details_source = name

        if info.get('direct_url'):
            download = info['direct_url']
        elif info.get('github_release'):
            download = f"Latest release of github.com/{info['github_release']['repo']}"
        else:
            download = "No direct link - Download opens the page below in your browser"

        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)

        details = f"""Name: {name}
Publisher: {info.get('publisher', 'Unknown')}
Category: {info.get('category', 'Other')}

Description:
{info.get('description') or 'No description available'}

Download:
{download}

More information:
{info.get('url', 'N/A')}

Status: {CHECKED + ' Selected for download' if self.selected_sources.get(name, False) else UNCHECKED + ' Not selected'}
"""

        self.details_text.insert(tk.END, details)
        self.details_text.config(state=tk.DISABLED)
        self.open_page_button.config(state=tk.NORMAL if info.get('url') else tk.DISABLED)

    def open_download_page(self):
        """Open the highlighted source's web page"""
        info = self.admx_sources.get(self.details_source or '', {})
        if info.get('url'):
            webbrowser.open(info['url'])

    def browse_download_path(self):
        """Browse for download directory"""
        path = filedialog.askdirectory()
        if path:
            self.download_path_var.set(os.path.normpath(path))

    def browse_sysvol(self):
        """Browse for SYSVOL path"""
        path = filedialog.askdirectory()
        if path:
            self.sysvol_var.set(os.path.normpath(path))

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_selected(self):
        """Download selected ADMX sources"""
        selected = [name for name, selected in self.selected_sources.items() if selected]

        if not selected:
            messagebox.showwarning("No Selection", "Please select at least one ADMX source to download.")
            return

        download_path = self.download_path_var.get().strip()
        if not download_path:
            messagebox.showwarning("Download Folder", "Please choose a download folder.")
            return
        try:
            os.makedirs(download_path, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Download Folder", f"Cannot create download folder:\n{e}")
            return

        self.log(f"Starting download of {len(selected)} ADMX source(s)...")
        self.status_var.set(f"Downloading {len(selected)} sources...")
        self.progress_var.set(0)

        # Read Tk variables here; the worker thread must not touch them
        options = {'extract': self.extract_var.get(), 'organize': self.organize_var.get()}
        self._run_background(self._download_thread, selected, download_path, options)

    def _download_thread(self, selected, download_path, options):
        """Download thread"""
        total = len(selected)
        successful = []
        failed = []
        manual = []

        for i, name in enumerate(selected):
            info = self.admx_sources[name]

            def set_progress(fraction, i=i):
                self._ui(self.progress_var.set, (i + fraction) / total * 100)

            set_progress(0)
            try:
                url = resolve_download_url(info)
                if not url:
                    page = info.get('url')
                    if page:
                        self.log(f"🌐 {name} has no direct download link; opening {page}")
                        self._ui(webbrowser.open, page)
                    else:
                        self.log(f"⚠️ No download URL for {name}")
                    manual.append(name)
                    continue

                # Create subdirectories if organizing
                if options['organize']:
                    save_dir = os.path.join(download_path,
                                            safe_filename(info.get('publisher', 'Other'), 'Other'),
                                            safe_filename(info.get('category', 'Other'), 'Other'))
                else:
                    save_dir = download_path
                os.makedirs(save_dir, exist_ok=True)

                self.log(f"Downloading {name}...")
                save_path = self._download_file(url, save_dir, safe_filename(name) + '.zip', set_progress)
                self.log(f"✓ Downloaded: {save_path}")

                file_type = detect_file_type(save_path)
                if file_type == 'html':
                    os.remove(save_path)
                    raise ValueError("the link returned a web page instead of a template file")

                # Extract into a folder named after the archive so sources don't overwrite each other
                if options['extract'] and file_type in ('zip', 'cab', 'msi'):
                    try:
                        extract_archive(save_path, os.path.splitext(save_path)[0], self.log, file_type)
                    except Exception as e:
                        self.log(f"  Warning: Could not extract {save_path}: {e}")

                successful.append(name)

            except Exception as e:
                self.log(f"✗ Failed to download {name}: {e}")
                failed.append(name)

        self._ui(self.progress_var.set, 100)
        summary = f"Downloaded {len(successful)}/{total} sources"
        self._ui(self.status_var.set, summary)
        self.log(f"Download complete: {len(successful)} downloaded, {len(failed)} failed, {len(manual)} manual")

        message = [f"{summary} to:\n{download_path}"]
        if failed:
            message.append("Failed:\n  " + "\n  ".join(failed))
        if manual:
            message.append("Opened download page (download these manually into the folder above):\n  "
                           + "\n  ".join(manual))
        show = messagebox.showwarning if failed else messagebox.showinfo
        self._ui(show, "Download Complete", "\n\n".join(message))

    def _download_file(self, url, save_dir, fallback_name, set_progress):
        """Stream url into save_dir and return the saved path"""
        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
            content_type = response.headers.get('Content-Type', '')
            if 'text/html' in content_type.lower():
                raise ValueError("the link returned a web page instead of a template file")

            filename = filename_from_response(response.geturl(),
                                              response.headers.get('Content-Disposition'),
                                              fallback_name)
            save_path = os.path.join(save_dir, filename)
            part_path = save_path + '.part'
            size = int(response.headers.get('Content-Length') or 0)
            received = 0

            try:
                with open(part_path, 'wb') as f:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                        if size:
                            set_progress(min(received / size, 1.0))
                if size and received < size:
                    raise IOError(f"download incomplete ({received} of {size} bytes)")
                os.replace(part_path, save_path)
            finally:
                if os.path.exists(part_path):
                    os.remove(part_path)

        return save_path

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _find_downloaded_policy_files(self):
        """Find ADMX/ADML files in the download folder, or show an error"""
        download_path = self.download_path_var.get().strip()
        if not download_path or not os.path.isdir(download_path):
            messagebox.showerror("No Downloads", "Please download ADMX files first.")
            return None

        admx_files, adml_files = find_policy_files(download_path)
        if not admx_files:
            messagebox.showerror("No ADMX Files", f"No ADMX files found in:\n{download_path}\n\n"
                                 "Download templates first, and extract any archives or MSIs.")
            return None
        return download_path, admx_files, adml_files

    def import_to_intune(self):
        """Import ADMX to Microsoft Intune"""
        self.log("Preparing Intune import...")

        instructions = """
To import ADMX templates into Microsoft Intune:

1. Open the Microsoft Intune admin center
   https://intune.microsoft.com

2. Navigate to:
   Devices > Manage devices > Configuration > Import ADMX

3. Click "Import"

4. Select the downloaded ADMX files:
"""

        download_path = self.download_path_var.get().strip()
        if download_path and os.path.isdir(download_path):
            instructions += f"\n   Location: {download_path}\n"

            admx_files, adml_files = find_policy_files(download_path)
            en_us = {os.path.splitext(os.path.basename(f))[0].lower(): f for f in adml_files
                     if os.path.basename(os.path.dirname(f)).lower() == 'en-us'}

            if admx_files:
                instructions += f"\n   Found {len(admx_files)} ADMX file(s)\n"
                instructions += "\n   Files (ADMX -> en-US ADML):\n"
                for f in admx_files[:20]:  # Show first 20
                    adml = en_us.get(os.path.splitext(os.path.basename(f))[0].lower())
                    instructions += f"   - {f}\n"
                    instructions += f"       {adml or '(no en-US ADML found)'}\n"
                if len(admx_files) > 20:
                    instructions += f"   ... and {len(admx_files) - 20} more\n"
            else:
                instructions += "\n   No ADMX files found yet - download templates first.\n"

        instructions += """
5. For each ADMX file:
   - Upload the .admx file
   - Upload the matching en-US .adml file (Intune only accepts en-US)
   - Import files that others depend on first
     (for example google.admx before chrome.admx)

6. Click "Create"

7. The ADMX templates will now be available in:
   Devices > Configuration > Create > Templates > Imported Administrative templates

Note: ADMX ingestion in Intune may take a few minutes to process.
"""

        self.show_instructions("Import to Intune", instructions)

    def _confirm_copy(self, title, dest, plan, admx_files, adml_files):
        """Summarise what will be copied and ask the user to confirm"""
        message = (f"Copy {len(admx_files)} ADMX and {len(adml_files)} ADML file(s) from the "
                   f"download folder to:\n{dest}\n\nExisting files with the same name will be overwritten.")

        duplicates = duplicate_targets(plan)
        if duplicates:
            names = sorted({os.path.basename(d) for d in duplicates})
            message += (f"\n\n⚠ {len(names)} file name(s) exist in more than one download "
                        f"(e.g. {', '.join(names[:3])}); the last one found wins.")

        missing = admx_missing_adml(admx_files, adml_files)
        if missing:
            message += (f"\n\n⚠ No ADML language file for: {', '.join(missing[:5])}"
                        f"{' ...' if len(missing) > 5 else ''}. Group Policy Editor will show errors for these.")

        return messagebox.askyesno(title, message + "\n\nContinue?")

    def import_to_sysvol(self):
        """Import ADMX to SYSVOL for domain Group Policy"""
        sysvol_path = self.sysvol_var.get().strip()

        if not sysvol_path or sysvol_path == SYSVOL_PLACEHOLDER:
            messagebox.showerror("SYSVOL Path Required", "Please enter your domain's SYSVOL PolicyDefinitions path.")
            return

        # The central store folder itself may not exist yet, but its parent must
        parent = os.path.dirname(sysvol_path.rstrip('\\/'))
        if not os.path.isdir(sysvol_path) and not os.path.isdir(parent):
            messagebox.showerror("SYSVOL Path Not Found", f"Cannot reach:\n{parent}\n\n"
                                 "Check the path and that you are connected to the domain.")
            return

        found = self._find_downloaded_policy_files()
        if not found:
            return
        _download_path, admx_files, adml_files = found

        plan = plan_policy_copy(admx_files, adml_files, sysvol_path)
        if not self._confirm_copy("Import to SYSVOL", sysvol_path, plan, admx_files, adml_files):
            return

        self.log(f"Importing ADMX files to SYSVOL: {sysvol_path}")
        self._run_background(self._copy_thread, plan, len(admx_files), len(adml_files),
                             "SYSVOL", "Group Policy will automatically use these templates.")

    def install_locally(self):
        """Install ADMX templates on local machine"""
        if sys.platform != 'win32':
            messagebox.showerror("Windows Only", "Local installation is only available on Windows.")
            return

        # Windows PolicyDefinitions path
        policy_defs = os.path.expandvars(r"%SystemRoot%\PolicyDefinitions")

        found = self._find_downloaded_policy_files()
        if not found:
            return
        _download_path, admx_files, adml_files = found

        plan = plan_policy_copy(admx_files, adml_files, policy_defs)
        if not self._confirm_copy("Install Locally", policy_defs, plan, admx_files, adml_files):
            return

        self.log("Installing ADMX templates locally...")
        self._run_background(self._copy_thread, plan, len(admx_files), len(adml_files),
                             "the local computer",
                             "You can now use these templates in Local Group Policy Editor (gpedit.msc).")

    def _copy_thread(self, plan, admx_count, adml_count, target_name, done_note):
        """Copy files according to plan (runs on a worker thread)"""
        total = len(plan)
        try:
            for i, (src, dst) in enumerate(plan, 1):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                self.log(f"Copied: {os.path.basename(src)} -> {os.path.dirname(dst)}")
                self._ui(self.progress_var.set, i / total * 100)
        except PermissionError as e:
            self.log(f"✗ Permission denied: {e}")
            self._ui(messagebox.showerror, "Permission Denied",
                     f"Could not write to {target_name}:\n{e}\n\n"
                     "Administrator (or domain admin) rights are required. "
                     "Right-click and 'Run as administrator'.")
            return
        except Exception as e:
            self.log(f"✗ Import failed: {e}")
            self._ui(messagebox.showerror, "Import Failed", f"Failed to copy to {target_name}:\n{e}")
            return

        self.log(f"✓ Successfully copied {admx_count} ADMX and {adml_count} ADML files to {target_name}")
        self._ui(messagebox.showinfo, "Import Complete",
                 f"Copied {admx_count} ADMX and {adml_count} ADML files to {target_name}.\n\n{done_note}")

    # ------------------------------------------------------------------
    # Custom sources
    # ------------------------------------------------------------------

    def add_custom_source(self):
        """Add custom ADMX source"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Custom ADMX Source")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text="Name:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        name_var = tk.StringVar()
        name_entry = ttk.Entry(dialog, textvariable=name_var, width=50)
        name_entry.pack(fill=tk.X, padx=10, pady=5)
        name_entry.focus_set()

        ttk.Label(dialog, text="Download URL (direct link to .zip/.admx/.msi):").pack(anchor=tk.W, padx=10, pady=(10, 0))
        url_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=url_var, width=50).pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(dialog, text="Publisher:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        publisher_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=publisher_var, width=50).pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(dialog, text="Category:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        category_var = tk.StringVar(value="Other")
        ttk.Combobox(
            dialog,
            textvariable=category_var,
            values=self.BASE_CATEGORIES,
            width=47
        ).pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(dialog, text="Description:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        desc_text = scrolledtext.ScrolledText(dialog, height=5, width=50)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)
        desc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        def save_custom():
            name = name_var.get().strip()
            url = url_var.get().strip()
            publisher = publisher_var.get().strip() or "Custom"
            category = category_var.get().strip() or "Other"
            description = desc_text.get(1.0, tk.END).strip()

            if not name or not url:
                messagebox.showerror("Required Fields", "Name and URL are required.", parent=dialog)
                return

            if urllib.parse.urlparse(url).scheme not in ('http', 'https'):
                messagebox.showerror("Invalid URL", "The URL must start with http:// or https://", parent=dialog)
                return

            if name in self.admx_sources and not messagebox.askyesno(
                    "Replace Source", f"A source named '{name}' already exists. Replace it?", parent=dialog):
                return

            self.admx_sources[name] = {
                "url": url,
                "direct_url": url,
                "description": description,
                "publisher": publisher,
                "category": category
            }

            self.load_sources()
            self.log(f"Added custom source: {name}")
            dialog.destroy()

        ttk.Button(btn_frame, text="Save", command=save_custom).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        dialog.bind('<Escape>', lambda e: dialog.destroy())

    def refresh_sources(self):
        """Refresh ADMX sources list"""
        self.load_sources()
        self.log("Refreshed ADMX sources list")

    # ------------------------------------------------------------------
    # Dialogs and log
    # ------------------------------------------------------------------

    def show_instructions(self, title, text):
        """Show instructions in a dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("700x550")
        dialog.transient(self.root)

        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(side=tk.BOTTOM, pady=10)

        text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=('Segoe UI', 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))
        text_widget.insert(tk.END, text)
        text_widget.config(state=tk.DISABLED)

    def copy_log(self):
        """Copy log to clipboard"""
        log_content = self.log_text.get(1.0, tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(log_content)
        self.status_var.set("Log copied to clipboard")

    def save_log(self):
        """Save log to file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"admx_manager_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        if filename:
            try:
                # UTF-8 so the log's symbols (✓, ✗, emoji) can be written on Windows
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                self.status_var.set(f"Log saved to {filename}")
            except OSError as e:
                messagebox.showerror("Save Log", f"Could not save log:\n{e}")

    def clear_log(self):
        """Clear log text"""
        self.log_text.delete(1.0, tk.END)
        self.status_var.set("Log cleared")

    def log(self, message):
        """Add message to log (safe to call from any thread)"""
        self._ui(self._append_log, message)

    def _append_log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"

        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.status_var.set(message[:100])


def main():
    """Main entry point"""
    if tk is None:
        print("ERROR: tkinter is not available. Install Python from python.org "
              "(tkinter is included with the Windows installer).", file=sys.stderr)
        sys.exit(1)

    # Set DPI awareness on Windows (must happen before the first window is created)
    if sys.platform == 'win32':
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    root = tk.Tk()
    ADMXManager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
