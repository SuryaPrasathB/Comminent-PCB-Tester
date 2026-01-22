import qtawesome as qta
from PySide6.QtGui import QIcon

class IconHelper:
    """
    Centralized Icon Management using QtAwesome (FontAwesome 5)
    """

    @staticmethod
    def get(name: str, color=None) -> QIcon:
        """
        Get an icon by name.
        Example: IconHelper.get('fa5s.home', color='white')
        """
        # Default color based on common usage, but configurable
        if color is None:
            color = "#555555" # Neutral gray

        # Check if it is a predefined key
        if name in IconHelper.ICONS:
            name = IconHelper.ICONS[name]

        return qta.icon(name, color=color)

    @staticmethod
    def apply_icon(widget, icon_name, color=None):
        widget.setIcon(IconHelper.get(icon_name, color))

    # ---- PREDEFINED ICONS (Mapping for consistency) ----
    ICONS = {
        "dashboard": "fa5s.tachometer-alt",
        "project": "fa5s.folder-open",
        "execution": "fa5s.play-circle",
        "results": "fa5s.chart-bar",
        "debug": "fa5s.bug",
        "logs": "fa5s.file-alt",
        "settings": "fa5s.cog",
        "user": "fa5s.user-circle",
        "logout": "fa5s.sign-out-alt",
        "theme_light": "fa5s.sun",
        "theme_dark": "fa5s.moon",
        "save": "fa5s.save",
        "delete": "fa5s.trash",
        "refresh": "fa5s.sync",
        "start": "fa5s.play",
        "stop": "fa5s.stop",
        "check": "fa5s.check",
        "times": "fa5s.times",
        "arrow_up": "fa5s.arrow-up",
        "arrow_down": "fa5s.arrow-down",
        "search": "fa5s.search",
        "pdf": "fa5s.file-pdf",
        "excel": "fa5s.file-excel",
        "lock": "fa5s.lock"
    }
