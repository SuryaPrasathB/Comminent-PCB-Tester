# src/core/crash_handler.py
import sys
import traceback
import logging
import os
from datetime import datetime

def install_crash_handler():
    """
    Installs a global exception hook to capture unhandled exceptions.
    These exceptions often cause silent application closes.
    """
    from src.core.paths import get_log_dir
    log_dir = get_log_dir()
    
    def exception_handler(exctype, value, tb, thread_info=None):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_msg = "".join(traceback.format_exception(exctype, value, tb))
        
        thread_name = thread_info.name if thread_info else "MainThread"
        
        # 1. Print to console
        print("\n" + "="*60)
        print(f"FATAL ERROR AT {timestamp} in thread [{thread_name}]")
        print(error_msg)
        print("="*60 + "\n")
        
        # 2. Log to a dedicated crash file
        crash_file = os.path.join(log_dir, f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{thread_name}.log")
        try:
            with open(crash_file, "w") as f:
                f.write(f"Crash Timestamp: {timestamp}\n")
                f.write(f"Thread: {thread_name}\n")
                f.write("="*60 + "\n")
                f.write(error_msg)
                f.write("="*60 + "\n")
        except:
            pass

        # 3. Log to the main logger if possible
        try:
            from src.core.logger import logger
            logger.error(f"FATAL UNHANDLED EXCEPTION in {thread_name}: {value}")
            logger.error(error_msg)
        except:
            pass
            
    def sys_hook(exctype, value, tb):
        exception_handler(exctype, value, tb)
        sys.__excepthook__(exctype, value, tb)

    def thread_hook(args):
        exception_handler(args.exc_type, args.exc_value, args.exc_traceback, args.thread)

    sys.excepthook = sys_hook
    
    import threading
    if hasattr(threading, 'excepthook'):
        threading.excepthook = thread_hook
        
    print("[CRASH HANDLER] Global and Thread exception hooks installed.")
