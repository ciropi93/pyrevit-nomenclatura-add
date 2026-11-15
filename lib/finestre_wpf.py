# -*- coding: utf-8 -*-
"""Piccoli aiuti per le finestre WPF sopra Revit (palette, lettere E/I, avvisi)."""
import clr
clr.AddReference("System.Drawing")
clr.AddReference("PresentationFramework")

from System import IntPtr
from System.Windows.Interop import WindowInteropHelper


def scala_dpi():
    """Pixel fisici per unita' WPF (1.0 a 96 dpi)."""
    from System.Drawing import Graphics
    g = Graphics.FromHwnd(IntPtr.Zero)
    try:
        return g.DpiX / 96.0
    finally:
        g.Dispose()


def non_attivabile(win, trasparente_ai_clic=False):
    """La finestra non prende il focus: Revit resta attivo (Esc, scorciatoie, ExternalEvent).

    trasparente_ai_clic: mouse e clic passano alla vista di Revit sotto.
    """
    try:
        import ctypes
        hwnd = WindowInteropHelper(win).EnsureHandle().ToInt64()
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_TRANSPARENT = 0x00000020
        stile = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        stile = stile | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        if trasparente_ai_clic:
            stile = stile | WS_EX_TRANSPARENT
        user32.SetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE, stile)
    except Exception:
        pass
