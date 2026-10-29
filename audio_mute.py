"""Mute / restore the default Windows speaker.

Uses the Windows IMMDeviceEnumerator API directly via comtypes, so it does
not depend on pycaw API changes between versions.
"""
from __future__ import annotations

import gc

try:
    import comtypes
    from comtypes import CLSCTX_ALL, GUID, CoCreateInstance
    from pycaw.pycaw import (
        IMMDeviceEnumerator,
        IAudioEndpointVolume,
        EDataFlow,
        ERole,
    )
    HAS_PYCAW = True
    _IMPORT_ERROR = None
    CLSID_MMDeviceEnumerator = GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
except Exception as e:
    HAS_PYCAW = False
    _IMPORT_ERROR = e


class AudioMuter:
    def __init__(self, log=print):
        self.log = log
        self._volume = None
        self._was_muted = None
        # Kept alive and released explicitly in restore(), on the same thread
        # that created them: if they get garbage-collected on another thread
        # (e.g. stt-process), Release() causes an access violation.
        self._enumerator = None
        self._device = None

    def available(self) -> bool:
        return HAS_PYCAW

    def _get_volume(self):
        try:
            comtypes.CoInitialize()
        except Exception:
            pass
        enumerator = CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, CLSCTX_ALL
        )
        device = enumerator.GetDefaultAudioEndpoint(
            EDataFlow.eRender.value, ERole.eMultimedia.value
        )
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        # QueryInterface instead of ctypes.cast: cast creates a reference
        # cycle that only the GC can free, on an arbitrary thread.
        vol = interface.QueryInterface(IAudioEndpointVolume)
        del interface
        self._enumerator = enumerator
        self._device = device
        return vol

    def _release_com(self):
        """Release the COM pointers on the current thread."""
        self._volume = None
        self._device = None
        self._enumerator = None
        gc.collect()

    def mute_all_outputs(self):
        if not HAS_PYCAW:
            self.log(f"[mute] pycaw not available: {_IMPORT_ERROR}")
            return
        if self._volume is not None:
            return
        try:
            vol = self._get_volume()
            self._was_muted = bool(vol.GetMute())
            self._volume = vol
            if not self._was_muted:
                vol.SetMute(1, None)
                self.log("[mute] output muted")
        except Exception as e:
            self.log(f"[mute] error: {e}")
            self._release_com()
            self._was_muted = None

    def restore(self):
        if self._volume is None:
            return
        try:
            self._volume.SetMute(1 if self._was_muted else 0, None)
            if not self._was_muted:
                self.log("[mute] output restored")
        except Exception as e:
            self.log(f"[mute] restore error: {e}")
        finally:
            self._release_com()
            self._was_muted = None
