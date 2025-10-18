#!/usr/bin/env python3
"""
Audiobook Processor GUI - Simple cross-platform interface for Windows and Mac
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import subprocess
import sys
import os
from pathlib import Path
import queue
import time


class ToolTip:
    """Simple tooltip class for tkinter widgets."""
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        
    def showtip(self):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + cy + self.widget.winfo_rooty() + 25
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                        font=("Arial", "8", "normal"))
        label.pack(ipadx=1)
        
    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class AudiobookProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Audiobook Processor")
        self.root.geometry("800x600")
        
        # Set icon and style
        self.setup_style()
        
        # Queue for thread communication
        self.output_queue = queue.Queue()
        
        # Variables
        self.selected_folder = tk.StringVar()
        self.destination_folder = tk.StringVar()
        self.use_custom_destination = tk.BooleanVar(value=False)
        self.compress_enabled = tk.BooleanVar(value=True)
        self.delete_enabled = tk.BooleanVar(value=False)
        self.bitrate_var = tk.StringVar(value="32k")
        self.format_var = tk.StringVar(value="m4a")
        self.long_running_mode = tk.BooleanVar(value=False)
        self.processing_mode = tk.StringVar(value="standard")  # Default to standard
        self.processing = False
        self.current_process = None
        
        # Try to import power management
        try:
            from power_manager import ProcessingSession
            self.power_management_available = True
        except ImportError:
            self.power_management_available = False
        
        self.create_widgets()
        self.update_output()
        
    def setup_style(self):
        """Setup GUI styling for cross-platform compatibility."""
        style = ttk.Style()
        
        # Use platform-appropriate theme
        if sys.platform == "darwin":  # macOS
            style.theme_use('aqua')
        elif sys.platform == "win32":  # Windows
            style.theme_use('winnative')
        else:  # Linux/other
            style.theme_use('clam')
            
    def create_widgets(self):
        """Create the main GUI elements."""
        # Create canvas and scrollbars for main window scrolling
        self.main_canvas = tk.Canvas(self.root, highlightthickness=0)
        self.v_scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.main_canvas.yview)
        self.h_scrollbar = ttk.Scrollbar(self.root, orient="horizontal", command=self.main_canvas.xview)
        
        self.main_canvas.configure(yscrollcommand=self.v_scrollbar.set, xscrollcommand=self.h_scrollbar.set)
        
        # Pack scrollbars and canvas
        self.v_scrollbar.pack(side="right", fill="y")
        self.h_scrollbar.pack(side="bottom", fill="x")
        self.main_canvas.pack(side="left", fill="both", expand=True)
        
        # Create main frame inside canvas
        self.main_frame = ttk.Frame(self.main_canvas, padding="10")
        self.main_canvas_frame = self.main_canvas.create_window((0, 0), window=self.main_frame, anchor="nw")
        
        # Configure canvas scrolling
        self.main_frame.bind("<Configure>", self.on_frame_configure)
        self.main_canvas.bind("<Configure>", self.on_canvas_configure)
        
        # Bind mousewheel to canvas
        self.main_canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        
        # Configure grid weights
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(8, weight=1)
        
        # Title
        title_label = ttk.Label(self.main_frame, text="[AUDIO] Audiobook Processor", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=(0, 10))
        
        # File structure info
        info_frame = ttk.LabelFrame(self.main_frame, text="[FOLDER] Folder Structure Tips", padding="10")
        info_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 15))
        
        info_text = ("- Folder names become the audiobook title and album name\n"
                     "- Parent folder names are used for series organization\n"
                     "- Single MP3 files: Metadata applied without combining\n"
                     "- Parent folders: Processes all book subfolders individually\n"
                     "- Author information: Automatically extracted from the first MP3 file's metadata (TPE1/artist tag)\n"
                     "  If no cover art is found, uses metadata from the first file; preserves existing author info\n"
                     "- Example: 'HARRY POTTER SERIES/1 The Philosophers Stone'\n"
                     "  -> Title: 'The Philosophers Stone'  -> Series: 'HARRY POTTER SERIES : The Philosophers Stone'")
        
        info_label = ttk.Label(info_frame, text=info_text, font=("Arial", 9), 
                              foreground="gray", justify=tk.LEFT)
        info_label.pack(anchor=tk.W)
        
        # Red warning text about number removal
        warning_text = ("[WARNING] IMPORTANT: Leading numbers are automatically removed from title names!\n"
                       "Example: '1 The Philosophers Stone' becomes 'The Philosophers Stone' in the final audiobook title")
        warning_label = ttk.Label(info_frame, text=warning_text, font=("Arial", 9, "bold"), 
                                 foreground="red", justify=tk.LEFT)
        warning_label.pack(anchor=tk.W, pady=(10, 0))
        
        # Processing Mode Selection
        mode_frame = ttk.LabelFrame(self.main_frame, text="Processing Mode", padding="10")
        mode_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        mode_frame.columnconfigure(1, weight=1)
        
        ttk.Radiobutton(mode_frame, text="[STANDARD] Standard (Compatible)", 
                       variable=self.processing_mode, value="standard").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(mode_frame, text="[START] Parallel (Faster)", 
                       variable=self.processing_mode, value="parallel").grid(row=0, column=1, sticky=tk.W)
        
        # Performance info
        perf_info = ttk.Label(mode_frame, text="Parallel mode is ~15% faster and uses multiple CPU cores", 
                             font=("Arial", 9), foreground="gray")
        perf_info.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        # Folder selection  
        folder_label = ttk.Label(self.main_frame, text="Select Folder:")
        folder_label.grid(row=3, column=0, sticky=tk.W, pady=5)
        
        # Add tooltip for folder selection
        self.create_tooltip(folder_label, 
                           "Select a folder containing MP3 files.\n" +
                           "- Single MP3: Applies metadata without combining\n" +
                           "- Multiple MP3s: Combines files into one audiobook\n" +
                           "- Parent folder: Processes all MP3 subfolders individually")
        
        folder_frame = ttk.Frame(self.main_frame)
        folder_frame.grid(row=3, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        folder_frame.columnconfigure(0, weight=1)
        
        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.selected_folder, width=50)
        self.folder_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        browse_btn = ttk.Button(folder_frame, text="Browse", command=self.browse_folder)
        browse_btn.grid(row=0, column=1)
        
        # Destination folder option
        dest_checkbox = ttk.Checkbutton(self.main_frame, text="Use custom output destination:", 
                                       variable=self.use_custom_destination, 
                                       command=self.on_destination_changed)
        dest_checkbox.grid(row=4, column=0, sticky=tk.W, pady=(10, 5), columnspan=3)
        
        self.dest_frame = ttk.Frame(self.main_frame)
        self.dest_frame.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        self.dest_frame.columnconfigure(0, weight=1)
        
        self.dest_entry = ttk.Entry(self.dest_frame, textvariable=self.destination_folder, 
                                   width=50, state='disabled')
        self.dest_entry.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        self.dest_browse_btn = ttk.Button(self.dest_frame, text="Browse", 
                                         command=self.browse_destination, state='disabled')
        self.dest_browse_btn.grid(row=0, column=1)
        
        # Options frame
        options_frame = ttk.LabelFrame(self.main_frame, text="Options", padding="10")
        options_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        options_frame.columnconfigure(1, weight=1)
        
        # Compression checkbox
        compress_cb = ttk.Checkbutton(options_frame, text="Compress original files to ZIP", 
                                     variable=self.compress_enabled, command=self.on_compress_changed)
        compress_cb.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Delete originals checkbox
        self.delete_cb = ttk.Checkbutton(options_frame, text="[DELETE] [WARNING] Delete original files after compression",
                                        variable=self.delete_enabled, state='normal')
        self.delete_cb.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        # Format selection
        ttk.Label(options_frame, text="Output Format:").grid(row=2, column=0, sticky=tk.W, pady=2)
        format_frame = ttk.Frame(options_frame)
        format_frame.grid(row=2, column=1, sticky=tk.W, pady=2)
        
        format_m4a_rb = ttk.Radiobutton(format_frame, text="M4A (smaller, modern)", 
                                       variable=self.format_var, value="m4a", 
                                       command=self.on_format_changed)
        format_m4a_rb.pack(side=tk.LEFT, padx=(0, 20))
        
        format_mp3_rb = ttk.Radiobutton(format_frame, text="MP3 (faster, compatible)", 
                                       variable=self.format_var, value="mp3",
                                       command=self.on_format_changed)
        format_mp3_rb.pack(side=tk.LEFT)
        
        # Long running mode checkbox
        long_running_cb = ttk.Checkbutton(options_frame, text="[POWER] Long running mode (prevents system sleep)", 
                                         variable=self.long_running_mode)
        long_running_cb.grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        if not self.power_management_available:
            long_running_cb.config(state='disabled')
            self.create_tooltip(long_running_cb, "Power management not available\nInstall power_manager.py for this feature")
        else:
            self.create_tooltip(long_running_cb, 
                               "Prevents system sleep/hibernation during processing\n" +
                               "Ideal for large batch jobs and overnight processing")
        
        # Bitrate selection
        ttk.Label(options_frame, text="Bitrate:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.bitrate_combo = ttk.Combobox(options_frame, textvariable=self.bitrate_var, 
                                         values=["32k", "64k", "128k", "192k"], width=10)
        self.bitrate_combo.grid(row=4, column=1, sticky=tk.W, pady=2)
        self.bitrate_combo.state(['readonly'])
        
        # Control buttons
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(row=7, column=0, columnspan=3, pady=10)
        
        self.process_btn = ttk.Button(button_frame, text="[START] Process Audiobooks", 
                                     command=self.start_processing)
        self.process_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(button_frame, text="[STOP] Stop Processing",
                                   command=self.stop_processing, state='disabled')
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.clear_btn = ttk.Button(button_frame, text="[CLEAR] Clear Output", 
                                   command=self.clear_output)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Output area
        output_frame = ttk.LabelFrame(self.main_frame, text="Processing Output", padding="5")
        output_frame.grid(row=8, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)
        
        self.output_text = scrolledtext.ScrolledText(output_frame, width=80, height=20, 
                                                    wrap=tk.WORD, font=("Consolas", 9))
        self.output_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Progress bar
        self.progress = ttk.Progressbar(self.main_frame, mode='indeterminate')
        self.progress.grid(row=9, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(10, 0))
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=10, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))
        
    def on_frame_configure(self, event):
        """Update scroll region when frame size changes."""
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        
    def on_canvas_configure(self, event):
        """Update canvas window width when canvas size changes."""
        self.main_canvas.itemconfig(self.main_canvas_frame, width=event.width)
        
    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        self.main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
    def browse_folder(self):
        """Open folder browser dialog."""
        folder = filedialog.askdirectory(title="Select Audiobook Folder")
        if folder:
            self.selected_folder.set(folder)
    
    def browse_destination(self):
        """Open destination folder browser dialog."""
        folder = filedialog.askdirectory(title="Select Output Destination Folder")
        if folder:
            self.destination_folder.set(folder)
    
    def on_destination_changed(self):
        """Handle custom destination checkbox changes."""
        if self.use_custom_destination.get():
            self.dest_entry.config(state='normal')
            self.dest_browse_btn.config(state='normal')
        else:
            self.dest_entry.config(state='disabled')
            self.dest_browse_btn.config(state='disabled')
            self.destination_folder.set("")
            
    def on_compress_changed(self):
        """Handle compression checkbox changes."""
        # Delete checkbox is now always available regardless of compression setting
        pass
            
    def on_format_changed(self):
        """Handle format selection changes."""
        # Update bitrate recommendations based on format
        if self.format_var.get() == "m4a":
            # M4A typically uses lower bitrates due to better compression
            self.bitrate_combo.configure(values=["32k", "64k", "128k", "192k"])
            if self.bitrate_var.get() not in ["32k", "64k", "128k", "192k"]:
                self.bitrate_var.set("64k")
        else:  # MP3
            # MP3 typically uses higher bitrates for good quality
            self.bitrate_combo.configure(values=["64k", "128k", "192k", "256k", "320k"])
            if self.bitrate_var.get() not in ["64k", "128k", "192k", "256k", "320k"]:
                self.bitrate_var.set("128k")
            
    def start_processing(self):
        """Start the audiobook processing in a separate thread."""
        if not self.selected_folder.get():
            messagebox.showerror("Error", "Please select a folder first!")
            return
            
        if not os.path.exists(self.selected_folder.get()):
            messagebox.showerror("Error", "Selected folder does not exist!")
            return
            
        # Check if folder contains MP3 files
        folder_path = Path(self.selected_folder.get())
        mp3_files = list(folder_path.rglob("*.mp3"))
        if not mp3_files:
            messagebox.showwarning("Warning", "No MP3 files found in selected folder!")
            return
            
        self.processing = True
        self.process_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.progress.start()
        self.status_var.set("Processing...")
        
        # Start processing thread
        self.processing_thread = threading.Thread(target=self.run_processing, daemon=True)
        self.processing_thread.start()
        
    def run_processing(self):
        """Run the audiobook processor in a separate thread."""
        try:
            # Initialize power management if enabled
            session = None
            if self.long_running_mode.get() and self.power_management_available:
                from power_manager import ProcessingSession
                session = ProcessingSession("gui_processing")
                session.start_session()
                self.output_queue.put("[POWER] Long running mode activated - system sleep prevented\n")
            
            # Build command - use single processor with optional parallel flag
            cmd = [sys.executable, "audiobook_processor.py", "batch", self.selected_folder.get()]
            
            # Add parallel flag if parallel mode is selected
            if self.processing_mode.get() == "parallel":
                cmd.append("--parallel")
            
            # Add destination folder if specified
            if self.use_custom_destination.get() and self.destination_folder.get():
                cmd.extend(["--destination", self.destination_folder.get()])
            
            # Add format option
            cmd.extend(["--format", self.format_var.get()])
            
            if self.compress_enabled.get():
                cmd.append("--compress-originals")
                
            if self.delete_enabled.get():
                cmd.append("--delete-originals")
                
            cmd.extend(["--bitrate", self.bitrate_var.get()])
            
            # Add auto-confirm flag
            env = os.environ.copy()
            env["AUDIOBOOK_AUTO_CONFIRM"] = "1"
            
            self.output_queue.put(f"[START] Starting processing: {' '.join(cmd)}\n")
            self.output_queue.put(f"[CONFIG] Processing Mode: {self.processing_mode.get().title()}\n")
            self.output_queue.put(f"[FOLDER] Source: {self.selected_folder.get()}\n")
            if self.use_custom_destination.get() and self.destination_folder.get():
                self.output_queue.put(f"[DESTINATION] Destination: {self.destination_folder.get()}\n")
            self.output_queue.put(f"[CONFIG] Options: Format={self.format_var.get().upper()}, Bitrate={self.bitrate_var.get()}, Compress={self.compress_enabled.get()}, Delete={self.delete_enabled.get()}\n")
            self.output_queue.put("=" * 60 + "\n")
            
            # Start process
            self.current_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                env=env,
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            # Read output line by line
            while True:
                output = self.current_process.stdout.readline()
                if output == '' and self.current_process.poll() is not None:
                    break
                if output:
                    self.output_queue.put(output)
                    
            # Get return code
            return_code = self.current_process.poll()
            
            if return_code == 0:
                self.output_queue.put("\n[SUCCESS] Processing completed successfully!\n")
                self.output_queue.put("STATUS:SUCCESS")
            else:
                self.output_queue.put(f"\n[ERROR] Processing failed with code {return_code}\n")
                self.output_queue.put("STATUS:ERROR")
                
        except Exception as e:
            self.output_queue.put(f"\n[ERROR] Error: {str(e)}\n")
            self.output_queue.put("STATUS:ERROR")
            
        finally:
            # Clean up power management session
            if 'session' in locals() and session:
                session.end_session()
                self.output_queue.put("[POWER] Long running mode deactivated - normal power settings restored\n")
            
            self.output_queue.put("STATUS:DONE")
            
    def stop_processing(self):
        """Stop the current processing."""
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.terminate()
                self.output_queue.put("\n[STOP] Processing stopped by user\n")
            except:
                pass
                
        self.processing = False
        self.process_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.progress.stop()
        self.status_var.set("Stopped")
        
    def clear_output(self):
        """Clear the output text area."""
        self.output_text.delete(1.0, tk.END)
        
    def update_output(self):
        """Update the output text area with queued messages."""
        try:
            while True:
                message = self.output_queue.get_nowait()
                
                if message.startswith("STATUS:"):
                    status = message.split(":", 1)[1]
                    if status == "SUCCESS":
                        self.status_var.set("[SUCCESS] Completed successfully!")
                        messagebox.showinfo("Success", "Audiobook processing completed successfully!")
                    elif status == "ERROR":
                        self.status_var.set("[ERROR] Processing failed")
                        messagebox.showerror("Error", "Processing failed. Check output for details.")
                    elif status == "DONE":
                        self.processing = False
                        self.process_btn.config(state='normal')
                        self.stop_btn.config(state='disabled')
                        self.progress.stop()
                        if not self.status_var.get().startswith(("[SUCCESS]", "[ERROR]")):
                            self.status_var.set("Ready")
                else:
                    self.output_text.insert(tk.END, message)
                    self.output_text.see(tk.END)
                    
        except queue.Empty:
            pass
            
        # Schedule next update
        self.root.after(100, self.update_output)
        
    def create_tooltip(self, widget, text):
        """Create a tooltip for a widget."""
        tooltip = ToolTip(widget, text)
        
        def on_enter(event):
            tooltip.showtip()
            
        def on_leave(event):
            tooltip.hidetip()
            
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)


def main():
    """Main function to run the GUI."""
    # Check if audiobook_processor.py exists
    processor_path = Path("audiobook_processor.py")
    if not processor_path.exists():
        print("Error: audiobook_processor.py not found in current directory!")
        print("Please make sure both files are in the same folder.")
        return
        
    root = tk.Tk()
    app = AudiobookProcessorGUI(root)
    
    # Handle window closing
    def on_closing():
        if app.processing:
            if messagebox.askokcancel("Quit", "Processing is still running. Do you want to stop and quit?"):
                app.stop_processing()
                root.destroy()
        else:
            root.destroy()
            
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    # Center window on screen
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    
    root.mainloop()


if __name__ == "__main__":
    main()