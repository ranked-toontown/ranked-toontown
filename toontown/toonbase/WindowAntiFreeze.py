"""
WindowAntiFreeze - Prevents Panda3D window from freezing during trolley minigames

This module implements a solution to prevent the game from freezing when
players hold the window title bar during trolley minigames, which would 
otherwise make them invulnerable to attacks due to collision detection stopping.

The solution works by:
1. Disabling window dragging and right-click context menus during trolley minigames
2. This prevents the modal loops that cause thread freezing
3. Only active during trolley minigames to minimize impact on normal gameplay
"""

import sys
import os
from direct.directnotify import DirectNotifyGlobal

# Only import Windows-specific modules on Windows
if os.name == 'nt':
    try:
        import ctypes
        from ctypes import wintypes
        
        # Windows API functions
        user32 = ctypes.windll.user32
        
        # Windows constants
        WM_SYSCOMMAND = 0x0112
        WM_NCRBUTTONDOWN = 0x00A4
        SC_MOVE = 0xF010
        SC_SIZE = 0xF000
        HTCAPTION = 2
        HTSYSMENU = 3
        
        # Function prototypes
        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        
        SetWindowLongPtrW = user32.SetWindowLongPtrW
        SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, WNDPROC]
        SetWindowLongPtrW.restype = WNDPROC
        
        CallWindowProcW = user32.CallWindowProcW
        CallWindowProcW.argtypes = [WNDPROC, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        CallWindowProcW.restype = ctypes.c_long
        
        GetWindowLongPtrW = user32.GetWindowLongPtrW
        GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        GetWindowLongPtrW.restype = WNDPROC
        
        GWLP_WNDPROC = -4
        
        WINDOWS_AVAILABLE = True
    except ImportError:
        WINDOWS_AVAILABLE = False
else:
    WINDOWS_AVAILABLE = False

class WindowAntiFreeze:
    """
    Prevents window freezing by disabling problematic window operations during trolley minigames.
    """
    
    notify = DirectNotifyGlobal.directNotify.newCategory('WindowAntiFreeze')
    
    def __init__(self):
        self.original_wndproc = None
        self.new_wndproc = None
        self.hwnd = None
        self.installed = False
        self.active = False  # Only active during trolley minigames
        
    def install(self):
        """Install the anti-freeze protection on the main Panda3D window."""
        if not WINDOWS_AVAILABLE:
            return False
            
        if self.installed:
            return True  # Already installed, don't warn
            
        try:
            # Get the window handle from Panda3D
            if not hasattr(base, 'win') or not base.win:
                return False
                
            # Get the native window handle
            window_handle = base.win.getWindowHandle()
            if not window_handle:
                return False
                
            int_handle = window_handle.getIntHandle()
            if not int_handle:
                return False
                
            self.hwnd = wintypes.HWND(int_handle)
            
            # Validate the window handle
            if not user32.IsWindow(self.hwnd):
                return False
            
            # Get the original window procedure
            self.original_wndproc = GetWindowLongPtrW(self.hwnd, GWLP_WNDPROC)
            if not self.original_wndproc:
                return False
            
            # Create and store the new window procedure to prevent garbage collection
            self.new_wndproc = WNDPROC(self._window_proc)
            
            # Install our custom window procedure
            result = SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, self.new_wndproc)
            
            if not result:
                return False
                
            self.installed = True
            self.notify.info("WindowAntiFreeze: Successfully installed anti-freeze protection")
            return True
            
        except Exception:
            return False
    
    def uninstall(self):
        """Remove the anti-freeze protection."""
        if not WINDOWS_AVAILABLE or not self.installed:
            return
            
        try:
            if self.hwnd and self.original_wndproc:
                SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, self.original_wndproc)
                
            self.installed = False
            self.hwnd = None
            self.original_wndproc = None
            self.new_wndproc = None
            
        except Exception:
            pass
    
    def activate(self):
        """Activate anti-freeze protection (called when entering trolley minigames)."""
        self.active = True
        self.notify.info("WindowAntiFreeze: Activated for trolley minigame")
    
    def deactivate(self):
        """Deactivate anti-freeze protection (called when leaving trolley minigames)."""
        self.active = False
        self.notify.info("WindowAntiFreeze: Deactivated")
    
    def _window_proc(self, hwnd, msg, wparam, lparam):
        """
        Custom window procedure that blocks problematic operations only during trolley minigames.
        """
        try:
            # Only block operations when active (during trolley minigames)
            if self.active:
                # Block right-click context menu on title bar and system menu
                if msg == WM_NCRBUTTONDOWN and (wparam == HTCAPTION or wparam == HTSYSMENU):
                    return 0  # Block right-click context menu entirely
                
                # Block problematic system commands that can cause freezing
                if msg == WM_SYSCOMMAND:
                    command = wparam & 0xFFF0
                    
                    # Block window dragging and resizing
                    if command == SC_MOVE or command == SC_SIZE:
                        return 0  # Block the operations completely
            
            # Pass all other messages to the original window procedure
            if self.original_wndproc:
                return CallWindowProcW(self.original_wndproc, hwnd, msg, wparam, lparam)
            else:
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            
        except Exception:
            # Fallback to original procedure on any error
            if self.original_wndproc:
                try:
                    return CallWindowProcW(self.original_wndproc, hwnd, msg, wparam, lparam)
                except Exception:
                    pass
            try:
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            except Exception:
                return 0

# Global instance
_window_anti_freeze = None

def install_window_anti_freeze():
    """Install the window anti-freeze protection."""
    global _window_anti_freeze
    
    if not WINDOWS_AVAILABLE:
        return False
    
    if _window_anti_freeze is None:
        _window_anti_freeze = WindowAntiFreeze()
    
    # Try to install, return success/failure silently
    try:
        return _window_anti_freeze.install()
    except Exception:
        return False

def uninstall_window_anti_freeze():
    """Remove the window anti-freeze protection."""
    global _window_anti_freeze
    
    if _window_anti_freeze:
        _window_anti_freeze.uninstall()

def activate_window_anti_freeze():
    """Activate anti-freeze protection for trolley minigames."""
    global _window_anti_freeze
    
    if _window_anti_freeze and _window_anti_freeze.installed:
        _window_anti_freeze.activate()

def deactivate_window_anti_freeze():
    """Deactivate anti-freeze protection when leaving trolley minigames."""
    global _window_anti_freeze
    
    if _window_anti_freeze and _window_anti_freeze.installed:
        _window_anti_freeze.deactivate()

def is_installed():
    """Check if the anti-freeze protection is installed."""
    global _window_anti_freeze
    return _window_anti_freeze and _window_anti_freeze.installed

def is_active():
    """Check if the anti-freeze protection is currently active."""
    global _window_anti_freeze
    return _window_anti_freeze and _window_anti_freeze.installed and _window_anti_freeze.active 