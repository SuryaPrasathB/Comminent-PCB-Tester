import os
import sys

def get_app_data_dir():
    """
    Returns the application data directory in a user-writable location.
    Windows: %LOCALAPPDATA%/PRO-TRACE
    Other: ~/.pro-trace
    """
    if sys.platform == "win32":
        base_dir = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        base_dir = os.path.expanduser("~")
    
    app_dir = os.path.join(base_dir, "PRO-TRACE")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir

def get_log_dir():
    log_dir = os.path.join(get_app_data_dir(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def get_settings_path():
    return os.path.join(get_app_data_dir(), "user_settings.json")

def get_report_export_dir():
    # We can keep reports in the same app data dir or allow user to configure it.
    # By default, we'll use a subfolder in AppData to ensure it's writable.
    report_dir = os.path.join(get_app_data_dir(), "Reports")
    os.makedirs(report_dir, exist_ok=True)
    return report_dir
