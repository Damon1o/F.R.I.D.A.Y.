"""Replace the Edge branding on the app window.

`--app=` windows are still Edge windows: Windows draws Edge's logo in the titlebar and
groups the taskbar button under Edge. Two fixes, both on the window itself — no PWA
install, no bundled runtime:

* WM_SETICON  — titlebar and Alt-Tab icon.
* System.AppUserModel.ID / .RelaunchIconResource — the taskbar button: with its own AppID
  the window stops grouping under Edge, and the icon resource is what the taskbar draws.
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)

WM_SETICON = 0x0080
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
VT_LPWSTR = 31


class GUID(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD),
                ("d4", ctypes.c_ubyte * 8)]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", wintypes.USHORT), ("r1", wintypes.WORD), ("r2", wintypes.WORD),
                ("r3", wintypes.WORD), ("p", ctypes.c_void_p), ("pad", ctypes.c_void_p)]


# {9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3} — the AppUserModel property set.
_APPUSERMODEL = GUID(0x9F4C2855, 0x9F79, 0x4B39, (ctypes.c_ubyte * 8)(0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3))
PKEY_AppUserModel_ID = PROPERTYKEY(_APPUSERMODEL, 5)
PKEY_AppUserModel_RelaunchIconResource = PROPERTYKEY(_APPUSERMODEL, 3)
# IPropertyStore {886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}
IID_IPropertyStore = GUID(0x886D8EEB, 0x8CF2, 0x4446, (ctypes.c_ubyte * 8)(0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99))

APP_ID = "DamonLin.FRIDAY"


def _find_window(pid: int):
    """First visible top-level window owned by `pid` (or any of Edge's children)."""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def _set_prop(store, key, text: str) -> None:
    pv = PROPVARIANT(vt=VT_LPWSTR, p=ctypes.cast(ctypes.create_unicode_buffer(text), ctypes.c_void_p))
    vtbl = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    set_value = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, ctypes.POINTER(PROPERTYKEY),
                                   ctypes.POINTER(PROPVARIANT))(vtbl[6])
    set_value(store, ctypes.byref(key), ctypes.byref(pv))


def _commit(store) -> None:
    vtbl = ctypes.cast(store, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtbl[7])(store)          # Commit
    ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p)(vtbl[2])(store)          # Release


def apply(pid: int, ico: str, timeout: float = 20.0) -> bool:
    """Poll for the window (Edge takes a second to show it), then rebrand it."""
    ole32.CoInitialize(None)  # SHGetPropertyStoreForWindow is COM; this thread is not the main one
    deadline = time.time() + timeout
    hwnd = None
    while time.time() < deadline and not hwnd:
        hwnd = _find_window(pid)
        if not hwnd:
            time.sleep(0.3)
    if not hwnd:
        return False

    for size, which in ((16, 0), (32, 1)):  # ICON_SMALL, ICON_BIG
        h = user32.LoadImageW(None, ico, IMAGE_ICON, size, size, LR_LOADFROMFILE)
        if h:
            user32.SendMessageW(hwnd, WM_SETICON, which, h)

    store = ctypes.c_void_p()
    if shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(IID_IPropertyStore),
                                           ctypes.byref(store)) == 0:
        _set_prop(store, PKEY_AppUserModel_ID, APP_ID)
        _set_prop(store, PKEY_AppUserModel_RelaunchIconResource, f"{ico},0")
        _commit(store)
        # The taskbar reads the AppID when it creates the button, which already happened;
        # hide/show forces it to make a new one under ours instead of Edge's.
        user32.ShowWindow(hwnd, 0)
        user32.ShowWindow(hwnd, 5)
    return True
