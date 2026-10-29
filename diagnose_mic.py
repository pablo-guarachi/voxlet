"""Microphone diagnostics: records 2 s from EVERY input device and reports peak/rms.

Run with the venv activated:
    .venv\\Scripts\\activate
    python diagnose_mic.py
"""
import sys
import time
import numpy as np
import sounddevice as sd

DURATION = 2.0
SR = 16000


def test_device(idx: int, name: str, max_in: int):
    print(f"\n[{idx}] {name} (in={max_in})")
    try:
        ch = 1 if max_in >= 1 else max_in
        rec = sd.rec(int(DURATION * SR), samplerate=SR, channels=ch, device=idx, dtype="float32")
        sd.wait()
        flat = rec.flatten()
        peak = float(np.max(np.abs(flat))) if flat.size else 0.0
        rms = float(np.sqrt(np.mean(flat**2))) if flat.size else 0.0
        verdict = "OK ✓" if peak > 0.005 else ("SILENT ✗" if peak < 0.001 else "VERY LOW ?")
        print(f"    peak={peak:.5f} rms={rms:.5f} → {verdict}")
        return peak, rms
    except Exception as e:
        print(f"    ERROR: {e}")
        return None, None


def main():
    print("=" * 60)
    print("MICROPHONE DIAGNOSTICS — speak during each test (2 s)")
    print("=" * 60)

    devs = sd.query_devices()
    default_in, default_out = sd.default.device
    print(f"\nDefault input: {default_in}  Default output: {default_out}")

    host_apis = sd.query_hostapis()
    print("\nAvailable host APIs:")
    for i, h in enumerate(host_apis):
        print(f"  [{i}] {h['name']} (default in={h.get('default_input_device')})")

    print("\nDetected input devices:")
    inputs = []
    for i, d in enumerate(devs):
        if d.get("max_input_channels", 0) > 0:
            host = host_apis[d["hostapi"]]["name"] if d.get("hostapi") is not None else "?"
            print(f"  [{i}] {d['name']!r}  host={host}  ch={d['max_input_channels']}  sr={d['default_samplerate']}")
            inputs.append((i, d["name"], d["max_input_channels"]))

    print("\n" + "=" * 60)
    print("STARTING TESTS — get ready to speak when you see 'TEST [n]'")
    print("=" * 60)
    time.sleep(2)

    results = {}
    for idx, name, max_in in inputs:
        print(f"\n>>> TEST [{idx}] in 1 s — SPEAK INTO THE MICROPHONE <<<")
        time.sleep(1)
        results[idx] = test_device(idx, name, max_in)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    working = [(i, p) for i, (p, _) in results.items() if p is not None and p > 0.005]
    if working:
        working.sort(key=lambda x: -x[1])
        print(f"\n✓ Devices that PICK UP audio (sorted by level):")
        for i, p in working:
            print(f"  device={i} peak={p:.4f}")
        print(f"\nUSE THIS DEVICE IN THE CONFIG: {working[0][0]}")
    else:
        print("\n✗ NO device captured any audio.")
        print("  → OS-level problem: privacy permissions or microphone muted system-wide.")


if __name__ == "__main__":
    main()
