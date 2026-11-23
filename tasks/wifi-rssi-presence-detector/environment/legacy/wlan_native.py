"""Native Windows WLAN reader. Cached BSS reads take about 1 ms per call."""

import ctypes
import os
from ctypes import wintypes


WLAN_API_VERSION = 2
WLAN_INTF_OPCODE_CURRENT_CONNECTION = 7
WLAN_MAX_NAME_LENGTH = 256
DOT11_SSID_MAX_LENGTH = 32
DOT11_RATE_SET_MAX_LENGTH = 126


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [("InterfaceGuid", GUID),
                ("strInterfaceDescription", wintypes.WCHAR * WLAN_MAX_NAME_LENGTH),
                ("isState", wintypes.DWORD)]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [("dwNumberOfItems", wintypes.DWORD), ("dwIndex", wintypes.DWORD),
                ("InterfaceInfo", WLAN_INTERFACE_INFO * 1)]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [("uSSIDLength", wintypes.ULONG),
                ("ucSSID", ctypes.c_ubyte * DOT11_SSID_MAX_LENGTH)]


class WLAN_RATE_SET(ctypes.Structure):
    _fields_ = [("uRateSetLength", wintypes.ULONG),
                ("usRateSet", wintypes.USHORT * DOT11_RATE_SET_MAX_LENGTH)]


class WLAN_BSS_ENTRY(ctypes.Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("uPhyId", wintypes.ULONG),
        ("dot11Bssid", ctypes.c_ubyte * 6),
        ("dot11BssType", wintypes.DWORD),
        ("dot11BssPhyType", wintypes.DWORD),
        ("lRssi", wintypes.LONG),
        ("uLinkQuality", wintypes.ULONG),
        ("bInRegDomain", ctypes.c_ubyte),
        ("usBeaconPeriod", wintypes.USHORT),
        ("ullTimestamp", ctypes.c_ulonglong),
        ("ullHostTimestamp", ctypes.c_ulonglong),
        ("usCapabilityInformation", wintypes.USHORT),
        ("ulChCenterFrequency", wintypes.ULONG),
        ("wlanRateSet", WLAN_RATE_SET),
        ("ulIeOffset", wintypes.ULONG),
        ("ulIeSize", wintypes.ULONG),
    ]


class WLAN_BSS_LIST(ctypes.Structure):
    _fields_ = [("dwTotalSize", wintypes.DWORD), ("dwNumberOfItems", wintypes.DWORD),
                ("wlanBssEntries", WLAN_BSS_ENTRY * 1)]


class WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("dot11Ssid", DOT11_SSID), ("dot11BssType", wintypes.DWORD),
                ("dot11Bssid", ctypes.c_ubyte * 6), ("dot11PhyType", wintypes.DWORD),
                ("uDot11PhyIndex", wintypes.ULONG), ("wlanSignalQuality", wintypes.ULONG),
                ("ulRxRate", wintypes.ULONG), ("ulTxRate", wintypes.ULONG)]


class WLAN_SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("bSecurityEnabled", wintypes.BOOL), ("bOneXEnabled", wintypes.BOOL),
                ("dot11AuthAlgorithm", wintypes.DWORD), ("dot11CipherAlgorithm", wintypes.DWORD)]


class WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("isState", wintypes.DWORD), ("wlanConnectionMode", wintypes.DWORD),
                ("strProfileName", wintypes.WCHAR * WLAN_MAX_NAME_LENGTH),
                ("wlanAssociationAttributes", WLAN_ASSOCIATION_ATTRIBUTES),
                ("wlanSecurityAttributes", WLAN_SECURITY_ATTRIBUTES)]


def address_string(address):
    return ":".join(f"{part:02x}" for part in address)


def check_status(status, operation):
    if status:
        raise OSError(status, operation)


class NativeWlan:
    def __init__(self):
        if os.name != "nt":
            raise OSError("The WLAN API is available on Windows")
        self.api = ctypes.WinDLL("wlanapi.dll")
        self.handle = wintypes.HANDLE()
        negotiated = wintypes.DWORD()
        self.api.WlanOpenHandle.argtypes = [wintypes.DWORD, ctypes.c_void_p,
                                            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.HANDLE)]
        check_status(self.api.WlanOpenHandle(WLAN_API_VERSION, None, ctypes.byref(negotiated),
                                             ctypes.byref(self.handle)), "WlanOpenHandle")
        self.api.WlanFreeMemory.argtypes = [ctypes.c_void_p]
        self.api.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self.api.WlanEnumInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_void_p)]
        self.api.WlanGetNetworkBssList.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID),
                                                  ctypes.c_void_p, wintypes.DWORD, wintypes.BOOL,
                                                  ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        self.api.WlanScan.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), ctypes.c_void_p,
                                     ctypes.c_void_p, ctypes.c_void_p]
        self.api.WlanQueryInterface.argtypes = [wintypes.HANDLE, ctypes.POINTER(GUID), wintypes.DWORD,
                                               ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                               ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
        self.interface = self._first_interface()

    def _first_interface(self):
        pointer = ctypes.c_void_p()
        check_status(self.api.WlanEnumInterfaces(self.handle, None, ctypes.byref(pointer)),
                     "WlanEnumInterfaces")
        try:
            header = ctypes.cast(pointer, ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)).contents
            if header.dwNumberOfItems == 0:
                raise OSError("No wireless interface")
            offset = WLAN_INTERFACE_INFO_LIST.InterfaceInfo.offset
            interface = WLAN_INTERFACE_INFO.from_address(pointer.value + offset)
            return GUID.from_buffer_copy(interface.InterfaceGuid)
        finally:
            self.api.WlanFreeMemory(pointer)

    def force_scan(self):
        check_status(self.api.WlanScan(self.handle, ctypes.byref(self.interface), None, None, None),
                     "WlanScan")

    def read_bss(self):
        pointer = ctypes.c_void_p()
        check_status(self.api.WlanGetNetworkBssList(self.handle, ctypes.byref(self.interface),
                                                   None, 3, False, None, ctypes.byref(pointer)),
                     "WlanGetNetworkBssList")
        try:
            header = ctypes.cast(pointer, ctypes.POINTER(WLAN_BSS_LIST)).contents
            offset = WLAN_BSS_LIST.wlanBssEntries.offset
            entries = (WLAN_BSS_ENTRY * header.dwNumberOfItems).from_address(pointer.value + offset)
            return {address_string(entry.dot11Bssid): int(entry.lRssi) for entry in entries}
        finally:
            self.api.WlanFreeMemory(pointer)

    def read_link(self):
        pointer = ctypes.c_void_p()
        size = wintypes.DWORD()
        value_type = wintypes.DWORD()
        check_status(self.api.WlanQueryInterface(self.handle, ctypes.byref(self.interface),
                                                WLAN_INTF_OPCODE_CURRENT_CONNECTION, None,
                                                ctypes.byref(size), ctypes.byref(pointer),
                                                ctypes.byref(value_type)), "WlanQueryInterface")
        try:
            connection = ctypes.cast(pointer, ctypes.POINTER(WLAN_CONNECTION_ATTRIBUTES)).contents
            return connection.wlanAssociationAttributes.wlanSignalQuality / 2 - 100
        finally:
            self.api.WlanFreeMemory(pointer)

    def close(self):
        if self.handle:
            self.api.WlanCloseHandle(self.handle, None)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()
