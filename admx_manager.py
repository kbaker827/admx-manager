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

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import urllib.request
import urllib.error
import json
import os
import sys
import zipfile
import shutil
import tempfile
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET


class ADMXManager:
    """Main ADMX Manager application"""
    
    # Predefined ADMX sources
    DEFAULT_SOURCES = {
        "Windows 11 2024": {
            "url": "https://download.microsoft.com/download/3/0/6/306AC1B2-2C0F-4C1B-8F6E-4E0A6D6E5B4C/Windows11-ADMX.msi",
            "description": "Windows 11 2024 Update Administrative Templates",
            "publisher": "Microsoft",
            "category": "Operating System"
        },
        "Windows 10 22H2": {
            "url": "https://www.microsoft.com/en-us/download/details.aspx?id=104223",
            "direct_url": "https://download.microsoft.com/download/3/0/6/306AC1B2-2C0F-4C1B-8F6E-4E0A6D6E5B4C/Windows-10-ADMX.msi",
            "description": "Windows 10 22H2 Administrative Templates",
            "publisher": "Microsoft",
            "category": "Operating System"
        },
        "Microsoft Office 2021/365": {
            "url": "https://www.microsoft.com/en-us/download/details.aspx?id=49030",
            "direct_url": "https://download.microsoft.com/download/2/7/A/27A2B5B7-4D5A-4C7E-9E8A-9B9C9D0E1F2G/Office2021-ADMX.zip",
            "description": "Microsoft Office 2021 and Microsoft 365 Apps ADMX templates",
            "publisher": "Microsoft",
            "category": "Productivity"
        },
        "Microsoft Edge": {
            "url": "https://www.microsoft.com/en-us/download/details.aspx?id=55319",
            "direct_url": "https://edgeupdates.microsoft.com/products/MicrosoftEdgePolicyTemplates/MicrosoftEdgePolicyTemplates.zip",
            "description": "Microsoft Edge browser ADMX templates",
            "publisher": "Microsoft",
            "category": "Browser"
        },
        "Google Chrome": {
            "url": "https://dl.google.com/dl/edgedl/chrome/policy/policy_templates.zip",
            "description": "Google Chrome browser ADMX templates",
            "publisher": "Google",
            "category": "Browser"
        },
        "Mozilla Firefox": {
            "url": "https://github.com/mozilla/policy-templates/releases",
            "direct_url": "https://github.com/mozilla/policy-templates/releases/latest/download/policy_templates.zip",
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
    
    def __init__(self, root):
        self.root = root
        self.root.title("ADMX Manager - Windows Administrative Templates")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        
        # Data storage
        self.admx_sources = dict(self.DEFAULT_SOURCES)
        self.selected_sources = {}
        self.download_queue = []
        self.downloaded_files = []
        
        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="admx_manager_")
        
        self.setup_ui()
        self.load_sources()
        
    def setup_ui(self):
        """Setup the user interface"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        self.create_header(main_frame)
        
        # Content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Left panel - ADMX Source List
        self.create_source_panel(content_frame)
        
        # Right panel - Details and Actions
        self.create_details_panel(content_frame)
        
        # Bottom panel - Log and Status
        self.create_log_panel(main_frame)
        
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
        self.search_var.trace('w', self.filter_sources)
        ttk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Category filter
        ttk.Label(search_frame, text="Category:").pack(side=tk.LEFT)
        self.category_var = tk.StringVar(value="All")
        self.category_combo = ttk.Combobox(
            search_frame,
            textvariable=self.category_var,
            values=["All", "Operating System", "Browser", "Productivity", "Virtualization", "Communication"],
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
            text="☑️ Select All",
            command=self.select_all
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            select_frame,
            text="☐ Select None",
            command=self.select_none
        ).pack(side=tk.LEFT, padx=2)
        
        # Treeview for sources
        columns = ('selected', 'name', 'publisher', 'category', 'description')
        self.tree = ttk.Treeview(left_frame, columns=columns, show='headings', selectmode='extended')
        
        self.tree.heading('selected', text='✓')
        self.tree.heading('name', text='Template Name')
        self.tree.heading('publisher', text='Publisher')
        self.tree.heading('category', text='Category')
        self.tree.heading('description', text='Description')
        
        self.tree.column('selected', width=30, anchor='center')
        self.tree.column('name', width=200)
        self.tree.column('publisher', width=100)
        self.tree.column('category', width=100)
        self.tree.column('description', width=300)
        
        # Scrollbars
        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(left_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind checkbox toggle
        self.tree.bind('<ButtonRelease-1>', self.toggle_selection)
        self.tree.bind('<Double-1>', self.show_details)
        
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
            text="Extract archives automatically",
            variable=self.extract_var
        ).pack(anchor=tk.W, pady=5)
        
        self.organize_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            download_tab,
            text="Organize by publisher/category",
            variable=self.organize_var
        ).pack(anchor=tk.W, pady=5)
        
        ttk.Separator(download_tab, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        ttk.Button(
            download_tab,
            text="⬇️ Download Selected",
            command=self.download_selected
        ).pack(fill=tk.X, pady=5)
        
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
        
        self.sysvol_var = tk.StringVar(value="\\\\your-domain\\SYSVOL\\your-domain\\Policies\\PolicyDefinitions")
        
        sysvol_frame = ttk.Frame(ad_frame)
        sysvol_frame.pack(fill=tk.X, pady=5)
        
        ttk.Entry(sysvol_frame, textvariable=self.sysvol_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(sysvol_frame, text="Browse...", command=self.browse_sysvol).pack(side=tk.LEFT)
        
        ttk.Button(
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
        
        ttk.Button(
            local_frame,
            text="Install Locally",
            command=self.install_locally
        ).pack(fill=tk.X, pady=5)
        
    def create_log_panel(self, parent):
        """Create bottom log panel"""
        log_frame = ttk.LabelFrame(parent, text="Activity Log", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
        
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
        
    def load_sources(self):
        """Load ADMX sources into treeview"""
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Add sources
        for name, info in self.admx_sources.items():
            self.tree.insert('', 'end', values=(
                '☐',
                name,
                info.get('publisher', 'Unknown'),
                info.get('category', 'Other'),
                info.get('description', '')[:50] + '...' if len(info.get('description', '')) > 50 else info.get('description', '')
            ))
            self.selected_sources[name] = False
            
        self.log(f"Loaded {len(self.admx_sources)} ADMX sources")
        
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
            if search_term and search_term not in name.lower() and search_term not in info.get('description', '').lower():
                continue
            
            # Check category
            if category != "All" and info.get('category') != category:
                continue
            
            # Add to tree
            checked = '☑️' if self.selected_sources.get(name, False) else '☐'
            self.tree.insert('', 'end', values=(
                checked,
                name,
                info.get('publisher', 'Unknown'),
                info.get('category', 'Other'),
                info.get('description', '')[:50] + '...' if len(info.get('description', '')) > 50 else info.get('description', '')
            ))
            
    def toggle_selection(self, event):
        """Toggle checkbox selection"""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == '#1':  # Checkbox column
                item = self.tree.identify_row(event.y)
                if item:
                    values = self.tree.item(item, 'values')
                    name = values[1]
                    self.selected_sources[name] = not self.selected_sources.get(name, False)
                    new_check = '☑️' if self.selected_sources[name] else '☐'
                    self.tree.item(item, values=(new_check,) + values[1:])
                    self.log(f"{'Selected' if self.selected_sources[name] else 'Deselected'}: {name}")
                    self.update_details(name)
                    
    def select_all(self):
        """Select all visible sources"""
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            name = values[1]
            self.selected_sources[name] = True
            self.tree.item(item, values=('☑️',) + values[1:])
        self.log("Selected all visible sources")
        
    def select_none(self):
        """Deselect all sources"""
        for name in self.selected_sources:
            self.selected_sources[name] = False
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            self.tree.item(item, values=('☐',) + values[1:])
        self.log("Deselected all sources")
        
    def show_details(self, event):
        """Show details for selected item"""
 item = self.tree.identify_row(event.y)
        if item:
            values = self.tree.item(item, 'values')
            name = values[1]
            self.update_details(name)
            
    def update_details(self, name):
        """Update details panel"""
        info = self.admx_sources.get(name, {})
        
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)
        
        details = f"""Name: {name}
Publisher: {info.get('publisher', 'Unknown')}
Category: {info.get('category', 'Other')}

Description:
{info.get('description', 'No description available')}

Download URL:
{info.get('url', 'N/A')}

Status: {'☑️ Selected for download' if self.selected_sources.get(name, False) else '☐ Not selected'}
"""
        
        self.details_text.insert(tk.END, details)
        self.details_text.config(state=tk.DISABLED)
        
    def browse_download_path(self):
        """Browse for download directory"""
        path = filedialog.askdirectory()
        if path:
            self.download_path_var.set(path)
            
    def browse_sysvol(self):
        """Browse for SYSVOL path"""
        path = filedialog.askdirectory()
        if path:
            self.sysvol_var.set(path)
            
    def download_selected(self):
        """Download selected ADMX sources"""
        selected = [name for name, selected in self.selected_sources.items() if selected]
        
        if not selected:
            messagebox.showwarning("No Selection", "Please select at least one ADMX source to download.")
            return
        
        download_path = self.download_path_var.get()
        os.makedirs(download_path, exist_ok=True)
        
        self.log(f"Starting download of {len(selected)} ADMX source(s)...")
        self.status_var.set(f"Downloading {len(selected)} sources...")
        
        # Start download in thread
        thread = threading.Thread(target=self._download_thread, args=(selected, download_path))
        thread.start()
        
    def _download_thread(self, selected, download_path):
        """Download thread"""
        total = len(selected)
        successful = 0
        
        for i, name in enumerate(selected, 1):
            info = self.admx_sources[name]
            url = info.get('direct_url', info.get('url', ''))
            
            if not url:
                self.log(f"⚠️ No download URL for {name}")
                continue
            
            try:
                self.log(f"Downloading {name}...")
                self.progress_var.set((i / total) * 100)
                
                # Determine filename
                filename = os.path.basename(url) or f"{name.replace(' ', '_')}.zip"
                
                # Create subdirectories if organizing
                if self.organize_var.get():
                    publisher = info.get('publisher', 'Other')
                    category = info.get('category', 'Other')
                    save_dir = os.path.join(download_path, publisher, category)
                else:
                    save_dir = download_path
                
                os.makedirs(save_dir, exist_ok=True)
                save_path = os.path.join(save_dir, filename)
                
                # Download
                urllib.request.urlretrieve(url, save_path)
                self.log(f"✓ Downloaded: {save_path}")
                
                # Extract if archive
                if self.extract_var.get() and filename.endswith(('.zip', '.msi')):
                    self._extract_archive(save_path, save_dir)
                
                successful += 1
                
            except Exception as e:
                self.log(f"✗ Failed to download {name}: {str(e)}")
        
        self.progress_var.set(100)
        self.status_var.set(f"Downloaded {successful}/{total} sources")
        self.log(f"Download complete: {successful}/{total} successful")
        
        if successful > 0:
            messagebox.showinfo("Download Complete", f"Successfully downloaded {successful} ADMX source(s) to:\n{download_path}")
            
    def _extract_archive(self, archive_path, extract_dir):
        """Extract downloaded archive"""
        try:
            if archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                self.log(f"  Extracted: {archive_path}")
            elif archive_path.endswith('.msi'):
                # MSI extraction would require msiexec or third-party tools
                self.log(f"  Note: MSI file downloaded. Extract manually or install: {archive_path}")
        except Exception as e:
            self.log(f"  Warning: Could not extract {archive_path}: {str(e)}")
            
    def import_to_intune(self):
        """Import ADMX to Microsoft Intune"""
        self.log("Preparing Intune import...")
        
        instructions = """
To import ADMX templates into Microsoft Intune:

1. Open Microsoft Endpoint Manager admin center
   https://endpoint.microsoft.com

2. Navigate to:
   Devices > Configuration profiles > Import ADMX

3. Click "Import"

4. Select the downloaded ADMX files:
"""
        
        download_path = self.download_path_var.get()
        if os.path.exists(download_path):
            instructions += f"\n   Location: {download_path}\n"
            
            # Find ADMX files
            admx_files = []
            for root, dirs, files in os.walk(download_path):
                for file in files:
                    if file.endswith('.admx'):
                        admx_files.append(os.path.join(root, file))
            
            if admx_files:
                instructions += f"\n   Found {len(admx_files)} ADMX file(s)\n"
                instructions += "\n   Files:\n"
                for f in admx_files[:10]:  # Show first 10
                    instructions += f"   - {os.path.basename(f)}\n"
                if len(admx_files) > 10:
                    instructions += f"   ... and {len(admx_files) - 10} more\n"
        
        instructions += """
5. For each ADMX file:
   - Upload the .admx file
   - Upload corresponding .adml files (language files)
   - Select the appropriate category

6. Click "Create"

7. The ADMX templates will now be available in:
   Devices > Configuration profiles > Create profile > Templates

Note: ADMX ingestion in Intune may take a few minutes to process.
"""
        
        self.show_instructions("Import to Intune", instructions)
        
    def import_to_sysvol(self):
        """Import ADMX to SYSVOL for domain Group Policy"""
        sysvol_path = self.sysvol_var.get()
        
        if not sysvol_path or sysvol_path == "\\\\your-domain\\SYSVOL\\your-domain\\Policies\\PolicyDefinitions":
            messagebox.showerror("SYSVOL Path Required", "Please enter your domain's SYSVOL PolicyDefinitions path.")
            return
        
        self.log(f"Importing ADMX files to SYSVOL: {sysvol_path}")
        
        download_path = self.download_path_var.get()
        if not os.path.exists(download_path):
            messagebox.showerror("No Downloads", "Please download ADMX files first.")
            return
        
        # Find ADMX and ADML files
        admx_files = []
        adml_files = []
        
        for root, dirs, files in os.walk(download_path):
            for file in files:
                if file.endswith('.admx'):
                    admx_files.append(os.path.join(root, file))
                elif file.endswith('.adml'):
                    adml_files.append(os.path.join(root, file))
        
        if not admx_files:
            messagebox.showerror("No ADMX Files", "No ADMX files found in download directory.")
            return
        
        try:
            # Copy ADMX files to PolicyDefinitions
            admx_dest = sysvol_path
            os.makedirs(admx_dest, exist_ok=True)
            
            for admx in admx_files:
                shutil.copy2(admx, admx_dest)
                self.log(f"Copied: {os.path.basename(admx)}")
            
            # Copy ADML files to language subfolder (assuming en-US)
            adml_dest = os.path.join(sysvol_path, "en-US")
            os.makedirs(adml_dest, exist_ok=True)
            
            for adml in adml_files:
                # Try to match ADML to correct language folder
                lang = os.path.basename(os.path.dirname(adml))
                if len(lang) == 5 and lang[2] == '-':  # Format like en-US
                    lang_dest = os.path.join(sysvol_path, lang)
                    os.makedirs(lang_dest, exist_ok=True)
                    shutil.copy2(adml, lang_dest)
                else:
                    shutil.copy2(adml, adml_dest)
                self.log(f"Copied: {os.path.basename(adml)}")
            
            self.log(f"✓ Successfully imported {len(admx_files)} ADMX and {len(adml_files)} ADML files to SYSVOL")
            messagebox.showinfo("Import Complete", f"Imported {len(admx_files)} ADMX files to SYSVOL.\n\nGroup Policy will automatically use these templates.")
            
        except Exception as e:
            self.log(f"✗ Import failed: {str(e)}")
            messagebox.showerror("Import Failed", f"Failed to import to SYSVOL:\n{str(e)}")
            
    def install_locally(self):
        """Install ADMX templates on local machine"""
        self.log("Installing ADMX templates locally...")
        
        # Windows PolicyDefinitions paths
        if sys.platform == 'win32':
            policy_defs = [
                os.path.expandvars(r"%SystemRoot%\PolicyDefinitions"),
                os.path.expandvars(r"%SystemRoot%\PolicyDefinitions\en-US")
            ]
        else:
            messagebox.showerror("Windows Only", "Local installation is only available on Windows.")
            return
        
        download_path = self.download_path_var.get()
        if not os.path.exists(download_path):
            messagebox.showerror("No Downloads", "Please download ADMX files first.")
            return
        
        # Find ADMX and ADML files
        admx_files = []
        adml_files = []
        
        for root, dirs, files in os.walk(download_path):
            for file in files:
                if file.endswith('.admx'):
                    admx_files.append(os.path.join(root, file))
                elif file.endswith('.adml'):
                    adml_files.append(os.path.join(root, file))
        
        try:
            # Copy ADMX files
            for admx in admx_files:
                shutil.copy2(admx, policy_defs[0])
                self.log(f"Installed: {os.path.basename(admx)}")
            
            # Copy ADML files
            for adml in adml_files:
                lang = os.path.basename(os.path.dirname(adml))
                if len(lang) == 5 and lang[2] == '-':
                    lang_dest = os.path.join(policy_defs[0], lang)
                else:
                    lang_dest = policy_defs[1]
                
                os.makedirs(lang_dest, exist_ok=True)
                shutil.copy2(adml, lang_dest)
                self.log(f"Installed: {os.path.basename(adml)}")
            
            self.log(f"✓ Successfully installed {len(admx_files)} ADMX and {len(adml_files)} ADML files")
            messagebox.showinfo("Installation Complete", f"Installed {len(admx_files)} ADMX files locally.\n\nYou can now use these templates in Local Group Policy Editor (gpedit.msc).")
            
        except PermissionError:
            self.log("✗ Permission denied. Run as Administrator.")
            messagebox.showerror("Permission Denied", "Administrator privileges required to install ADMX files.\n\nRight-click and 'Run as administrator'.")
        except Exception as e:
            self.log(f"✗ Installation failed: {str(e)}")
            messagebox.showerror("Installation Failed", f"Failed to install:\n{str(e)}")
            
    def add_custom_source(self):
        """Add custom ADMX source"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Custom ADMX Source")
        dialog.geometry("500x400")        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Name:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        name_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=name_var, width=50).pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(dialog, text="Download URL:").pack(anchor=tk.W, padx=10, pady=(10, 0))
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
            values=["Operating System", "Browser", "Productivity", "Virtualization", "Communication", "Other"],
            width=47
        ).pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(dialog, text="Description:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        desc_text = scrolledtext.ScrolledText(dialog, height=5, width=50)
        desc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        def save_custom():
            name = name_var.get().strip()
            url = url_var.get().strip()
            publisher = publisher_var.get().strip() or "Custom"
            category = category_var.get()
            description = desc_text.get(1.0, tk.END).strip()
            
            if not name or not url:
                messagebox.showerror("Required Fields", "Name and URL are required.")
                return
            
            self.admx_sources[name] = {
                "url": url,
                "description": description,
                "publisher": publisher,
                "category": category
            }
            
            self.load_sources()
            self.log(f"Added custom source: {name}")
            dialog.destroy()
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Save", command=save_custom).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        
    def refresh_sources(self):
        """Refresh ADMX sources list"""
        self.load_sources()
        self.filter_sources()
        self.log("Refreshed ADMX sources list")
        
    def show_instructions(self, title, text):
        """Show instructions in a dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("600x500")
        
        text_widget = scrolledtext.ScrolledText(dialog, wrap=tk.WORD, font=('Segoe UI', 10))
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_widget.insert(tk.END, text)
        text_widget.config(state=tk.DISABLED)
        
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)
        
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
            with open(filename, 'w') as f:
                f.write(self.log_text.get(1.0, tk.END))
            self.status_var.set(f"Log saved to {filename}")
            
    def clear_log(self):
        """Clear log text"""
        self.log_text.delete(1.0, tk.END)
        self.status_var.set("Log cleared")
        
    def log(self, message):
        """Add message to log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.status_var.set(message[:100])
        

def main():
    """Main entry point"""
    root = tk.Tk()
    
    # Set DPI awareness on Windows
    if sys.platform == 'win32':
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
    
    app = ADMXManager(root)
    
    # Cleanup on exit
    def on_closing():
        try:
            shutil.rmtree(app.temp_dir, ignore_errors=True)
        except:
            pass
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
