"""Application identity for Qt and macOS Python-based launches."""
import sys

APP_NAME = "AutoEventTracker"


def configure_application_identity():
    # Set these before QApplication initializes the native application menus.
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QGuiApplication

    QCoreApplication.setApplicationName(APP_NAME)
    QGuiApplication.setApplicationDisplayName(APP_NAME)
    if sys.platform != "darwin":
        return

    # Change only this process's in-memory bundle metadata, never Python's plist.
    import ctypes

    cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
    pointer = ctypes.c_void_p
    cf.CFBundleGetMainBundle.restype = pointer
    cf.CFBundleGetMainBundle.argtypes = []
    cf.CFBundleGetInfoDictionary.restype = pointer
    cf.CFBundleGetInfoDictionary.argtypes = [pointer]
    cf.CFStringCreateWithCString.restype = pointer
    cf.CFStringCreateWithCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFDictionarySetValue.argtypes = [pointer, pointer, pointer]
    cf.CFDictionarySetValue.restype = None
    cf.CFRelease.argtypes = [pointer]
    cf.CFRelease.restype = None
    bundle = cf.CFBundleGetMainBundle()
    info = cf.CFBundleGetInfoDictionary(bundle) if bundle else None
    if not info:
        return
    value = cf.CFStringCreateWithCString(None, APP_NAME.encode('utf-8'), 0x08000100)
    try:
        for name in (b'CFBundleName', b'CFBundleDisplayName'):
            key = cf.CFStringCreateWithCString(None, name, 0x08000100)
            try:
                cf.CFDictionarySetValue(info, key, value)
            finally:
                cf.CFRelease(key)
    finally:
        cf.CFRelease(value)
