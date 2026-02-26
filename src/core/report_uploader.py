import os
import threading
import time
import json
import importlib.util
from src.core.logger import logger

# Mock for development on non-Windows
class MockUploader:
    def __init__(self, folders, interval):
        self.folders = folders
        self.interval = interval
        self.running = False
        logger.info(f"MockUploader initialized with folders={folders}")

    def Run(self):
        logger.info("MockUploader started")
        self.running = True
        while self.running:
            time.sleep(1)
        logger.info("MockUploader stopped loop")

    def Stop(self):
        self.running = False
        logger.info("MockUploader Stop called")

class ReportUploader:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ReportUploader, cls).__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self.uploader_obj = None
        self.thread = None
        self.current_folder = None
        self.dll_loaded = False
        self.AutoLogUploaderType = None
        self.System = None

        # Try to load DLL
        # Verified against "CPL ENGINE LOG UPLOAD DLL" README:
        # - DLL: CplEngineClient.dll (Matches provided file in src/core/dlls)
        # - Class: AutoLogUploader
        # - Method: Run() (blocking), Stop()
        # - Constructor: AutoLogUploader(string folderPaths, int intervalSeconds)
        self._load_dll()

    def _load_dll(self):
        try:
            # Check if pythonnet is installed
            spec = importlib.util.find_spec("clr")
            if spec is None:
                logger.warning("pythonnet (clr) not found. Using MockUploader.")
                self.dll_loaded = False
                return

            import clr
            import System
            self.System = System

            # Path to DLL - user should place it in src/core/dlls/
            base_dir = os.path.dirname(os.path.abspath(__file__))
            dll_path = os.path.join(base_dir, "dlls", "CplEngineClient.dll")

            if os.path.exists(dll_path):
                # Use UnsafeLoadFrom to bypass network security checks (0x80131515)
                assembly = self.System.Reflection.Assembly.UnsafeLoadFrom(dll_path)
                self.AutoLogUploaderType = assembly.GetType("AutoLogUploader")
                self.dll_loaded = True
                logger.info(f"Loaded DLL from {dll_path}")
            else:
                logger.warning(f"DLL not found at {dll_path}. Using MockUploader.")
                self.dll_loaded = False

        except ImportError:
            logger.warning("pythonnet (clr) import failed. Using MockUploader.")
            self.dll_loaded = False
        except Exception as e:
            logger.error(f"Failed to load DLL: {e}")
            self.dll_loaded = False

    def start(self, folder_path):
        """
        Starts the uploader watching the given folder.
        If running with different folder, restarts.
        """
        if self.current_folder == folder_path and self.thread and self.thread.is_alive():
            logger.info("Uploader already running for this folder.")
            return

        self.stop()

        logger.info(f"Starting ReportUploader for {folder_path}")
        self.current_folder = folder_path

        try:
            folders_json = json.dumps([folder_path])
            interval = 5  # default interval

            if self.dll_loaded and self.AutoLogUploaderType and self.System:
                # Create instance
                # Constructor signature: AutoLogUploader(string folders, int interval)
                self.uploader_obj = self.System.Activator.CreateInstance(
                    self.AutoLogUploaderType,
                    self.System.String(folders_json),
                    self.System.Int32(interval)
                )
            else:
                self.uploader_obj = MockUploader(folders_json, interval)

            # Run in thread
            self.thread = threading.Thread(target=self._run_uploader_loop, daemon=True)
            self.thread.start()

        except Exception as e:
            logger.error(f"Failed to start uploader: {e}")
            self.uploader_obj = None

    def _run_uploader_loop(self):
        try:
            if self.uploader_obj:
                # Assuming Run() is blocking as per user example
                self.uploader_obj.Run()
        except Exception as e:
            logger.error(f"Uploader thread error: {e}")

    def stop(self):
        if self.uploader_obj:
            logger.info("Stopping ReportUploader...")
            try:
                self.uploader_obj.Stop()
            except Exception as e:
                logger.error(f"Error stopping uploader: {e}")

        if self.thread and self.thread.is_alive():
             self.thread.join(timeout=2)

        self.uploader_obj = None
        self.thread = None

        self.current_folder = None

    def update_folder(self, folder_path):
        """
        Updates the watched folder. If different from current, restarts the uploader.
        """
        if self.current_folder != folder_path:
            logger.info(f"Folder changed from {self.current_folder} to {folder_path}. Restarting uploader.")
            self.start(folder_path)
