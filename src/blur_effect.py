"""
Windows DWM Blur/Acrylic Effect Module

Provides functions to enable Windows 10/11 blur effects on Qt windows.
Uses ctypes to call Windows DWM (Desktop Window Manager) APIs.

Supports:
- Windows 11: Mica, Acrylic, Tabbed effects
- Windows 10: Acrylic blur (limited)
- Fallback: Returns False if unsupported
"""

import ctypes
from ctypes import wintypes
import sys

# Only available on Windows
if sys.platform == 'win32':
    dwmapi = ctypes.windll.dwmapi
    user32 = ctypes.windll.user32
else:
    dwmapi = None
    user32 = None

# DWM Window Attributes
DWMWA_NCRENDERING_POLICY = 2
DWMWA_TRANSITIONS_FORCEDISABLED = 3
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38

# Window corner preferences (Windows 11)
DWMWCP_DEFAULT = 0
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWCP_ROUNDSMALL = 3

# System backdrop types (Windows 11)
DWMSBT_AUTO = 0
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2      # Mica
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
DWMSBT_TABBEDWINDOW = 4     # Mica Alt

# Accent state for Windows 10 acrylic
class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]

class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(ACCENT_POLICY)),
        ("SizeOfData", ctypes.c_size_t),
    ]

# Accent states
ACCENT_DISABLED = 0
ACCENT_ENABLE_GRADIENT = 1
ACCENT_ENABLE_TRANSPARENTGRADIENT = 2
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
ACCENT_ENABLE_HOSTBACKDROP = 5

# Window composition attribute
WCA_ACCENT_POLICY = 19


def get_windows_version():
    """Get Windows major build number."""
    try:
        version = sys.getwindowsversion()
        return version.build
    except:
        return 0


def enable_dark_mode(hwnd):
    """Enable dark mode title bar (Windows 10 1809+)."""
    if not dwmapi:
        return False

    try:
        value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
        return True
    except:
        return False


def set_window_corners(hwnd, rounded=True):
    """Set window corner style (Windows 11 only)."""
    if not dwmapi:
        return False

    build = get_windows_version()
    if build < 22000:  # Windows 11 minimum build
        return False

    try:
        preference = DWMWCP_ROUND if rounded else DWMWCP_DONOTROUND
        value = ctypes.c_int(preference)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
        return True
    except:
        return False


def enable_mica(hwnd):
    """Enable Mica effect (Windows 11 22H2+)."""
    if not dwmapi:
        return False

    build = get_windows_version()
    if build < 22621:  # Windows 11 22H2
        return False

    try:
        value = ctypes.c_int(DWMSBT_MAINWINDOW)
        result = dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
        return result == 0
    except:
        return False


def enable_acrylic_win11(hwnd):
    """Enable Acrylic effect (Windows 11)."""
    if not dwmapi:
        return False

    build = get_windows_version()
    if build < 22000:
        return False

    try:
        value = ctypes.c_int(DWMSBT_TRANSIENTWINDOW)
        result = dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(value),
            ctypes.sizeof(value)
        )
        return result == 0
    except:
        return False


def enable_acrylic_win10(hwnd, color=0x20000000):
    """
    Enable Acrylic blur effect (Windows 10).

    Args:
        hwnd: Window handle
        color: ARGB color (default: semi-transparent black)
               Format: 0xAARRGGBB
    """
    if not user32:
        return False

    build = get_windows_version()
    if build < 17134:  # Windows 10 1803
        return False

    try:
        SetWindowCompositionAttribute = user32.SetWindowCompositionAttribute
        SetWindowCompositionAttribute.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)
        ]
        SetWindowCompositionAttribute.restype = ctypes.c_bool

        accent = ACCENT_POLICY()
        accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.GradientColor = color
        accent.AccentFlags = 2  # Enable color

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.pointer(accent)
        data.SizeOfData = ctypes.sizeof(accent)

        return SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
    except:
        return False


def enable_blur(hwnd, effect='auto', color=0x20000000):
    """
    Enable blur effect on a window.

    Args:
        hwnd: Window handle (from Qt's winId())
        effect: 'auto', 'mica', 'acrylic', or 'blur'
        color: Background color for acrylic (ARGB format)

    Returns:
        True if effect was applied, False otherwise
    """
    if not dwmapi:
        return False

    # Convert Qt winId to int if needed
    if hasattr(hwnd, '__int__'):
        hwnd = int(hwnd)

    # Enable dark mode for better integration
    enable_dark_mode(hwnd)

    # Set rounded corners on Windows 11
    set_window_corners(hwnd, rounded=True)

    build = get_windows_version()

    if effect == 'auto':
        # Try effects in order of preference
        if build >= 22621:  # Windows 11 22H2+
            if enable_acrylic_win11(hwnd):
                return True
        if build >= 22000:  # Windows 11
            if enable_acrylic_win11(hwnd):
                return True
        if build >= 17134:  # Windows 10 1803+
            if enable_acrylic_win10(hwnd, color):
                return True
        return False

    elif effect == 'mica':
        return enable_mica(hwnd)

    elif effect == 'acrylic':
        if build >= 22000:
            return enable_acrylic_win11(hwnd)
        else:
            return enable_acrylic_win10(hwnd, color)

    elif effect == 'blur':
        return enable_acrylic_win10(hwnd, color)

    return False


def disable_blur(hwnd):
    """Disable blur effects on a window."""
    if not dwmapi:
        return False

    if hasattr(hwnd, '__int__'):
        hwnd = int(hwnd)

    build = get_windows_version()

    try:
        if build >= 22000:
            value = ctypes.c_int(DWMSBT_NONE)
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_SYSTEMBACKDROP_TYPE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )

        if user32:
            accent = ACCENT_POLICY()
            accent.AccentState = ACCENT_DISABLED

            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = WCA_ACCENT_POLICY
            data.Data = ctypes.pointer(accent)
            data.SizeOfData = ctypes.sizeof(accent)

            SetWindowCompositionAttribute = user32.SetWindowCompositionAttribute
            SetWindowCompositionAttribute(hwnd, ctypes.byref(data))

        return True
    except:
        return False
