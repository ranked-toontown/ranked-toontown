"""
WindowAntiFreeze - Prevents Panda3D window from freezing when title bar is dragged

This module implements a solution to prevent the game from freezing when
players hold the window title bar, which would otherwise make them
invulnerable to boss attacks due to collision detection stopping.

The solution works by:
1. Disabling window dragging and system context menus entirely
2. This prevents the modal loops that cause thread freezing
3. Simple and effective approach with no complex message handling
"""

import sys
import os
from direct.directnotify import DirectNotifyGlobal

# Only import Windows-specific modules on Windows
if os.name == 'nt':
    try:
        import ctypes
        from ctypes import wintypes
        import threading
        
        # Windows API functions
        user32 = ctypes.windll.user32
        
        # Windows constants
        WM_SYSCOMMAND = 0x0112
        WM_NCLBUTTONDOWN = 0x00A1
        WM_NCRBUTTONDOWN = 0x00A4
        WM_NCRBUTTONUP = 0x00A5
        SC_MOVE = 0xF010
        SC_SIZE = 0xF000
        SC_CONTEXTHELP = 0xF180
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
    Prevents window freezing by disabling problematic window operations.
    """
    
    notify = DirectNotifyGlobal.directNotify.newCategory('WindowAntiFreeze')
    
    def __init__(self):
        self.original_wndproc = None
        self.new_wndproc = None
        self.hwnd = None
        self.installed = False
        self.dragging = False
        
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
    
    def _window_proc(self, hwnd, msg, wparam, lparam):
        """
        Custom window procedure that handles window operations safely.
        """
        try:
            # Block right-click context menu on title bar and system menu
            if msg == WM_NCRBUTTONDOWN and (wparam == HTCAPTION or wparam == HTSYSMENU):
                return 0  # Block right-click context menu entirely
            
            # Handle title bar dragging with custom implementation
            if msg == WM_NCLBUTTONDOWN and wparam == HTCAPTION:
                if not self.dragging:
                    self._start_async_drag()
                return 0  # Block default drag behavior
            
            # Block problematic system commands that can cause freezing
            if msg == WM_SYSCOMMAND:
                command = wparam & 0xFFF0
                
                # Block the default move command since we handle it ourselves
                if command == SC_MOVE:
                    return 0
                
                # Block resize and context help
                if command == SC_SIZE or command == SC_CONTEXTHELP:
                    return 0
            
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
    
    def _start_async_drag(self):
        """Start window dragging on a separate thread to prevent freezing."""
        if self.dragging:
            return
            
        self.dragging = True
        drag_thread = threading.Thread(target=self._handle_drag, daemon=True)
        drag_thread.start()
    
    def _handle_drag(self):
        """Handle window dragging asynchronously."""
        try:
            # Get initial cursor and window positions
            cursor_pos = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(cursor_pos))
            start_cursor = (cursor_pos.x, cursor_pos.y)
            
            rect = wintypes.RECT()
            user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            start_window = (rect.left, rect.top)
            
            # Track mouse movement while button is held
            while user32.GetAsyncKeyState(0x01) < 0:  # Left mouse button pressed
                user32.GetCursorPos(ctypes.byref(cursor_pos))
                
                # Calculate new window position
                dx = cursor_pos.x - start_cursor[0]
                dy = cursor_pos.y - start_cursor[1]
                new_x = start_window[0] + dx
                new_y = start_window[1] + dy
                
                # Move the window
                user32.SetWindowPos(
                    self.hwnd,
                    None,
                    new_x, new_y,
                    0, 0,
                    0x0001 | 0x0004  # SWP_NOSIZE | SWP_NOZORDER
                )
                
                # Small delay to prevent excessive CPU usage
                threading.Event().wait(0.01)
                
        except Exception:
            pass
        finally:
            self.dragging = False

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

def is_installed():
    """Check if the anti-freeze protection is installed."""
    global _window_anti_freeze
    return _window_anti_freeze and _window_anti_freeze.installed 