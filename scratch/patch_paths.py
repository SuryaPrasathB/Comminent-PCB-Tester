import os
import glob
import re

root = r"d:\SURYA\.DEVELOPMENT\.PROJECTS\Project No XXX_PCB_Tester Comminent\Comminent-PCB-Tester"

def replace_in_file(filepath, pattern, replacement):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

# 1. Update main.py
replace_in_file(
    os.path.join(root, "main.py"),
    r'icon_path = os\.path\.join\("resources", "icons", "app_icon\.ico"\)',
    'from src.core.paths import get_resource_path\n    icon_path = get_resource_path("resources/icons/app_icon.ico")'
)

# 2. Update login_window.py
replace_in_file(
    os.path.join(root, "src/ui/login_window.py"),
    r'base_dir = os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\s+ui_path = os\.path\.join\(base_dir, "forms", "login\.ui"\)',
    'from src.core.paths import get_resource_path\n        ui_path = get_resource_path("src/ui/forms/login.ui")'
)

# 3. Update main_window.py
replace_in_file(
    os.path.join(root, "src/ui/main_window.py"),
    r'base_dir = os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\s+ui_path = os\.path\.join\(base_dir, "forms", "main_window\.ui"\)',
    'from src.core.paths import get_resource_path\n        ui_path = get_resource_path("src/ui/forms/main_window.ui")'
)

replace_in_file(
    os.path.join(root, "src/ui/main_window.py"),
    r"        if getattr\(sys, 'frozen', False\):\s+base_path = sys\._MEIPASS\s+else:\s+base_path = os\.path\.abspath\(\".\"\)\s+# Set Window Icon\s+icon_path = os\.path\.join\(base_path, \"resources\", \"icons\", \"app_icon\.ico\"\)\s+if os\.path\.exists\(icon_path\):\s+self\.setWindowIcon\(QIcon\(icon_path\)\)\s+# Set Sidebar Logo \(Prefer PNG, fallback to ICO\)\s+png_path = os\.path\.join\(base_path, \"resources\", \"icons\", \"app_icon\.png\"\)",
    """        from src.core.paths import get_resource_path

        # Set Window Icon
        icon_path = get_resource_path("resources/icons/app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Set Sidebar Logo (Prefer PNG, fallback to ICO)
        png_path = get_resource_path("resources/icons/app_icon.png")"""
)

# 4. Update views (debug, execution, project_config, results, settings, test_completion)
views = glob.glob(os.path.join(root, "src/ui/views/*.py"))
for view in views:
    filename = os.path.basename(view).replace(".py", ".ui")
    replace_in_file(
        view,
        r'base_dir = os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\s+ui_path = os\.path\.join\(base_dir, "..", "forms", "' + filename + r'"\)',
        f'from src.core.paths import get_resource_path\n        ui_path = get_resource_path("src/ui/forms/{filename}")'
    )
    replace_in_file(
        view,
        r'ui_file_path = os\.path\.join\(os\.path\.dirname\(__file__\), "..", "forms", "' + filename + r'"\)',
        f'from src.core.paths import get_resource_path\n        ui_file_path = get_resource_path("src/ui/forms/{filename}")'
    )

# 5. Update report_uploader.py
replace_in_file(
    os.path.join(root, "src/core/report_uploader.py"),
    r'base_dir = os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\s+template_path = os\.path\.join\(base_dir, "\.\.", "\.\.", "Report Export", "template", "active_template\.xlsx"\)',
    'from src.core.paths import get_resource_path\n                template_path = get_resource_path("Report Export/template/active_template.xlsx")'
)

print("Done patching files.")
