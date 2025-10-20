#!/usr/bin/env python3
"""
System Keep-Alive Manager for Long Running Audiobook Processing
Prevents system sleep, hibernation, and screen lock during processing.
"""

import os
import sys
import time
import threading
import ctypes
from ctypes import wintypes
import subprocess
from pathlib import Path


class WindowsPowerManager:
    """Manages Windows power settings to prevent system sleep."""
    
    # Windows API constants
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    ES_AWAYMODE_REQUIRED = 0x00000040
    
    def __init__(self):
        self.kernel32 = ctypes.windll.kernel32
        self.original_state = None
        self.keep_alive_active = False
        self.heartbeat_thread = None
        self._stop_heartbeat = threading.Event()
        
    def prevent_sleep(self):
        """Prevent system from sleeping or hibernating."""
        try:
            # Combine flags to keep system and display awake
            flags = (self.ES_CONTINUOUS | 
                    self.ES_SYSTEM_REQUIRED | 
                    self.ES_DISPLAY_REQUIRED)
            
            result = self.kernel32.SetThreadExecutionState(flags)
            if result:
                self.keep_alive_active = True
                print("[SUCCESS] System sleep prevention activated")
                
                # Start heartbeat to maintain the state
                self.start_heartbeat()
                return True
            else:
                print("[ERROR] Failed to prevent system sleep")
                return False

        except Exception as e:
            print(f"[ERROR] Error preventing sleep: {e}")
            return False

    def allow_sleep(self):
        """Restore normal system sleep behavior."""
        try:
            self.stop_heartbeat()
            
            result = self.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            if result:
                self.keep_alive_active = False
                print("[SUCCESS] System sleep prevention deactivated")
                return True
            else:
                print("[ERROR] Failed to restore sleep settings")
                return False

        except Exception as e:
            print(f"[ERROR] Error restoring sleep: {e}")
            return False

    def start_heartbeat(self):
        """Start heartbeat thread to maintain keep-alive state."""
        if not self.heartbeat_thread or not self.heartbeat_thread.is_alive():
            self._stop_heartbeat.clear()
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_worker, daemon=True)
            self.heartbeat_thread.start()
    
    def stop_heartbeat(self):
        """Stop heartbeat thread."""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self._stop_heartbeat.set()
            self.heartbeat_thread.join(timeout=2)
    
    def _heartbeat_worker(self):
        """Worker thread that periodically refreshes the keep-alive state."""
        while not self._stop_heartbeat.is_set():
            if self.keep_alive_active:
                try:
                    # Refresh the execution state every 30 seconds
                    flags = (self.ES_CONTINUOUS | 
                            self.ES_SYSTEM_REQUIRED | 
                            self.ES_DISPLAY_REQUIRED)
                    self.kernel32.SetThreadExecutionState(flags)
                except Exception:
                    pass
            
            # Wait 30 seconds or until stop signal
            self._stop_heartbeat.wait(30)


class ProcessingSession:
    """Manages a long-running processing session with power management."""
    
    def __init__(self, session_name="audiobook_processing"):
        self.session_name = session_name
        self.power_manager = WindowsPowerManager()
        self.start_time = time.time()
        self.session_id = time.strftime("%Y%m%d_%H%M%S")
        self.log_file = Path(f"logs/session_{self.session_id}.log")
        
        # Ensure logs directory exists
        self.log_file.parent.mkdir(exist_ok=True)
        
    def start_session(self):
        """Start a protected processing session."""
        print(f"[START] STARTING LONG-RUNNING SESSION")
        print(f"Session ID: {self.session_id}")
        print(f"Log file: {self.log_file}")
        print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)
        
        # Log session start
        self.log_message("SESSION_START", f"Session {self.session_id} started")
        
        # Activate power management
        if self.power_manager.prevent_sleep():
            self.log_message("POWER_MGMT", "System sleep prevention activated")
            return True
        else:
            self.log_message("POWER_ERROR", "Failed to activate sleep prevention")
            return False
    
    def end_session(self):
        """End the processing session and restore normal power settings."""
        duration = time.time() - self.start_time
        duration_str = f"{duration/3600:.1f} hours" if duration > 3600 else f"{duration/60:.1f} minutes"
        
        print(f"\n[END] ENDING SESSION")
        print(f"Duration: {duration_str}")
        print(f"End time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Restore power settings
        if self.power_manager.allow_sleep():
            self.log_message("POWER_MGMT", "System sleep settings restored")
        
        self.log_message("SESSION_END", f"Session completed after {duration_str}")
        print(f"[LOG] Session log saved: {self.log_file}")
    
    def log_message(self, category, message):
        """Log a message to the session log file."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {category}: {message}\n"
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"[WARNING] Failed to write to log: {e}")
    
    def get_session_status(self):
        """Get current session status."""
        duration = time.time() - self.start_time
        return {
            'session_id': self.session_id,
            'duration_seconds': duration,
            'keep_alive_active': self.power_manager.keep_alive_active,
            'log_file': str(self.log_file)
        }
    
    def __enter__(self):
        """Context manager entry."""
        self.start_session()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type:
            self.log_message("ERROR", f"Session ended with error: {exc_val}")
        self.end_session()


def setup_unattended_mode():
    """Set up environment for unattended processing."""
    print("[SETUP] SETTING UP UNATTENDED MODE")
    print("=" * 40)
    
    # Set environment variable for auto-confirmation
    os.environ['AUDIOBOOK_AUTO_CONFIRM'] = '1'
    print("[SUCCESS] Auto-confirmation enabled")
    
    # Create process monitoring script
    monitor_script = Path("monitor_processing.py")
    if not monitor_script.exists():
        create_monitoring_script()
    
    print("[SUCCESS] Process monitoring available")
    print("[SUCCESS] Unattended mode ready")


def create_monitoring_script():
    """Create a script to monitor processing progress."""
    script_content = '''#!/usr/bin/env python3
"""Process monitoring script for unattended audiobook processing."""

import psutil
import time
from pathlib import Path

def monitor_processing():
    """Monitor processing and provide status updates."""
    print("[MONITOR] PROCESSING MONITOR")
    print("=" * 30)
    
    while True:
        # Check for Python processes
        python_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
            try:
                if 'python' in proc.info['name'].lower():
                    python_processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if python_processes:
            print(f"\\n[MONITOR] Active Python processes: {len(python_processes)}")
            for proc in python_processes:
                print(f"   PID {proc['pid']}: CPU {proc['cpu_percent']:.1f}% | RAM {proc['memory_info'].rss/1024/1024:.1f}MB")
        
        # Check log files for activity
        log_files = list(Path("logs").glob("*.log")) if Path("logs").exists() else []
        if log_files:
            latest_log = max(log_files, key=lambda f: f.stat().st_mtime)
            size_mb = latest_log.stat().st_size / (1024 * 1024)
            print(f"[LOG] Latest log: {latest_log.name} ({size_mb:.1f}MB)")
        
        print(f"[TIME] {time.strftime('%H:%M:%S')} - Monitoring... (Ctrl+C to stop)")
        time.sleep(30)  # Update every 30 seconds

if __name__ == "__main__":
    try:
        monitor_processing()
    except KeyboardInterrupt:
        print("\\n[STOP] Monitor stopped")
'''
    
    with open("monitor_processing.py", 'w', encoding='utf-8') as f:
        f.write(script_content)


def main():
    """Demonstrate the power management system."""
    print("[POWER] AUDIOBOOK PROCESSOR - POWER MANAGEMENT TEST")
    print("=" * 50)
    
    # Test the power management
    with ProcessingSession("test_session") as session:
        print("\n[TIME] Simulating long processing (10 seconds)...")
        print("[INFO] During this time:")
        print("   - System should not sleep")
        print("   - Screen should stay active")
        print("   - Processing continues uninterrupted")
        
        for i in range(10):
            print(f"   Processing step {i+1}/10...")
            session.log_message("PROCESSING", f"Completed step {i+1}")
            time.sleep(1)
        
        status = session.get_session_status()
        print(f"\n[STATUS] Session Status:")
        print(f"   Duration: {status['duration_seconds']:.1f} seconds")
        print(f"   Keep-alive: {'Active' if status['keep_alive_active'] else 'Inactive'}")
        print(f"   Log file: {status['log_file']}")


if __name__ == "__main__":
    # Check if running on Windows
    if sys.platform != "win32":
        print("[ERROR] This power management system is designed for Windows")
        sys.exit(1)
    
    main()