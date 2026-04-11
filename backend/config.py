from pydantic import BaseModel
import json
import os
from typing import Any


class PrinterConfig(BaseModel):
    name: str
    ip: str
    access_code: str  # keep local only
    serial: str | None = None  # optional; some stacks use it


class AppConfig(BaseModel):
    # PrusaSlicer CLI
    prusa_console_exe: str
    prusa_profile_ini: str  # exported config bundle you control

    # Where to place temporary slice outputs
    slice_dir: str

    # Printers (one or many)
    printers: list[PrinterConfig]


def printers_override_path() -> str:
    return os.environ.get(
        "PRINTERS_CONFIG_JSON",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "printers.local.json")),
    )


def _sanitize_printer_rows(rows: list[dict[str, Any]]) -> list[PrinterConfig]:
    out: list[PrinterConfig] = []
    for row in rows:
        try:
            name = str(row.get("name", "")).strip()
            ip = str(row.get("ip", "")).strip()
            access_code = str(row.get("access_code", "")).strip()
            serial_raw = row.get("serial", None)
            serial = str(serial_raw).strip() if serial_raw is not None else None
            if not name or not ip or not access_code:
                continue
            out.append(
                PrinterConfig(
                    name=name,
                    ip=ip,
                    access_code=access_code,
                    serial=(serial or None),
                )
            )
        except Exception:
            continue
    return out


def load_printers_override() -> list[PrinterConfig]:
    path = printers_override_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc, dict):
            return []
        rows = doc.get("printers", [])
        if not isinstance(rows, list):
            return []
        return _sanitize_printer_rows(rows)
    except Exception:
        return []


def save_printers_override(printers: list[PrinterConfig]) -> str:
    path = printers_override_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {
        "printers": [
            {
                "name": p.name,
                "ip": p.ip,
                "access_code": p.access_code,
                "serial": p.serial,
            }
            for p in printers
        ]
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    return path


def _sync_process_env_printers(printers: list[PrinterConfig]) -> None:
    # Keep current process env aligned for compatibility with current conventions.
    for idx in [1, 2]:
        i = idx - 1
        if i < len(printers):
            p = printers[i]
            os.environ[f"PRINTER_{idx}_NAME"] = p.name
            os.environ[f"PRINTER_{idx}_IP"] = p.ip
            os.environ[f"PRINTER_{idx}_ACCESS_CODE"] = p.access_code
            if p.serial:
                os.environ[f"PRINTER_{idx}_SERIAL"] = p.serial
            elif f"PRINTER_{idx}_SERIAL" in os.environ:
                del os.environ[f"PRINTER_{idx}_SERIAL"]
        else:
            for k in ("NAME", "IP", "ACCESS_CODE", "SERIAL"):
                env_key = f"PRINTER_{idx}_{k}"
                if env_key in os.environ:
                    del os.environ[env_key]


def _load_printers_from_env() -> list[PrinterConfig]:
    printers: list[PrinterConfig] = []
    for idx in [1, 2]:
        name = os.environ.get(f"PRINTER_{idx}_NAME", f"BRIDGE{idx}")
        ip = os.environ.get(f"PRINTER_{idx}_IP", "")
        access_code = os.environ.get(f"PRINTER_{idx}_ACCESS_CODE", "")
        serial = os.environ.get(f"PRINTER_{idx}_SERIAL", None)
        if ip and access_code:
            printers.append(
                PrinterConfig(name=name, ip=ip, access_code=access_code, serial=serial)
            )
    return printers


def load_config() -> AppConfig:
    # IMPORTANT: do not hardcode secrets into git. Read from env.
    prusa_console_exe = os.environ.get(
        "PRUSA_SLICER_CONSOLE",
        r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe",
    )
    prusa_profile_ini = os.environ.get(
        "PRUSA_PROFILE_INI",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "prusaconfig.ini")),
    )
    slice_dir = os.environ.get(
        "SLICE_DIR",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runs", "_slices")),
    )

    printers = _load_printers_from_env()

    # Local override takes precedence and can contain more than two printers.
    override_printers = load_printers_override()
    if override_printers:
        printers = override_printers
        _sync_process_env_printers(printers)

    return AppConfig(
        prusa_console_exe=prusa_console_exe,
        prusa_profile_ini=prusa_profile_ini,
        slice_dir=slice_dir,
        printers=printers,
    )
