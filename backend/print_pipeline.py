# backend/print_pipeline.py
from __future__ import annotations

import os
import time
import uuid
import re
import json
import math
import shutil
import zipfile

import numpy as np
import trimesh

from slicer_prusa import slice_stl_to_gcode
from slicer_bambu import slice_stl_to_3mf_with_bambu, slice_assembled_stls_to_3mf_with_bambu
from bambu_lan import (
    BambuPrinterConfig,
    upload_3mf,
    upload_3mf_file,
    start_print,
    get_printer_status,
)


def _to_float_or_none(value) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _parse_duration_to_seconds(text: str | None) -> int | None:
    if not text:
        return None
    total = 0
    found = False
    for m in re.finditer(r"(\d+)\s*([hms])", text.lower()):
        found = True
        n = int(m.group(1))
        unit = m.group(2)
        if unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        else:
            total += n
    if found:
        return total
    if text.strip().isdigit():
        return int(text.strip())
    return None


def _parse_percent_to_int(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if not m:
        return None
    try:
        return int(round(float(m.group(1))))
    except Exception:
        return None


def _filament_density_g_per_cm3(filament_type: str | None) -> float:
    t = (filament_type or "").strip().upper()
    if "PLA-CF" in t or "PLACF" in t:
        return 1.28
    if "PLA" in t:
        return 1.24
    if "PETG" in t:
        return 1.27
    if "ABS" in t or "ASA" in t:
        return 1.05
    if "TPU" in t:
        return 1.21
    return 1.24


def _normalize_hex8(value: str | None) -> str | None:
    raw = str(value or "").strip().lstrip("#").upper()
    if len(raw) == 8:
        return f"#{raw}"
    if len(raw) == 6:
        return f"#{raw}FF"
    return None


def _hex_rgb(value: str | None) -> tuple[int, int, int]:
    norm = _normalize_hex8(value) or "#000000FF"
    return (
        int(norm[1:3], 16),
        int(norm[3:5], 16),
        int(norm[5:7], 16),
    )


def _color_distance_sq(a: str | None, b: str | None) -> int:
    ar, ag, ab = _hex_rgb(a)
    br, bg, bb = _hex_rgb(b)
    return (ar - br) ** 2 + (ag - bg) ** 2 + (ab - bb) ** 2


def _luminance(hex_color: str | None) -> float:
    """Perceived luminance 0–255; lower = darker."""
    r, g, b = _hex_rgb(hex_color)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _stl_bbox_volume(stl_path: str) -> float:
    """Bounding-box volume in mm³; used to identify the largest (body) part."""
    try:
        mesh = trimesh.load_mesh(stl_path, force="mesh")
        if not isinstance(mesh, trimesh.Trimesh):
            mesh = trimesh.util.concatenate(tuple(mesh.dump()))
        extents = np.asarray(mesh.extents, dtype=float)
        return float(extents[0] * extents[1] * extents[2])
    except Exception:
        return 0.0


def _tray_color_css(value: str | None) -> str:
    norm = _normalize_hex8(value)
    if not norm:
        return "#00AE42"
    return f"#{norm[1:7]}"


def _bambu_filament_search_roots(paths: dict) -> list[str]:
    roots: list[str] = []
    for key in ("filament_root", "filament_ota_root"):
        root = str(paths.get(key) or "").strip()
        if root and os.path.isdir(root) and root not in roots:
            roots.append(root)
    for key in ("filament_abs", "filament_placf", "filament_pla"):
        root = os.path.dirname(os.path.abspath(str(paths.get(key) or "")))
        if root and os.path.isdir(root) and root not in roots:
            roots.append(root)
    return roots


def _find_bambu_preset_path(preset_name: str, search_roots: list[str]) -> str | None:
    filename = str(preset_name or "").strip()
    if not filename:
        return None
    if not filename.lower().endswith(".json"):
        filename = f"{filename}.json"

    for root in search_roots:
        direct = os.path.join(root, filename)
        if os.path.exists(direct):
            return direct

    for root in search_roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            if filename in filenames:
                return os.path.join(dirpath, filename)
    return None


def _load_bambu_preset_json_flat(
    preset_path: str,
    *,
    search_roots: list[str],
    _seen: set[str] | None = None,
) -> dict:
    abs_path = os.path.abspath(preset_path)
    seen = set(_seen or ())
    if abs_path in seen:
        raise RuntimeError(f"Cyclic Bambu preset inheritance detected for {abs_path}")
    seen.add(abs_path)

    with open(abs_path, "r", encoding="utf-8", errors="replace") as handle:
        data = json.load(handle)

    inherits = str(data.get("inherits") or "").strip()
    if not inherits:
        return dict(data)

    parent_path = _find_bambu_preset_path(
        inherits,
        [os.path.dirname(abs_path), *search_roots],
    )
    if not parent_path:
        return dict(data)

    merged = _load_bambu_preset_json_flat(parent_path, search_roots=search_roots, _seen=seen)
    merged.update(data)
    return merged


def _materialize_bambu_filament_json(paths: dict, preset_path: str, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    merged = _load_bambu_preset_json_flat(
        preset_path,
        search_roots=_bambu_filament_search_roots(paths),
    )
    merged.pop("inherits", None)
    merged["from"] = "user"
    merged["instantiation"] = "true"
    merged["setting_id"] = f"PMF{uuid.uuid4().hex[:8].upper()}"
    out_path = os.path.join(
        out_dir,
        f"{os.path.splitext(os.path.basename(preset_path))[0]}_{uuid.uuid4().hex[:8]}.filament.json",
    )
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=2)
    return out_path


def _filament_json_for_tray_type(paths: dict, tray_type: str | None, out_dir: str | None = None) -> str:
    tray_text = str(tray_type or "").upper()
    if "ABS" in tray_text or "ASA" in tray_text:
        chosen = paths["filament_abs"]
    elif "PLA-CF" in tray_text or "PLACF" in tray_text:
        chosen = paths["filament_placf"]
    else:
        chosen = paths["filament_pla"]
    if out_dir:
        return _materialize_bambu_filament_json(paths, chosen, out_dir)
    return chosen


def _keychain_preview_parts(model_3mf_path: str | None) -> list[dict]:
    if not model_3mf_path:
        return []
    job_dir = os.path.dirname(os.path.abspath(model_3mf_path))
    if not os.path.isdir(job_dir):
        return []

    parts: list[dict] = []
    for name in os.listdir(job_dir):
        match = re.fullmatch(r"preview_([0-9a-fA-F]{8})\.stl", name)
        if not match:
            continue
        parts.append(
            {
                "color": f"#{match.group(1).upper()}",
                "stl_path": os.path.join(job_dir, name),
            }
        )
    parts.sort(key=lambda item: os.path.basename(item["stl_path"]).lower())
    return parts


def _write_centered_keychain_parts(parts: list[dict], out_dir: str) -> list[dict]:
    os.makedirs(out_dir, exist_ok=True)
    loaded: list[dict] = []
    meshes: list[trimesh.Trimesh] = []
    for item in parts:
        mesh = trimesh.load_mesh(item["stl_path"], force="mesh")
        if not isinstance(mesh, trimesh.Trimesh):
            mesh = trimesh.util.concatenate(tuple(mesh.dump()))
        mesh = mesh.copy()
        loaded.append({**item, "mesh": mesh})
        meshes.append(mesh)

    if not meshes:
        return []

    merged = trimesh.util.concatenate(meshes)
    bounds = np.asarray(merged.bounds, dtype=float)
    center = (bounds[0] + bounds[1]) / 2.0
    shift = np.array([100.0 - center[0], 100.0 - center[1], max(0.0, -float(bounds[0][2]))], dtype=float)

    written: list[dict] = []
    for item in loaded:
        mesh = item["mesh"].copy()
        mesh.apply_translation(shift)
        # Skip parts thinner than the minimum layer height — Bambu Studio's
        # --assemble command rejects batches that include sub-layer geometry
        # (e.g. single-face surface colour patches that are < 0.1 mm tall).
        z_extent = float(mesh.bounds[1][2] - mesh.bounds[0][2])
        if z_extent < 0.1:
            continue
        out_path = os.path.join(out_dir, os.path.basename(item["stl_path"]))
        mesh.export(out_path)
        written.append({k: v for k, v in item.items() if k != "mesh"} | {"stl_path": out_path})
    return written


def _patch_nozzle_type_in_3mf(project_3mf_path: str, nozzle_type: str) -> None:
    """
    Overwrite the nozzle_type embedded in a .3mf so the X1C doesn't raise a
    nozzle-mismatch dialog requiring manual resume.

    Patches two locations:
      - Metadata/project_settings.config  (JSON key "nozzle_type")
      - Metadata/plate_1.gcode            (gcode comment "; nozzle_type = ...")
    """
    if not os.path.exists(project_3mf_path) or not nozzle_type:
        return
    try:
        with zipfile.ZipFile(project_3mf_path, "r") as zf:
            archive = {name: zf.read(name) for name in zf.namelist()}

        changed = False

        settings_raw = archive.get("Metadata/project_settings.config")
        if settings_raw:
            data = json.loads(settings_raw.decode("utf-8", errors="replace"))
            if data.get("nozzle_type") != nozzle_type:
                data["nozzle_type"] = nozzle_type
                archive["Metadata/project_settings.config"] = json.dumps(
                    data, ensure_ascii=False, indent=4
                ).encode("utf-8")
                changed = True

        gcode_raw = archive.get("Metadata/plate_1.gcode")
        if gcode_raw:
            gcode_text = gcode_raw.decode("utf-8", errors="replace")
            patched = _upsert_gcode_comment_kv(gcode_text, "nozzle_type", nozzle_type)
            if patched != gcode_text:
                archive["Metadata/plate_1.gcode"] = patched.encode("utf-8")
                changed = True

        if not changed:
            return

        tmp_path = project_3mf_path + ".ntpatch.tmp"
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, payload in archive.items():
                zf.writestr(name, payload)
        os.replace(tmp_path, project_3mf_path)
    except Exception:
        pass  # never fail the whole pipeline for a metadata patch


def _rewrite_keychain_multicolor_metadata(
    *,
    project_3mf_path: str,
    gcode_path: str,
    slots: list[dict],
    first_slot: int,
) -> None:
    if not os.path.exists(project_3mf_path):
        return

    ordered_slots = [item for item in slots if isinstance(item, dict)]
    if not ordered_slots:
        return

    tray_colors = [_tray_color_css(item.get("tray_color")) for item in ordered_slots]
    tray_types = [str(item.get("tray_type") or "PLA") for item in ordered_slots]
    filament_ids = [max(0, int(item.get("filament_id", idx + 1)) - 1) for idx, item in enumerate(ordered_slots)]
    first_extruder = max(0, int(first_slot) - 1)

    def _replace_header_line(text: str, key: str, value: str) -> str:
        pattern = re.compile(rf"(?m)^; {re.escape(key)} = .*$")
        if pattern.search(text):
            return pattern.sub(f"; {key} = {value}", text)
        return text

    gcode_text = ""
    if gcode_path and os.path.exists(gcode_path):
        with open(gcode_path, "r", encoding="utf-8", errors="replace") as handle:
            gcode_text = handle.read()
        gcode_text = _replace_header_line(gcode_text, "filament_colour", ";".join(tray_colors))
        gcode_text = _replace_header_line(gcode_text, "extruder_colour", ";".join(tray_colors))
        gcode_text = _replace_header_line(gcode_text, "filament_type", ";".join(tray_types))
        gcode_text = _replace_header_line(gcode_text, "default_filament_colour", f"\"{tray_colors[0]}\"")
        with open(gcode_path, "w", encoding="utf-8", errors="replace") as handle:
            handle.write(gcode_text)

    with zipfile.ZipFile(project_3mf_path, "r") as zf:
        archive = {name: zf.read(name) for name in zf.namelist()}

    project_settings_raw = archive.get("Metadata/project_settings.config")
    if project_settings_raw:
        data = json.loads(project_settings_raw.decode("utf-8", errors="replace"))
        data["filament_colour"] = tray_colors
        data["extruder_colour"] = tray_colors
        data["default_filament_colour"] = [tray_colors[0]]
        data["filament_type"] = tray_types
        archive["Metadata/project_settings.config"] = json.dumps(data, ensure_ascii=False, indent=4).encode("utf-8")

    plate_raw = archive.get("Metadata/plate_1.json")
    if plate_raw:
        meta = json.loads(plate_raw.decode("utf-8", errors="replace"))
        meta["filament_colors"] = tray_colors
        meta["filament_ids"] = filament_ids
        meta["first_extruder"] = first_extruder
        archive["Metadata/plate_1.json"] = json.dumps(meta, ensure_ascii=False, indent=2).encode("utf-8")

    if gcode_text and "Metadata/plate_1.gcode" in archive:
        archive["Metadata/plate_1.gcode"] = gcode_text.encode("utf-8")

    tmp_path = project_3mf_path + ".tmp"
    with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in archive.items():
            zf.writestr(name, payload)
    os.replace(tmp_path, project_3mf_path)


def _build_keychain_multicolor_plan(
    *,
    model_3mf_path: str | None,
    slice_dir: str,
    printer_cfg: BambuPrinterConfig,
    paths: dict,
    use_ams: bool,
) -> dict | None:
    preview_parts = _keychain_preview_parts(model_3mf_path)
    if (not use_ams) or len(preview_parts) < 2:
        return None

    try:
        status = get_printer_status(printer_cfg)
    except Exception:
        return None

    trays = status.get("ams", {}).get("trays", []) if isinstance(status, dict) else []
    trays = [tray for tray in trays if isinstance(tray, dict) and int(tray.get("slot", 0) or 0) > 0]
    if len(trays) < 2:
        return None

    # Body = the largest-volume STL — assign it to the darkest loaded AMS tray
    # so the user gets black (or whichever dark colour is loaded) for the base.
    body_color = max(preview_parts, key=lambda p: _stl_bbox_volume(p["stl_path"]))["color"]
    darkest_tray = min(trays, key=lambda t: _luminance(t.get("color")))
    darkest_slot = int(darkest_tray.get("slot", 0) or 0)

    selected_slots: list[dict] = []
    used_slots: set[int] = set()
    for part in preview_parts:
        available = [t for t in trays if int(t.get("slot", 0) or 0) not in used_slots]
        if not available:
            available = trays  # all slots used — allow reuse rather than dropping

        if part["color"] == body_color and darkest_slot not in used_slots:
            chosen = darkest_tray
        else:
            chosen = min(
                available,
                key=lambda t: (
                    _color_distance_sq(t.get("color"), part["color"]),
                    int(t.get("slot", 0) or 0),
                ),
            )
        slot = int(chosen.get("slot", 0) or 0)
        used_slots.add(slot)
        selected_slots.append(
            {
                "slot": slot,
                "tray_color": _normalize_hex8(chosen.get("color")) or "#00AE42FF",
                "tray_type": str(chosen.get("type") or ""),
                "color": part["color"],
                "stl_path": part["stl_path"],
            }
        )

    work_dir = os.path.join(slice_dir, f"keychain_multicolor_{uuid.uuid4().hex[:8]}")
    written_parts = _write_centered_keychain_parts(selected_slots, work_dir)
    if not written_parts:
        return None

    by_path = {os.path.basename(item["stl_path"]).lower(): item for item in selected_slots}
    written_parts = [
        {
            **by_path.get(os.path.basename(item["stl_path"]).lower(), {}),
            "stl_path": item["stl_path"],
        }
        for item in written_parts
    ]
    written_parts = [
        {
            **item,
            "filament_id": idx + 1,
        }
        for idx, item in enumerate(written_parts)
    ]

    filament_jsons = [
        _filament_json_for_tray_type(paths, item.get("tray_type"), out_dir=work_dir)
        for item in written_parts
    ]

    return {
        "work_dir": work_dir,
        "parts": written_parts,
        "filament_jsons": filament_jsons,
        "filament_ids": [int(item["filament_id"]) for item in written_parts],
        "ams_mapping": [max(0, int(item["slot"]) - 1) for item in written_parts],
        "first_slot": 1,
        "slots": [
            {
                "slot": int(item["slot"]),
                "filament_id": int(item["filament_id"]),
                "tray_color": _normalize_hex8(item.get("tray_color")) or "#00AE42FF",
                "tray_type": str(item.get("tray_type") or ""),
                "color": _normalize_hex8(item.get("color")) or "#FFFFFFFF",
            }
            for item in written_parts
        ],
    }


def _extract_print_estimate(
    gcode_path: str,
    mode: str,
    infill_percent: int | None,
    filament_type_hint: str | None = None,
) -> dict:
    if not gcode_path or not os.path.exists(gcode_path):
        return {
            "available": False,
            "reason": "gcode_not_found",
            "mode": mode,
            "infill_percent": infill_percent,
        }

    with open(gcode_path, "r", encoding="utf-8", errors="replace") as f:
        gcode_text = f.read()

    model_time_text = None
    total_time_text = None

    # Bambu header format
    m = re.search(r"model printing time:\s*([^;\n]+)", gcode_text, re.IGNORECASE)
    if m:
        model_time_text = m.group(1).strip()
    m = re.search(r"total estimated time:\s*([^;\n]+)", gcode_text, re.IGNORECASE)
    if m:
        total_time_text = m.group(1).strip()

    # Prusa footer format
    if not total_time_text:
        m = re.search(r"estimated printing time.*?=\s*([^\n;]+)", gcode_text, re.IGNORECASE)
        if m:
            total_time_text = m.group(1).strip()

    model_seconds = _parse_duration_to_seconds(model_time_text)
    total_seconds = _parse_duration_to_seconds(total_time_text)

    filament_len_mm = None
    filament_cm3 = None
    filament_g = None
    volume_source = "gcode"

    # Prefer explicit mm values. If slicer reports meters, convert m -> mm.
    for pattern, mult in [
        (r"total filament length \[mm\]\s*:\s*([0-9.]+)", 1.0),
        (r"filament used \[mm\]\s*=\s*([0-9.]+)", 1.0),
        (r"total filament length \[m\]\s*:\s*([0-9.]+)", 1000.0),
        (r"filament used \[m\]\s*=\s*([0-9.]+)", 1000.0),
    ]:
        m = re.search(pattern, gcode_text, re.IGNORECASE)
        if m:
            base = _to_float_or_none(m.group(1))
            filament_len_mm = (base * mult) if base is not None else None
            break

    # Prefer cm^3. If value is mm^3, convert mm^3 -> cm^3.
    for pattern, to_cm3 in [
        (r"total filament volume \[cm\^3\]\s*:\s*([0-9.]+)", 1.0),
        (r"filament used \[cm3\]\s*=\s*([0-9.]+)", 1.0),
        (r"total filament volume \[mm\^3\]\s*:\s*([0-9.]+)", 0.001),
        (r"filament used \[mm3\]\s*=\s*([0-9.]+)", 0.001),
    ]:
        m = re.search(pattern, gcode_text, re.IGNORECASE)
        if m:
            base = _to_float_or_none(m.group(1))
            filament_cm3 = (base * to_cm3) if base is not None else None
            break

    filament_diameter_mm = None
    m = re.search(r"filament_diameter\s*[:=]\s*([0-9.]+)", gcode_text, re.IGNORECASE)
    if m:
        filament_diameter_mm = _to_float_or_none(m.group(1))
    if filament_diameter_mm is None or filament_diameter_mm <= 0:
        filament_diameter_mm = 1.75

    volume_from_length_cm3 = None
    if filament_len_mm is not None and filament_len_mm > 0:
        r = filament_diameter_mm * 0.5
        # mm^3 -> cm^3 by dividing by 1000
        volume_from_length_cm3 = (3.141592653589793 * r * r * filament_len_mm) / 1000.0

    # Some Bambu headers report value that numerically looks like mm^3 even though label says cm^3.
    if (
        filament_cm3 is not None
        and filament_cm3 > 0
        and volume_from_length_cm3 is not None
        and volume_from_length_cm3 > 0
    ):
        if filament_cm3 > (volume_from_length_cm3 * 5.0):
            mm3_as_cm3 = filament_cm3 / 1000.0
            if mm3_as_cm3 <= (volume_from_length_cm3 * 5.0):
                filament_cm3 = mm3_as_cm3
                volume_source = "gcode_mm3_corrected"
    elif (filament_cm3 is None or filament_cm3 <= 0) and volume_from_length_cm3 is not None and volume_from_length_cm3 > 0:
        filament_cm3 = volume_from_length_cm3
        volume_source = "length_derived"

    for pattern in [
        r"total filament weight \[g\]\s*:\s*([0-9.]+)",
        r"total filament used \[g\]\s*=\s*([0-9.]+)",
    ]:
        m = re.search(pattern, gcode_text, re.IGNORECASE)
        if m:
            filament_g = _to_float_or_none(m.group(1))
            break

    layer_count = None
    for pattern in [
        r"total layer number:\s*([0-9]+)",
        r"total layers count\s*=\s*([0-9]+)",
    ]:
        m = re.search(pattern, gcode_text, re.IGNORECASE)
        if m:
            layer_count = int(m.group(1))
            break

    infill_text = None
    for pattern in [
        r";\s*sparse_infill_density\s*=\s*([^\n;]+)",
        r";\s*fill_density\s*=\s*([^\n;]+)",
    ]:
        m = re.search(pattern, gcode_text, re.IGNORECASE)
        if m:
            infill_text = m.group(1).strip()
            break

    inferred_infill = _parse_percent_to_int(infill_text)
    if inferred_infill is None:
        inferred_infill = infill_percent

    m = re.search(r";\s*filament_type\s*=\s*([^\n;]+)", gcode_text, re.IGNORECASE)
    filament_type_from_gcode = m.group(1).strip() if m else None
    filament_type_hint_clean = (str(filament_type_hint).strip() if filament_type_hint else None)
    filament_type = filament_type_hint_clean or filament_type_from_gcode

    m = re.search(r";\s*curr_bed_type\s*=\s*([^\n;]+)", gcode_text, re.IGNORECASE)
    bed_type = m.group(1).strip() if m else None

    m = re.search(r";\s*nozzle_diameter\s*=\s*([^\n;]+)", gcode_text, re.IGNORECASE)
    nozzle_diameter = m.group(1).strip() if m else None

    m = re.search(r";\s*nozzle_type\s*=\s*([^\n;]+)", gcode_text, re.IGNORECASE)
    nozzle_type = m.group(1).strip() if m else None

    weight_estimated_g = None
    weight_source = "gcode"
    if (filament_g is None or filament_g <= 0) and filament_cm3 is not None and filament_cm3 > 0:
        density = _filament_density_g_per_cm3(filament_type)
        weight_estimated_g = round(filament_cm3 * density, 2)
        weight_source = "volume_estimate"
        filament_g = weight_estimated_g

    return {
        "available": bool(total_seconds or model_seconds or filament_len_mm),
        "minutes_total": (round(total_seconds / 60, 1) if total_seconds is not None else None),
        "minutes_model": (round(model_seconds / 60, 1) if model_seconds is not None else None),
        "time_text_total": total_time_text,
        "time_text_model": model_time_text,
        "filament_length_mm": filament_len_mm,
        "filament_volume_cm3": filament_cm3,
        "filament_volume_source": volume_source,
        "filament_weight_g": filament_g,
        "filament_weight_estimated_g": weight_estimated_g,
        "filament_weight_source": weight_source,
        "layer_count": layer_count,
        "mode": mode,
        "infill_percent": inferred_infill,
        "filament_type": filament_type,
        "filament_type_from_gcode": filament_type_from_gcode,
        "filament_type_hint": filament_type_hint_clean,
        "bed_type": bed_type,
        "nozzle_diameter": nozzle_diameter,
        "nozzle_type": nozzle_type,
    }


def _orientation_candidate_degrees() -> list[tuple[int, int, int]]:
    # 24 axis-aligned orientations (cube rotations) from quarter turns.
    return [
        (0, 0, 0), (0, 0, 90), (0, 0, 180), (0, 0, 270),
        (90, 0, 0), (90, 0, 90), (90, 0, 180), (90, 0, 270),
        (180, 0, 0), (180, 0, 90), (180, 0, 180), (180, 0, 270),
        (270, 0, 0), (270, 0, 90), (270, 0, 180), (270, 0, 270),
        (0, 90, 0), (0, 90, 90), (0, 90, 180), (0, 90, 270),
        (0, 270, 0), (0, 270, 90), (0, 270, 180), (0, 270, 270),
    ]


def _rotation_matrix_from_degrees(rx_deg: int, ry_deg: int, rz_deg: int):
    rx = trimesh.transformations.rotation_matrix(math.radians(float(rx_deg)), [1, 0, 0])
    ry = trimesh.transformations.rotation_matrix(math.radians(float(ry_deg)), [0, 1, 0])
    rz = trimesh.transformations.rotation_matrix(math.radians(float(rz_deg)), [0, 0, 1])
    return trimesh.transformations.concatenate_matrices(rx, ry, rz)


def _score_upright_extents(extents: tuple[float, float, float] | list[float]) -> float:
    x = max(float(extents[0]), 1e-6)
    y = max(float(extents[1]), 1e-6)
    z = max(float(extents[2]), 1e-6)
    avg_xy = (x + y) * 0.5
    footprint = x * y
    # Favor tall posture with reduced footprint.
    return (z / avg_xy) + (z / math.sqrt(footprint))


def _orientation_alignment_matrices(mesh: trimesh.Trimesh) -> list[tuple[str, np.ndarray]]:
    mats: list[tuple[str, np.ndarray]] = [("as_is", trimesh.transformations.identity_matrix())]
    try:
        pit = mesh.principal_inertia_transform
        if pit is not None:
            mats.append(("principal_axes", pit))
    except Exception:
        pass
    return mats


def _apply_orientation_inplace(mesh: trimesh.Trimesh, orientation_mode: str | None) -> dict:
    mode_raw = str(orientation_mode or "upright_auto").strip().lower()
    mode = mode_raw if mode_raw in ("upright_auto", "keep", "x_up", "y_up", "z_up") else "upright_auto"

    if mode in ("keep", "z_up"):
        return {
            "orientation_mode_requested": mode_raw,
            "orientation_mode_effective": mode,
            "orientation_rotated": False,
            "rotation_deg": {"x": 0, "y": 0, "z": 0},
        }

    if mode == "x_up":
        rot = _rotation_matrix_from_degrees(0, -90, 0)
        mesh.apply_transform(rot)
        return {
            "orientation_mode_requested": mode_raw,
            "orientation_mode_effective": mode,
            "orientation_rotated": True,
            "rotation_deg": {"x": 0, "y": -90, "z": 0},
        }

    if mode == "y_up":
        rot = _rotation_matrix_from_degrees(90, 0, 0)
        mesh.apply_transform(rot)
        return {
            "orientation_mode_requested": mode_raw,
            "orientation_mode_effective": mode,
            "orientation_rotated": True,
            "rotation_deg": {"x": 90, "y": 0, "z": 0},
        }

    # upright_auto: test both as-is and principal-axes aligned candidates,
    # then pick the most upright quarter-turn orientation.
    best = None
    best_score = -1e18
    for align_name, align_mat in _orientation_alignment_matrices(mesh):
        base = mesh.copy()
        try:
            base.apply_transform(align_mat)
        except Exception:
            continue

        for rx, ry, rz in _orientation_candidate_degrees():
            test_mesh = base.copy()
            test_mesh.apply_transform(_rotation_matrix_from_degrees(rx, ry, rz))
            ext = test_mesh.extents
            score = _score_upright_extents(ext)
            if score > best_score:
                best_score = score
                best = (align_name, align_mat, rx, ry, rz)

    if not best:
        return {
            "orientation_mode_requested": mode_raw,
            "orientation_mode_effective": "upright_auto",
            "orientation_rotated": False,
            "rotation_deg": {"x": 0, "y": 0, "z": 0},
        }

    align_name, align_mat, rx, ry, rz = best
    identity = trimesh.transformations.identity_matrix()
    rotated = (not np.allclose(align_mat, identity, atol=1e-6)) or (rx != 0 or ry != 0 or rz != 0)
    if rotated:
        if not np.allclose(align_mat, identity, atol=1e-6):
            mesh.apply_transform(align_mat)
        if rx != 0 or ry != 0 or rz != 0:
            mesh.apply_transform(_rotation_matrix_from_degrees(rx, ry, rz))

    return {
        "orientation_mode_requested": mode_raw,
        "orientation_mode_effective": "upright_auto",
        "orientation_rotated": bool(rotated),
        "orientation_alignment": align_name,
        "rotation_deg": {"x": int(rx), "y": int(ry), "z": int(rz)},
    }


def _prepare_stl_for_print(
    stl_path: str,
    work_dir: str,
    min_max_extent_mm: float = 10.0,
    auto_target_max_extent_mm: float = 40.0,
    target_max_extent_mm: float | None = None,
    scale_percent: float | None = None,
    size_preset: str | None = None,
    orientation_mode: str = "upright_auto",
) -> tuple[str, dict]:
    """
    Auto-scale very small meshes (common from Shap-E) so they print reliably.
    STL units are treated as mm by slicers.
    """
    def _normalize_mesh_pose_inplace(m: trimesh.Trimesh) -> dict:
        """
        Normalize translation so model is centered on XY and resting on Z=0.
        Keeps orientation and scale unchanged.
        """
        b = m.bounds
        if b is None or len(b) < 2:
            return {"normalized_pose": False, "reason": "missing_bounds"}

        min_x, min_y, min_z = float(b[0][0]), float(b[0][1]), float(b[0][2])
        max_x, max_y = float(b[1][0]), float(b[1][1])
        center_x = (min_x + max_x) * 0.5
        center_y = (min_y + max_y) * 0.5

        # Shift XY center to origin, then place bottom on bed.
        tx = -center_x
        ty = -center_y
        tz = -min_z
        moved = abs(tx) > 1e-6 or abs(ty) > 1e-6 or abs(tz) > 1e-6
        if moved:
            m.apply_translation([tx, ty, tz])

        return {
            "normalized_pose": bool(moved),
            "translation_applied_mm": {
                "x": round(tx, 6),
                "y": round(ty, 6),
                "z": round(tz, 6),
            },
        }

    try:
        mesh = trimesh.load(stl_path, force="mesh")
        if not isinstance(mesh, trimesh.Trimesh) or mesh.vertices is None or len(mesh.vertices) == 0:
            return stl_path, {"scaled": False, "reason": "invalid_mesh"}

        orientation_meta = _apply_orientation_inplace(mesh, orientation_mode)

        extents = mesh.extents
        size_x = float(extents[0]) if extents is not None and len(extents) > 0 else 0.0
        size_y = float(extents[1]) if extents is not None and len(extents) > 1 else 0.0
        size_z = float(extents[2]) if extents is not None and len(extents) > 2 else 0.0
        max_extent = float(max(size_x, size_y, size_z))
        if max_extent <= 0:
            return stl_path, {"scaled": False, "reason": "non_positive_extent"}

        scale_factor: float | None = None
        scale_reason = None

        if target_max_extent_mm is not None:
            scale_factor = float(target_max_extent_mm) / max_extent
            scale_reason = "target_max_extent_mm"
        elif scale_percent is not None:
            scale_factor = float(scale_percent) / 100.0
            scale_reason = "scale_percent"
        elif max_extent < float(min_max_extent_mm):
            scale_factor = float(auto_target_max_extent_mm) / max_extent
            scale_reason = "auto_small_mesh"

        if scale_factor is None:
            norm_meta = _normalize_mesh_pose_inplace(mesh)
            if norm_meta.get("normalized_pose"):
                normalized_path = os.path.join(work_dir, f"{uuid.uuid4().hex}.normalized.stl")
                mesh.export(normalized_path)
                return normalized_path, {
                    "scaled": False,
                    "scale_reason": "none",
                    "source_stl_path": stl_path,
                    "normalized_stl_path": normalized_path,
                    "source_dimensions_mm": {
                        "x": size_x,
                        "y": size_y,
                        "z": size_z,
                        "max_extent": max_extent,
                    },
                    "size_preset": size_preset,
                    "orientation_mode": orientation_mode,
                    **orientation_meta,
                    **norm_meta,
                }
            return stl_path, {
                "scaled": False,
                "scale_reason": "none",
                "source_dimensions_mm": {
                    "x": size_x,
                    "y": size_y,
                    "z": size_z,
                    "max_extent": max_extent,
                },
                "size_preset": size_preset,
                "orientation_mode": orientation_mode,
                **orientation_meta,
                **norm_meta,
            }

        if scale_factor <= 0:
            return stl_path, {"scaled": False, "reason": "invalid_scale_factor"}

        if abs(scale_factor - 1.0) < 1e-5:
            norm_meta = _normalize_mesh_pose_inplace(mesh)
            if norm_meta.get("normalized_pose"):
                normalized_path = os.path.join(work_dir, f"{uuid.uuid4().hex}.normalized.stl")
                mesh.export(normalized_path)
                return normalized_path, {
                    "scaled": False,
                    "scale_reason": scale_reason,
                    "scale_factor": 1.0,
                    "source_stl_path": stl_path,
                    "normalized_stl_path": normalized_path,
                    "source_dimensions_mm": {
                        "x": size_x,
                        "y": size_y,
                        "z": size_z,
                        "max_extent": max_extent,
                    },
                    "target_max_extent_mm": target_max_extent_mm,
                    "size_preset": size_preset,
                    "orientation_mode": orientation_mode,
                    **orientation_meta,
                    **norm_meta,
                }
            return stl_path, {
                "scaled": False,
                "scale_reason": scale_reason,
                "scale_factor": 1.0,
                "source_dimensions_mm": {
                    "x": size_x,
                    "y": size_y,
                    "z": size_z,
                    "max_extent": max_extent,
                },
                "target_max_extent_mm": target_max_extent_mm,
                "size_preset": size_preset,
                "orientation_mode": orientation_mode,
                **orientation_meta,
                **norm_meta,
            }

        mesh.apply_scale(scale_factor)
        norm_meta = _normalize_mesh_pose_inplace(mesh)

        out_ext = mesh.extents
        out_x = float(out_ext[0]) if out_ext is not None and len(out_ext) > 0 else 0.0
        out_y = float(out_ext[1]) if out_ext is not None and len(out_ext) > 1 else 0.0
        out_z = float(out_ext[2]) if out_ext is not None and len(out_ext) > 2 else 0.0

        scaled_path = os.path.join(work_dir, f"{uuid.uuid4().hex}.scaled.stl")
        mesh.export(scaled_path)
        return scaled_path, {
            "scaled": True,
            "scale_reason": scale_reason,
            "source_stl_path": stl_path,
            "scaled_stl_path": scaled_path,
            "source_dimensions_mm": {
                "x": size_x,
                "y": size_y,
                "z": size_z,
                "max_extent": max_extent,
            },
            "scaled_dimensions_mm": {
                "x": out_x,
                "y": out_y,
                "z": out_z,
                "max_extent": float(max(out_x, out_y, out_z)),
            },
            "source_max_extent_mm": max_extent,
            "target_max_extent_mm": (float(target_max_extent_mm) if target_max_extent_mm is not None else None),
            "auto_target_max_extent_mm": float(auto_target_max_extent_mm),
            "scale_factor": scale_factor,
            "scale_percent": round(scale_factor * 100.0, 2),
            "size_preset": size_preset,
            "orientation_mode": orientation_mode,
            **orientation_meta,
            **norm_meta,
        }
    except Exception as e:
        return stl_path, {"scaled": False, "reason": f"scale_error:{e}"}


def _analyze_support_need(
    stl_path: str,
    threshold_deg: float = 45.0,
    min_centroid_z_mm: float = 0.6,
) -> dict:
    """
    Lightweight geometric heuristic for auto-support decisions.
    """
    try:
        mesh = trimesh.load(stl_path, force="mesh")
        if not isinstance(mesh, trimesh.Trimesh) or mesh.vertices is None or len(mesh.vertices) == 0:
            return {"available": False, "reason": "invalid_mesh", "requires_support": True}

        if mesh.faces is None or len(mesh.faces) == 0:
            return {"available": False, "reason": "no_faces", "requires_support": True}

        face_normals = mesh.face_normals
        face_areas = mesh.area_faces
        centers = mesh.triangles_center
        if face_normals is None or face_areas is None or centers is None:
            return {"available": False, "reason": "missing_face_data", "requires_support": True}

        bounds = mesh.bounds
        z_min = float(bounds[0][2]) if bounds is not None else 0.0
        min_z_for_support = z_min + float(min_centroid_z_mm)

        # Down-facing triangles with strong downward normal (undersides/overhangs).
        nz_threshold = -abs(math.cos(math.radians(float(threshold_deg))))
        total_area = float(mesh.area) if mesh.area is not None else 0.0
        if total_area <= 0:
            return {"available": False, "reason": "non_positive_area", "requires_support": True}

        overhang_area = 0.0
        overhang_faces = 0
        total_faces = int(len(face_areas))
        for idx in range(total_faces):
            c = centers[idx]
            if float(c[2]) <= min_z_for_support:
                continue
            n = face_normals[idx]
            if float(n[2]) >= nz_threshold:
                continue
            a = float(face_areas[idx])
            if a <= 0:
                continue
            overhang_area += a
            overhang_faces += 1

        ratio = (overhang_area / total_area) if total_area > 0 else 0.0

        # Tuned to avoid over-supporting small decorative parts while still catching real overhangs.
        requires = bool(
            (overhang_area >= 120.0 and ratio >= 0.012)
            or (overhang_area >= 380.0)
        )
        severity = "high" if overhang_area >= 500.0 or ratio >= 0.08 else ("medium" if requires else "low")

        return {
            "available": True,
            "requires_support": requires,
            "severity": severity,
            "threshold_deg": float(threshold_deg),
            "min_centroid_z_mm": float(min_centroid_z_mm),
            "overhang_area_mm2": round(overhang_area, 2),
            "overhang_ratio": round(ratio, 4),
            "overhang_faces": int(overhang_faces),
            "total_faces": int(total_faces),
            "total_area_mm2": round(total_area, 2),
        }
    except Exception as e:
        return {"available": False, "reason": f"support_analysis_error:{e}", "requires_support": True}


_FILAMENT_BED_TEMP: dict[str, int] = {
    "ABS": 90, "ASA": 100, "PC": 100, "PA": 90, "PA-CF": 90,
    "PETG": 70, "PETG-CF": 70, "PLA-CF": 60, "PLA": 60,
}


def _bed_temp_for_filament(filament_type: str | None, default: int = 60) -> int:
    key = (filament_type or "").upper().strip()
    return _FILAMENT_BED_TEMP.get(key, _FILAMENT_BED_TEMP.get(key.split("-")[0], default))


def _ensure_bed_preheat_gcode(gcode_text: str, bed_temp_c: int = 60, filament_type: str | None = None) -> str:
    bed_temp_c = _bed_temp_for_filament(filament_type, default=bed_temp_c)
    # If slicer already emitted bed heat commands, keep original G-code.
    if re.search(r"(?m)^M140\s+S", gcode_text) or re.search(r"(?m)^M190\s+S", gcode_text):
        return gcode_text

    preheat = (
        "; PrintMind auto-added bed preheat for printer compatibility\n"
        f"M140 S{int(bed_temp_c)} ; set bed temperature\n"
        f"M190 S{int(bed_temp_c)} ; wait for bed temperature\n"
    )

    lines = gcode_text.splitlines(keepends=True)
    insert_at = 0
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("M104") or line.lstrip().startswith("G28"):
            insert_at = idx
            break
        insert_at = idx + 1
    lines.insert(insert_at, preheat)
    return "".join(lines)


def _ensure_start_purge_lines_gcode(gcode_text: str) -> str:
    marker = "; PrintMind auto-added purge lines"
    if marker in gcode_text:
        return gcode_text

    idx = gcode_text.find(";LAYER_CHANGE")
    if idx <= 0:
        return gcode_text

    purge = (
        f"{marker}\n"
        "G92 E0\n"
        "G1 Z0.28 F1200\n"
        "G1 X20 Y2 F6000\n"
        "G1 E2 F2400\n"
        "G1 X220 Y2 E12 F1200\n"
        "G1 X220 Y3 F6000\n"
        "G1 X20 Y3 E22 F1200\n"
        "G92 E0\n"
    )
    return gcode_text[:idx] + purge + gcode_text[idx:]


def _upsert_gcode_comment_kv(gcode_text: str, key: str, value: str) -> str:
    """
    Ensure comment key exists as '; key = value' in G-code text.
    If key exists, replace it. Otherwise prepend a new line near the top.
    """
    line = f"; {key} = {value}"
    pattern = re.compile(rf"(?m)^;\s*{re.escape(key)}\s*=\s*.*$")
    if pattern.search(gcode_text):
        return pattern.sub(line, gcode_text)
    return f"{line}\n{gcode_text}"


def _ensure_bambu_match_metadata_gcode(
    gcode_text: str,
    bed_type: str,
    nozzle_mm: float,
    nozzle_type: str,
    filament_type: str | None = None,
) -> str:
    """
    Add/override metadata keys that X1C uses for nozzle/bed compatibility checks.
    This reduces manual confirmation prompts when using fallback (Prusa) slicing.
    """
    out = gcode_text
    out = _upsert_gcode_comment_kv(out, "curr_bed_type", str(bed_type or "Textured PEI Plate"))
    out = _upsert_gcode_comment_kv(out, "nozzle_diameter", f"{float(nozzle_mm):.1f}")
    out = _upsert_gcode_comment_kv(out, "nozzle_type", str(nozzle_type or "hardened_steel"))
    if filament_type:
        out = _upsert_gcode_comment_kv(out, "filament_type", str(filament_type))
    return out


def _safe_job_name(mode: str, job_name: str | None, job_id: str) -> str:
    if job_name:
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in job_name.strip())
        safe = safe.strip("._-")[:40]
    else:
        safe = ""
    if not safe:
        safe = f"{mode}_{job_id[:8]}"
    return safe


def _bambu_default_paths() -> dict:
    appdata = os.environ.get("APPDATA", "")
    system_root = os.environ.get(
        "BAMBU_SYSTEM_ROOT",
        os.path.join(appdata, "BambuStudio", "system", "BBL"),
    )
    return {
        "exe": os.environ.get("BAMBU_STUDIO_EXE", r"C:\Program Files\Bambu Studio\bambu-studio.exe"),
        "machine_root": os.path.join(system_root, "machine"),
        "filament_root": os.path.join(system_root, "filament"),
        "filament_ota_root": os.path.join(appdata, "BambuStudio", "ota", "presets", "BBL", "filament"),
        "machine_default": os.environ.get(
            "BAMBU_MACHINE_JSON",
            os.path.join(system_root, "machine", "Bambu Lab X1 Carbon 0.4 nozzle.json"),
        ),
        "process_decorative": os.environ.get(
            "BAMBU_PROCESS_DECORATIVE_JSON",
            os.path.join(system_root, "process", "0.16mm Optimal @BBL X1C.json"),
        ),
        "process_durable": os.environ.get(
            "BAMBU_PROCESS_DURABLE_JSON",
            os.path.join(system_root, "process", "0.20mm Strength @BBL X1C.json"),
        ),
        "process_draft": os.environ.get(
            "BAMBU_PROCESS_DRAFT_JSON",
            os.path.join(system_root, "process", "0.24mm Draft @BBL X1C.json"),
        ),
        "filament_pla": os.environ.get(
            "BAMBU_FILAMENT_PLA_JSON",
            os.path.join(system_root, "filament", "Bambu PLA Basic @BBL X1C.json"),
        ),
        "filament_placf": os.environ.get(
            "BAMBU_FILAMENT_PLACF_JSON",
            os.path.join(system_root, "filament", "Bambu PLA-CF @BBL X1C.json"),
        ),
        "filament_abs": os.environ.get(
            "BAMBU_FILAMENT_ABS_JSON",
            os.path.join(system_root, "filament", "Bambu ABS @BBL X1C.json"),
        ),
    }


def _pick_bambu_machine_json(paths: dict, nozzle_mm: float) -> str:
    nozzle_text = f"{float(nozzle_mm):.1f}"
    candidate = os.path.join(paths["machine_root"], f"Bambu Lab X1 Carbon {nozzle_text} nozzle.json")
    if os.path.exists(candidate):
        return candidate
    return paths["machine_default"]


def _pick_bambu_process_json(mode: str, paths: dict) -> str:
    m = (mode or "").lower().strip()
    if m == "draft":
        return paths["process_draft"]
    if m == "durable":
        return paths["process_durable"]
    return paths["process_decorative"]


def _pick_bambu_filament_json(
    printer_cfg: BambuPrinterConfig,
    paths: dict,
    use_ams: bool,
    ams_slot: int | None,
    materialize_dir: str | None = None,
) -> tuple[str, dict]:
    meta: dict = {"source": "default"}
    chosen = paths["filament_pla"]

    if not use_ams or not ams_slot:
        if materialize_dir:
            chosen = _materialize_bambu_filament_json(paths, chosen, materialize_dir)
        return chosen, meta

    try:
        st = get_printer_status(printer_cfg)
        trays = st.get("ams", {}).get("trays", []) if isinstance(st, dict) else []
        tray = next((t for t in trays if int(t.get("slot", -1)) == int(ams_slot)), None)
        if not tray:
            return chosen, meta

        tray_type = str(tray.get("type") or "").upper()
        meta = {"source": "ams", "slot": int(ams_slot), "tray_type": tray_type}
        if "ABS" in tray_type:
            chosen = paths["filament_abs"]
        elif "PLA-CF" in tray_type or "PLACF" in tray_type:
            chosen = paths["filament_placf"]
        else:
            chosen = paths["filament_pla"]
        if materialize_dir:
            chosen = _materialize_bambu_filament_json(paths, chosen, materialize_dir)
        return chosen, meta
    except Exception as e:
        if materialize_dir:
            chosen = _materialize_bambu_filament_json(paths, chosen, materialize_dir)
        return chosen, {"source": "fallback", "reason": str(e)}


def _can_use_bambu_backend(paths: dict) -> tuple[bool, list[str]]:
    required = [paths["exe"], paths["machine_default"], paths["filament_pla"]]
    missing = [p for p in required if not os.path.exists(p)]
    # At least one process profile should exist.
    process_ok = any(
        os.path.exists(p)
        for p in [paths["process_decorative"], paths["process_durable"], paths["process_draft"]]
    )
    if not process_ok:
        missing.append("process_profile")
    return (len(missing) == 0), missing


def _build_bambu_process_override(
    base_process_json: str,
    out_dir: str,
    bed_type: str,
    nozzle_type: str,
    infill_percent: int | None = None,
    support_enabled: bool = True,
    support_type: str = "tree(auto)",
    support_on_build_plate_only: bool = False,
    enable_prime_tower: bool | None = None,
    flush_into_support: bool | None = None,
    flush_into_objects: bool | None = None,
    flush_into_infill: bool | None = None,
) -> tuple[str, dict]:
    bed = (bed_type or "").strip()
    if not bed:
        return base_process_json, {"override_applied": False}

    with open(base_process_json, "r", encoding="utf-8") as f:
        p = json.load(f)

    p["curr_bed_type"] = bed
    p["nozzle_type"] = nozzle_type

    effective_infill = infill_percent if infill_percent is not None else 15
    clamped = max(0, min(100, int(effective_infill)))
    infill_text = f"{clamped}%"
    p["sparse_infill_density"] = infill_text
    p["skeleton_infill_density"] = infill_text
    p["skin_infill_density"] = infill_text
    applied_infill = clamped

    support_type_effective = "tree(auto)" if support_type not in ("tree(auto)", "normal(auto)") else support_type
    p["enable_support"] = "1" if support_enabled else "0"
    p["support_type"] = support_type_effective
    p["support_on_build_plate_only"] = "1" if support_on_build_plate_only else "0"
    if enable_prime_tower is not None:
        p["enable_prime_tower"] = "1" if enable_prime_tower else "0"
    if flush_into_support is not None:
        p["flush_into_support"] = "1" if flush_into_support else "0"
    if flush_into_objects is not None:
        p["flush_into_objects"] = "1" if flush_into_objects else "0"
    if flush_into_infill is not None:
        p["flush_into_infill"] = "1" if flush_into_infill else "0"
    p["name"] = f"{p.get('name', 'Process')} (PrintMind)"
    p["from"] = "user"
    p["instantiation"] = "true"
    p["setting_id"] = f"PM{uuid.uuid4().hex[:6].upper()}"

    out_path = os.path.join(out_dir, f"{uuid.uuid4().hex}.process_override.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)

    return out_path, {
        "override_applied": True,
        "bed_type": bed,
        "nozzle_type": nozzle_type,
        "infill_percent": applied_infill,
        "support_enabled": bool(support_enabled),
        "support_type": support_type_effective,
        "support_on_build_plate_only": bool(support_on_build_plate_only),
        "enable_prime_tower": enable_prime_tower,
        "flush_into_support": flush_into_support,
        "flush_into_objects": flush_into_objects,
        "flush_into_infill": flush_into_infill,
        "process_override_json": out_path,
    }


def run_print_pipeline(
    prusa_console_exe: str,
    prusa_profile_ini: str,
    slice_dir: str,
    stl_path: str,
    model_3mf_path: str | None,
    printer_ip: str,
    printer_access_code: str,
    printer_serial: str,
    mode: str,
    auto_start: bool,
    job_name: str | None = None,
    use_ams: bool = True,
    ams_slot: int | None = None,
    bed_leveling: bool = True,
    flow_cali: bool = True,
    vibration_cali: bool = True,
    layer_inspect: bool = False,
    timelapse: bool = False,
    bed_type: str = "Textured PEI Plate",
    nozzle_mm: float = 0.4,
    nozzle_type: str = "hardened_steel",
    infill_percent: int | None = None,
    scale_percent: float | None = None,
    target_max_extent_mm: float | None = None,
    size_preset: str | None = None,
    orientation_mode: str = "upright_auto",
    support_mode: str = "auto",
    support_enabled: bool | None = None,
    support_type: str = "tree(auto)",
    support_on_build_plate_only: bool = False,
    estimate_only: bool = False,
) -> dict:
    os.makedirs(slice_dir, exist_ok=True)
    t0 = time.time()

    prepared_stl_path, stl_scale = _prepare_stl_for_print(
        stl_path=stl_path,
        work_dir=slice_dir,
        target_max_extent_mm=target_max_extent_mm,
        scale_percent=scale_percent,
        size_preset=size_preset,
        orientation_mode=orientation_mode,
    )
    bambu_input_path = os.path.abspath(model_3mf_path) if model_3mf_path else prepared_stl_path

    support_mode_norm = (support_mode or "auto").strip().lower()
    if support_mode_norm not in ("auto", "on", "off"):
        support_mode_norm = "auto"
    support_analysis = _analyze_support_need(prepared_stl_path)
    if support_mode_norm == "on":
        support_enabled_effective = True
    elif support_mode_norm == "off":
        support_enabled_effective = False
    else:
        if support_enabled is None:
            support_enabled_effective = bool(support_analysis.get("requires_support", True))
        else:
            support_enabled_effective = bool(support_enabled)

    printer_cfg = BambuPrinterConfig(
        ip=printer_ip,
        access_code=printer_access_code,
        serial=printer_serial,
    )

    paths = _bambu_default_paths()
    use_bambu_backend, bambu_missing = _can_use_bambu_backend(paths)
    bambu_runtime_error: str | None = None

    uploaded_name: str | None = None
    estimate_filament_type_hint: str | None = None
    multicolor_ams_mapping: list[int] | None = None

    if use_bambu_backend:
        try:
            machine_json = _pick_bambu_machine_json(paths, nozzle_mm=nozzle_mm)
            process_json = _pick_bambu_process_json(mode, paths)
            keychain_multicolor = _build_keychain_multicolor_plan(
                model_3mf_path=model_3mf_path,
                slice_dir=slice_dir,
                printer_cfg=printer_cfg,
                paths=paths,
                use_ams=use_ams,
            )
            process_json_effective, process_override_meta = _build_bambu_process_override(
                base_process_json=process_json,
                out_dir=slice_dir,
                bed_type=bed_type,
                nozzle_type=nozzle_type,
                infill_percent=infill_percent,
                support_enabled=support_enabled_effective,
                support_type=support_type,
                support_on_build_plate_only=support_on_build_plate_only,
                enable_prime_tower=(True if keychain_multicolor else None),
                flush_into_support=(False if keychain_multicolor else None),
                flush_into_objects=(False if keychain_multicolor else None),
                flush_into_infill=(False if keychain_multicolor else None),
            )
            if keychain_multicolor:
                multicolor_ams_mapping = list(keychain_multicolor["ams_mapping"])
                filament_meta = {
                    "source": "ams_multicolor",
                    "slots": keychain_multicolor["slots"],
                }
                estimate_filament_type_hint = str(keychain_multicolor["slots"][0].get("tray_type") or "").strip() or None
                s = slice_assembled_stls_to_3mf_with_bambu(
                    bambu_studio_exe=paths["exe"],
                    machine_json=machine_json,
                    process_json=process_json_effective,
                    filament_jsons=keychain_multicolor["filament_jsons"],
                    filament_ids=keychain_multicolor["filament_ids"],
                    stl_paths=[item["stl_path"] for item in keychain_multicolor["parts"]],
                    out_dir=slice_dir,
                )
                _rewrite_keychain_multicolor_metadata(
                    project_3mf_path=s["project_3mf_path"],
                    gcode_path=s.get("gcode_path", ""),
                    slots=keychain_multicolor["slots"],
                    first_slot=int(keychain_multicolor["first_slot"]),
                )
                s["keychain_multicolor"] = {
                    "enabled": True,
                    "slots": keychain_multicolor["slots"],
                    "ams_mapping": keychain_multicolor["ams_mapping"],
                }
                filament_json_effective = ";".join(keychain_multicolor["filament_jsons"])
                bambu_input_effective = ";".join(item["stl_path"] for item in keychain_multicolor["parts"])
            else:
                filament_json, filament_meta = _pick_bambu_filament_json(
                    printer_cfg=printer_cfg,
                    paths=paths,
                    use_ams=use_ams,
                    ams_slot=ams_slot,
                    materialize_dir=slice_dir,
                )
                estimate_filament_type_hint = str(filament_meta.get("tray_type") or "").strip() or None
                if not estimate_filament_type_hint:
                    fj = os.path.basename(str(filament_json)).upper()
                    if "PLA-CF" in fj or "PLACF" in fj:
                        estimate_filament_type_hint = "PLA-CF"
                    elif "ABS" in fj:
                        estimate_filament_type_hint = "ABS"
                    elif "PETG" in fj:
                        estimate_filament_type_hint = "PETG"
                    elif "PLA" in fj:
                        estimate_filament_type_hint = "PLA"
                s = slice_stl_to_3mf_with_bambu(
                    bambu_studio_exe=paths["exe"],
                    machine_json=machine_json,
                    process_json=process_json_effective,
                    filament_json=filament_json,
                    stl_path=bambu_input_path,
                    out_dir=slice_dir,
                )
                filament_json_effective = filament_json
                bambu_input_effective = bambu_input_path
            # Patch nozzle_type into the 3mf so the X1C doesn't prompt a mismatch dialog.
            _patch_nozzle_type_in_3mf(s["project_3mf_path"], nozzle_type)
            if not estimate_only:
                safe = _safe_job_name(mode, job_name, s["job_id"])
                upload_name = f"printmind_{safe}_{uuid.uuid4().hex[:4]}.3mf"
                uploaded_name = upload_3mf_file(
                    printer_cfg,
                    local_3mf_path=s["project_3mf_path"],
                    upload_name=upload_name,
                )
            backend_meta = {
                "slicer_backend": "bambu_studio",
                "machine_json": machine_json,
                "process_json": process_json_effective,
                "process_base_json": process_json,
                "filament_json": filament_json_effective,
                "filament_selection": filament_meta,
                "estimate_filament_type_hint": estimate_filament_type_hint,
                "bambu_input_path": bambu_input_effective,
                "color_model_source": model_3mf_path,
                "bed_type": bed_type,
                "nozzle_mm": nozzle_mm,
                "nozzle_type": nozzle_type,
                "infill_percent": infill_percent,
                "support_mode": support_mode_norm,
                "support_enabled_effective": support_enabled_effective,
                "support_type": support_type,
                "support_on_build_plate_only": support_on_build_plate_only,
                "support_analysis": support_analysis,
                "scale_percent": scale_percent,
                "target_max_extent_mm": target_max_extent_mm,
                "size_preset": size_preset,
                "orientation_mode": orientation_mode,
                "process_override": process_override_meta,
                "keychain_multicolor": (
                    {
                        "enabled": True,
                        "slots": keychain_multicolor["slots"],
                        "ams_mapping": keychain_multicolor["ams_mapping"],
                    }
                    if keychain_multicolor
                    else None
                ),
            }
        except Exception as e:
            # Some generated meshes are rejected by Bambu CLI even when they are valid STL.
            # Fall back to Prusa path so UI doesn't fail with 500.
            bambu_runtime_error = str(e)
            use_bambu_backend = False

    if not use_bambu_backend:
        # Fallback path: PrusaSlicer + custom startup safety additions.
        s = slice_stl_to_gcode(
            prusa_console_exe=prusa_console_exe,
            profile_ini=prusa_profile_ini,
            stl_path=prepared_stl_path,
            out_dir=slice_dir,
            mode=mode,
            infill_percent=infill_percent,
        )

        with open(s["gcode_path"], "r", encoding="utf-8", errors="replace") as f:
            gcode_text = f.read()
        gcode_text = _ensure_bed_preheat_gcode(gcode_text, bed_temp_c=60, filament_type=estimate_filament_type_hint)
        gcode_text = _ensure_start_purge_lines_gcode(gcode_text)
        gcode_text = _ensure_bambu_match_metadata_gcode(
            gcode_text=gcode_text,
            bed_type=bed_type,
            nozzle_mm=nozzle_mm,
            nozzle_type=nozzle_type,
            filament_type=estimate_filament_type_hint,
        )
        # Keep on-disk G-code consistent with uploaded payload and estimates.
        with open(s["gcode_path"], "w", encoding="utf-8", errors="replace") as f:
            f.write(gcode_text)

        if not estimate_only:
            safe = _safe_job_name(mode, job_name, s["job_id"])
            upload_name = f"printmind_{safe}_{uuid.uuid4().hex[:4]}.3mf"
            uploaded_name = upload_3mf(
                printer_cfg,
                gcode_text=gcode_text,
                upload_name=upload_name,
            )
        backend_meta = {
            "slicer_backend": "prusa_fallback",
            "fallback_reason": (
                "bambu_slice_failed_runtime" if bambu_runtime_error else "missing_bambu_cli_or_presets"
            ),
            "missing": bambu_missing,
            "bambu_runtime_error": bambu_runtime_error,
            "infill_percent": infill_percent,
            "support_mode": support_mode_norm,
            "support_enabled_effective": support_enabled_effective,
            "support_type": support_type,
            "support_on_build_plate_only": support_on_build_plate_only,
            "support_analysis": support_analysis,
            "scale_percent": scale_percent,
            "target_max_extent_mm": target_max_extent_mm,
            "size_preset": size_preset,
            "orientation_mode": orientation_mode,
            "estimate_filament_type_hint": estimate_filament_type_hint,
            "bambu_input_path": bambu_input_path,
            "color_model_source": model_3mf_path,
        }

    estimate = _extract_print_estimate(
        gcode_path=s.get("gcode_path", ""),
        mode=mode,
        infill_percent=infill_percent,
        filament_type_hint=estimate_filament_type_hint,
    )

    started = False
    if auto_start and (not estimate_only) and uploaded_name:
        start_print(
            printer_cfg,
            uploaded_name,
            plate=1,
            use_ams=use_ams,
            ams_slot=ams_slot,
            ams_mapping=multicolor_ams_mapping,
            bed_leveling=bed_leveling,
            flow_cali=flow_cali,
            vibration_cali=vibration_cali,
            layer_inspect=layer_inspect,
            timelapse=timelapse,
        )
        started = True

    total = time.time() - t0
    return {
        "seconds_total": total,
        "slice": dict(s),
        "stl_scale": stl_scale,
        "estimated": estimate,
        **backend_meta,
        "estimate_only": bool(estimate_only),
        "upload": ({"upload_name": uploaded_name} if uploaded_name else None),
        "print_options": {
            "use_ams": use_ams,
            "ams_slot": ams_slot,
            "bed_leveling": bed_leveling,
            "flow_cali": flow_cali,
            "vibration_cali": vibration_cali,
            "layer_inspect": layer_inspect,
            "timelapse": timelapse,
            "bed_type": bed_type,
            "nozzle_mm": nozzle_mm,
            "nozzle_type": nozzle_type,
            "infill_percent": infill_percent,
            "support_mode": support_mode_norm,
            "support_enabled_effective": support_enabled_effective,
            "support_type": support_type,
            "support_on_build_plate_only": support_on_build_plate_only,
            "support_analysis": support_analysis,
            "scale_percent": scale_percent,
            "target_max_extent_mm": target_max_extent_mm,
            "size_preset": size_preset,
            "orientation_mode": orientation_mode,
        },
        "started": started,
    }
