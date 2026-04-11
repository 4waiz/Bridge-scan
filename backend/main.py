# backend/main.py
import json
import os
import io
import threading
import time
import traceback
import urllib.request
import urllib.parse
import uuid
import warnings
from typing import Any

import trimesh
from PIL import Image
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
try:
    from bambulabs_api.states_info import PrintStatus as BambuPrintStatus
except Exception:
    BambuPrintStatus = None

# Silence noisy upstream shap-e AMP deprecation warnings.
warnings.filterwarnings("ignore", category=FutureWarning, message=r".*torch\.cuda\.amp\.custom_fwd.*")
warnings.filterwarnings("ignore", category=FutureWarning, message=r".*torch\.cuda\.amp\.custom_bwd.*")

from config import load_config, PrinterConfig, save_printers_override, printers_override_path
from print_pipeline import run_print_pipeline, _apply_orientation_inplace
from bambu_lan import BambuPrinterConfig, get_printer_status, send_print_command

ROOT = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.abspath(os.path.join(ROOT, ".."))
FRONTEND_DIR = os.path.join(APP_ROOT, "frontend")
RUNS_DIR = os.path.join(APP_ROOT, "runs")

app = FastAPI()

STATIC_DIR = os.path.join(FRONTEND_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

shape = None
_SHAPE_LOCK = threading.Lock()
_SHAPE_IMPORT_ERROR: str | None = None
keychain_template = None
_KEYCHAIN_LOCK = threading.Lock()
_KEYCHAIN_IMPORT_ERROR: str | None = None
cfg = load_config()


def _env_bool(name: str, default: str) -> bool:
    return str(os.environ.get(name, default)).strip().lower() not in ("0", "false", "no")


def _service_not_loaded_payload() -> dict[str, Any]:
    return {
        "loaded": False,
        "device": "lazy",
        "strict_gpu_mode": _env_bool("STRICT_GPU_MODE", "1"),
        "disable_quality_fallback": _env_bool("DISABLE_QUALITY_FALLBACK", "1"),
        "gpu_vram_gb": 0.0,
        "low_vram_mode": False,
        "prewarm": _PREWARM_RESULT,
        "lazy_init": True,
        "error": _SHAPE_IMPORT_ERROR,
    }


def _shape_payload(svc) -> dict[str, Any]:
    if svc is None:
        return _service_not_loaded_payload()
    return {
        "loaded": True,
        "device": str(svc.device),
        "strict_gpu_mode": bool(getattr(svc, "_strict_gpu_mode", False)),
        "disable_quality_fallback": bool(getattr(svc, "_disable_quality_fallback", False)),
        "gpu_vram_gb": round(float(getattr(svc, "_gpu_vram_gb", 0.0) or 0.0), 2),
        "low_vram_mode": bool(getattr(svc, "_low_vram_mode", False)),
        "prewarm": _PREWARM_RESULT,
        "lazy_init": True,
        "error": _SHAPE_IMPORT_ERROR,
    }


def _get_shape_service(load_if_missing: bool = True):
    global shape
    global _SHAPE_IMPORT_ERROR
    if shape is not None or not load_if_missing:
        return shape
    with _SHAPE_LOCK:
        if shape is not None:
            return shape
        try:
            from shap_e_service import ShapeService as _ShapeService

            shape = _ShapeService(RUNS_DIR)
            _SHAPE_IMPORT_ERROR = None
            return shape
        except Exception as e:
            _SHAPE_IMPORT_ERROR = str(e)
            raise


def _get_keychain_service(load_if_missing: bool = True):
    global keychain_template
    global _KEYCHAIN_IMPORT_ERROR
    if keychain_template is not None or not load_if_missing:
        return keychain_template
    with _KEYCHAIN_LOCK:
        if keychain_template is not None:
            return keychain_template
        try:
            from keychain_service import KeychainService as _KeychainService

            keychain_template = _KeychainService(
                template_dir=os.path.join(ROOT, "assets", "templates", "bridge_keychain"),
                runs_dir=RUNS_DIR,
            )
            _KEYCHAIN_IMPORT_ERROR = None
            return keychain_template
        except Exception as e:
            _KEYCHAIN_IMPORT_ERROR = str(e)
            raise


def _is_generation_cancelled(exc: Exception) -> bool:
    return exc.__class__.__name__ == "GenerationCancelledError"


def _reload_cfg() -> None:
    global cfg
    cfg = load_config()


class GenerateRequest(BaseModel):
    prompt: str
    quality_preset: str = "balanced"
    request_id: str | None = None


class GenerateImageUrlRequest(BaseModel):
    image_url: str
    quality_preset: str = "balanced"
    request_id: str | None = None


class GenerationCancelRequest(BaseModel):
    request_id: str


class KeychainBuildRequest(BaseModel):
    name: str
    name_color: str | None = None


class SliceAndSendRequest(BaseModel):
    stl_path: str
    model_3mf_path: str | None = None
    printer_name: str
    auto_route: bool = False
    mode: str = "decorative"
    auto_start: bool = False
    skip_preflight: bool = False
    job_name: str | None = None
    use_ams: bool = True
    ams_slot: int | None = None
    bed_leveling: bool = True
    flow_cali: bool = True
    vibration_cali: bool = True
    layer_inspect: bool = False
    timelapse: bool = False
    bed_type: str = "Textured PEI Plate"
    nozzle_mm: float = 0.4
    nozzle_type: str = "hardened_steel"
    infill_percent: int | None = None
    scale_percent: float | None = None
    target_max_extent_mm: float | None = None
    size_preset: str | None = None
    orientation_mode: str = "upright_auto"
    support_mode: str = "auto"
    support_enabled: bool | None = None
    support_type: str = "tree(auto)"
    support_on_build_plate_only: bool = False


class PrinterCommandRequest(BaseModel):
    printer_name: str | None = None


class PrinterAdminItem(BaseModel):
    name: str
    ip: str
    access_code: str
    serial: str | None = None


class PrintersAdminSaveRequest(BaseModel):
    printers: list[PrinterAdminItem]


_QUEUE_LOCK = threading.Lock()
_QUEUE_ITEMS: list[dict[str, Any]] = []
_QUEUE_STOP = threading.Event()
_QUEUE_THREAD: threading.Thread | None = None
_PREWARM_THREAD: threading.Thread | None = None
_PREWARM_RESULT: dict[str, Any] | None = None

_ERROR_HINTS: dict[str, str] = {
    "0500803C": "Nozzle mismatch. Re-slice with the actual nozzle diameter/type or update printer nozzle settings.",
    "0500803B": "Nozzle mismatch. Re-slice with the actual nozzle diameter/type or update printer nozzle settings.",
    "0300400C": "Build plate mismatch. Re-slice with the currently mounted plate type.",
}

_TIMELINE_STAGES: list[tuple[str, str]] = [
    ("queued", "Queued"),
    ("heating", "Heating"),
    ("calibration", "Calibration"),
    ("first_layer", "First Layer"),
    ("printing", "Printing"),
    ("stopped", "Stopped"),
    ("finished", "Finished"),
]


def _normalize_nozzle_type(v: Any) -> str | None:
    raw = str(v or "").strip().lower()
    if not raw:
        return None
    alias = {
        "hx01": "hardened_steel",
        "hardened_steel": "hardened_steel",
        "hardened steel": "hardened_steel",
        "stainless_steel": "stainless_steel",
        "stainless steel": "stainless_steel",
    }
    if raw in alias:
        return alias[raw]
    if "harden" in raw:
        return "hardened_steel"
    if "stainless" in raw:
        return "stainless_steel"
    return raw


def _model_dump(m: BaseModel) -> dict[str, Any]:
    if hasattr(m, "model_dump"):
        return m.model_dump()  # pydantic v2
    return m.dict()  # pydantic v1


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except Exception:
        return None


def _normalize_hex8(v: Any) -> str | None:
    raw = str(v or "").strip().replace("#", "")
    if len(raw) == 6:
        raw = f"{raw}FF"
    if len(raw) != 8:
        return None
    try:
        int(raw, 16)
    except Exception:
        return None
    return raw.upper()


def _hex_rgb(v: Any) -> tuple[int, int, int] | None:
    normalized = _normalize_hex8(v)
    if not normalized:
        return None
    return (
        int(normalized[0:2], 16),
        int(normalized[2:4], 16),
        int(normalized[4:6], 16),
    )


def _color_distance_sq(a: Any, b: Any) -> int:
    rgb_a = _hex_rgb(a)
    rgb_b = _hex_rgb(b)
    if not rgb_a or not rgb_b:
        return 10**9
    return sum((int(x) - int(y)) ** 2 for x, y in zip(rgb_a, rgb_b))


def _request_is_keychain(req: SliceAndSendRequest) -> bool:
    stl_path = os.path.abspath(str(req.stl_path or "")).lower()
    model_3mf_path = os.path.abspath(str(req.model_3mf_path or "")).lower() if req.model_3mf_path else ""
    job_name = str(req.job_name or "").strip().lower()
    keychain_root = os.path.abspath(os.path.join(RUNS_DIR, "keychain")).lower()
    return (
        stl_path.startswith(keychain_root)
        or (model_3mf_path and model_3mf_path.startswith(keychain_root))
        or job_name.startswith("bridge-keychain-")
    )


def _preferred_ams_slot(
    req: SliceAndSendRequest,
    trays: list[dict[str, Any]],
    *,
    active_slot: int = 0,
) -> int | None:
    if not trays:
        return None
    if _request_is_keychain(req):
        ranked = sorted(
            trays,
            key=lambda tray: (
                _color_distance_sq(tray.get("color"), "F5641EFF"),
                _to_int(tray.get("slot", 0), 0),
            ),
        )
        preferred = _to_int(ranked[0].get("slot", 0), 0)
        if preferred > 0:
            return preferred
    if active_slot > 0:
        return active_slot
    fallback = _to_int(trays[0].get("slot", 0), 0)
    return fallback if fallback > 0 else None


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _build_issue(
    code: str,
    severity: str,
    message: str,
    *,
    field: str | None = None,
    suggested_fix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
    }
    if field:
        out["field"] = field
    if suggested_fix:
        out["suggested_fix"] = suggested_fix
    return out


def _safe_run_path(path: str) -> str | None:
    abs_path = os.path.abspath(path)
    runs_abs = os.path.abspath(RUNS_DIR)
    if not abs_path.startswith(runs_abs) or not os.path.exists(abs_path):
        return None
    return abs_path


def _export_model_variant(stl_path: str, target_format: str) -> tuple[str, str, str]:
    fmt = str(target_format or "stl").strip().lower()
    allowed = {
        "stl": ("model/stl", ".stl"),
        "obj": ("model/obj", ".obj"),
        "3mf": ("model/3mf", ".3mf"),
    }
    if fmt not in allowed:
        raise ValueError("format must be one of: stl, obj, 3mf")

    media_type, suffix = allowed[fmt]
    src_ext = os.path.splitext(stl_path)[1].strip().lower()
    if fmt == "3mf":
        if src_ext != ".3mf":
            raise ValueError("3mf export requires a .3mf source path")
        return stl_path, media_type, f"model{suffix}"
    if fmt == "stl":
        return stl_path, media_type, f"model{suffix}"

    base, _ = os.path.splitext(stl_path)
    out_path = f"{base}{suffix}"
    if not os.path.exists(out_path):
        mesh = trimesh.load_mesh(stl_path, force="mesh")
        mesh.export(out_path, file_type=fmt)
    return out_path, media_type, f"model{suffix}"


def _translate_print_error(error_code: int, error_hex: str | None) -> str | None:
    if not error_code:
        return None
    hx = (error_hex or f"{error_code:08X}").upper()
    if hx in _ERROR_HINTS:
        return _ERROR_HINTS[hx]
    return (
        f"Printer reported error {hx}. Check nozzle, plate, AMS loading, and resume/restart if needed."
    )


def _humanize_print_stage_name(name: str) -> str:
    text = str(name or "").replace("_", " ").strip().title()
    replacements = {
        "Heatbed Preheating": "Heatbed Preheating",
        "Heating Hotend": "Heating Hotend",
        "Auto Bed Leveling": "Auto Bed Leveling",
        "Scanning Bed Surface": "Scanning Bed Surface",
        "Inspecting First Layer": "Inspecting First Layer",
        "Calibrating Extrusion Flow": "Calibrating Extrusion Flow",
        "Calibrating Motor Noise": "Calibrating Motor Noise",
        "Calibrating Micro Lidar": "Calibrating Micro LiDAR",
        "Calibrating Lidar": "Calibrating LiDAR",
        "Changing Filament": "Changing Filament",
        "Filament Loading": "Filament Loading",
        "Filament Unloading": "Filament Unloading",
        "Cleaning Nozzle Tip": "Cleaning Nozzle Tip",
        "Checking Extruder Temperature": "Checking Extruder Temperature",
        "Identifying Build Plate Type": "Identifying Build Plate Type",
        "Sweeping Xy Mech Mode": "Sweeping XY Mech Mode",
    }
    return replacements.get(text, text)


def _mc_stage_timeline(mc_print_stage: Any) -> tuple[str, str] | None:
    if BambuPrintStatus is None:
        return None
    try:
        stage = BambuPrintStatus(_to_int(mc_print_stage, -999))
    except Exception:
        return None

    if stage == BambuPrintStatus.UNKNOWN:
        return None
    if stage == BambuPrintStatus.IDLE:
        return ("queued", "Queued")
    if stage == BambuPrintStatus.PRINTING:
        return ("printing", "Printing")
    if stage == BambuPrintStatus.INSPECTING_FIRST_LAYER:
        return ("first_layer", "Inspecting First Layer")

    paused_names = {
        name for name in dir(BambuPrintStatus)
        if name.startswith("PAUSED_") or name == "M400_PAUSE"
    }
    if stage.name in paused_names:
        return ("printing", "Paused / Interrupted")

    heating_stages = {
        BambuPrintStatus.HEATBED_PREHEATING,
        BambuPrintStatus.HEATING_HOTEND,
        BambuPrintStatus.CHECKING_EXTRUDER_TEMPERATURE,
        BambuPrintStatus.IDENTIFYING_BUILD_PLATE_TYPE,
        BambuPrintStatus.HOMING_TOOLHEAD,
        BambuPrintStatus.CLEANING_NOZZLE_TIP,
        BambuPrintStatus.CHANGING_FILAMENT,
        BambuPrintStatus.FILAMENT_LOADING,
        BambuPrintStatus.FILAMENT_UNLOADING,
        BambuPrintStatus.COOLING_CHAMBER,
    }
    if stage in heating_stages:
        return ("heating", _humanize_print_stage_name(stage.name))

    calibration_stages = {
        BambuPrintStatus.AUTO_BED_LEVELING,
        BambuPrintStatus.SWEEPING_XY_MECH_MODE,
        BambuPrintStatus.CALIBRATING_EXTRUSION,
        BambuPrintStatus.SCANNING_BED_SURFACE,
        BambuPrintStatus.CALIBRATING_MICRO_LIDAR,
        BambuPrintStatus.CALIBRATING_LIDAR,
        BambuPrintStatus.CALIBRATING_EXTRUSION_FLOW,
        BambuPrintStatus.CALIBRATING_MOTOR_NOISE,
    }
    if stage in calibration_stages:
        return ("calibration", _humanize_print_stage_name(stage.name))

    return None


def _build_timeline(
    gcode_state: str | None,
    percent: int | float | None,
    mc_print_stage: Any = None,
) -> tuple[str, str, list[dict[str, Any]]]:
    state = str(gcode_state or "").upper()
    pct = max(0, min(100, _to_int(percent, 0)))

    stage_from_mc = _mc_stage_timeline(mc_print_stage)
    active_states = {"PREPARE", "RUNNING", "FINISH"}
    terminal_states = {"FAILED", "PAUSE", "FINISHED", "FINISH", "COMPLETE", "COMPLETED", "IDLE"}
    allow_mc_stage = state in active_states or (not state and pct > 0)

    interrupted_states = {"FAILED", "PAUSE"}
    if state in interrupted_states:
        if stage_from_mc is not None:
            last_stage_id = stage_from_mc[0]
        elif pct <= 0:
            last_stage_id = "calibration"
        elif pct < 3:
            last_stage_id = "first_layer"
        else:
            last_stage_id = "printing"
        if last_stage_id not in {"queued", "heating", "calibration", "first_layer", "printing"}:
            last_stage_id = "queued"

        stage_id = "stopped"
        stage_label = "Paused" if state == "PAUSE" else "Stopped"
        progress_order = ["queued", "heating", "calibration", "first_layer", "printing"]
        reached_index = progress_order.index(last_stage_id)
        timeline = []
        for sid, label in _TIMELINE_STAGES:
            if sid == "stopped":
                step_state = "halted"
            elif sid == "finished":
                step_state = "pending"
            elif sid in progress_order and progress_order.index(sid) <= reached_index:
                step_state = "done"
            else:
                step_state = "pending"
            timeline.append({"id": sid, "label": label, "state": step_state})
        return stage_id, stage_label, timeline

    if stage_from_mc is not None and allow_mc_stage and state not in terminal_states:
        stage_id, stage_label = stage_from_mc
    else:
        stage_id = "queued"
        stage_label = "Ready" if state in {"", "IDLE"} else "Queued"
        if state in {"PREPARE"}:
            stage_id = "heating"
            stage_label = "Heating / Preparing"
        elif state in {"RUNNING"}:
            if pct <= 0:
                stage_id = "calibration"
                stage_label = "Startup / Calibration"
            elif pct < 3:
                stage_id = "first_layer"
                stage_label = "First Layer"
            else:
                stage_id = "printing"
                stage_label = "Printing"
        elif state in {"FINISH", "FINISHED", "COMPLETE", "COMPLETED"}:
            stage_id = "finished"
            stage_label = "Finished"

    stage_index = next((i for i, (sid, _) in enumerate(_TIMELINE_STAGES) if sid == stage_id), 0)
    timeline = []
    for i, (sid, label) in enumerate(_TIMELINE_STAGES):
        timeline.append(
            {
                "id": sid,
                "label": label,
                "state": "done" if i < stage_index else ("active" if i == stage_index else "pending"),
            }
        )
    return stage_id, stage_label, timeline


def _augment_status_payload(status: dict[str, Any]) -> dict[str, Any]:
    error_code = _to_int(status.get("print_error", 0), 0)
    error_hex = status.get("print_error_hex")
    raw = status.get("raw") if isinstance(status.get("raw"), dict) else {}
    stage_id, stage_label, timeline = _build_timeline(
        status.get("gcode_state"),
        status.get("percent"),
        raw.get("mc_print_stage"),
    )
    gcode_file = str(status.get("gcode_file") or "")
    job_name = str(status.get("subtask_name") or "").strip() or (os.path.basename(gcode_file) if gcode_file else "")
    return {
        **status,
        "stage_id": stage_id,
        "stage_label": stage_label,
        "timeline": timeline,
        "job_name": job_name or None,
        "error_hint": _translate_print_error(error_code, error_hex),
    }


def _find_printer(printer_name: str | None) -> PrinterConfig | None:
    if not cfg.printers:
        return None
    if not printer_name:
        return cfg.printers[0]
    return next((x for x in cfg.printers if x.name == printer_name), None)


def _measure_scaled_xy(
    stl_path: str,
    scale_percent: float | None,
    target_max_extent_mm: float | None,
    orientation_mode: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"available": False}
    mesh = trimesh.load(stl_path, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or mesh.vertices is None or len(mesh.vertices) == 0:
        return {"available": False, "reason": "invalid_mesh"}
    try:
        _apply_orientation_inplace(mesh, orientation_mode)
    except Exception:
        # If orientation transform fails, continue with original mesh for fit estimate.
        pass

    ext = mesh.extents
    x = float(ext[0]) if ext is not None and len(ext) > 0 else 0.0
    y = float(ext[1]) if ext is not None and len(ext) > 1 else 0.0
    z = float(ext[2]) if ext is not None and len(ext) > 2 else 0.0
    max_e = max(x, y, z)
    if max_e <= 0:
        return {"available": False, "reason": "non_positive_extent"}

    scale_factor = 1.0
    if target_max_extent_mm is not None and target_max_extent_mm > 0:
        scale_factor = float(target_max_extent_mm) / max_e
    elif scale_percent is not None and scale_percent > 0:
        scale_factor = float(scale_percent) / 100.0

    out.update(
        {
            "available": True,
            "x_mm": x * scale_factor,
            "y_mm": y * scale_factor,
            "z_mm": z * scale_factor,
            "max_extent_mm": max_e * scale_factor,
            "scale_factor": scale_factor,
            "source_max_extent_mm": max_e,
        }
    )
    return out


def _recommend_printer(req: SliceAndSendRequest) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for p in cfg.printers:
        score = 0.0
        notes: list[str] = []
        st: dict[str, Any] | None = None
        err: str | None = None
        try:
            if not p.serial:
                raise RuntimeError("missing serial")
            st = get_printer_status(
                BambuPrinterConfig(ip=p.ip, access_code=p.access_code, serial=p.serial)
            )
        except Exception as e:
            err = str(e)

        if err:
            score -= 120
            notes.append(f"status unavailable: {err}")
        else:
            state = str(st.get("gcode_state") or "").upper()
            if state in {"RUNNING", "PREPARE"}:
                score -= 100
                notes.append("currently busy")
            elif state in {"PAUSE", "FAILED"}:
                score += 10
                notes.append("paused/failed but can accept next job after stop")
            else:
                score += 50
                notes.append("idle or ready")

            if _to_int(st.get("print_error", 0), 0) == 0:
                score += 8
            else:
                score -= 20
                notes.append("printer has active error")

            nozzle_live = _to_float(st.get("nozzle_diameter"))
            if nozzle_live is not None:
                if abs(nozzle_live - float(req.nozzle_mm)) <= 0.01:
                    score += 24
                    notes.append("nozzle matches request")
                else:
                    score -= 18
                    notes.append(f"nozzle mismatch ({nozzle_live} vs {req.nozzle_mm})")

            trays = st.get("ams", {}).get("trays", []) if isinstance(st.get("ams"), dict) else []
            if req.use_ams:
                if req.ams_slot:
                    if any(_to_int(t.get("slot", -1), -1) == _to_int(req.ams_slot, -2) for t in trays):
                        score += 18
                        notes.append("requested AMS slot is available")
                    else:
                        score -= 35
                        notes.append("requested AMS slot missing")
                else:
                    if trays:
                        score += 8
                        notes.append("AMS available")

        candidates.append(
            {
                "printer_name": p.name,
                "score": round(score, 2),
                "notes": notes,
                "state": (st.get("gcode_state") if st else None),
                "error": err,
            }
        )

    candidates.sort(key=lambda x: x.get("score", -9999), reverse=True)
    recommended = candidates[0]["printer_name"] if candidates else None
    return {
        "recommended_printer_name": recommended,
        "candidates": candidates,
    }


def _run_preflight(req: SliceAndSendRequest, *, ignore_busy: bool = False) -> dict[str, Any]:
    payload = _model_dump(req)
    issues: list[dict[str, Any]] = []
    fixes: dict[str, Any] = {}

    stl_abs = os.path.abspath(req.stl_path)
    runs_abs = os.path.abspath(RUNS_DIR)
    if not stl_abs.startswith(runs_abs) or not os.path.exists(stl_abs):
        issues.append(_build_issue("stl_missing", "block", "STL file was not found in runs directory.", field="stl_path"))
        return {
            "can_print": False,
            "issues": issues,
            "auto_fix_payload": {**payload, **fixes},
            "recommended_printer": None,
        }

    recommendation = _recommend_printer(req) if req.auto_route else None
    effective_printer_name = req.printer_name
    if recommendation and recommendation.get("recommended_printer_name"):
        rec_name = str(recommendation["recommended_printer_name"])
        if rec_name and rec_name != req.printer_name:
            fixes["printer_name"] = rec_name
            effective_printer_name = rec_name
            issues.append(
                _build_issue(
                    "auto_route_recommendation",
                    "info",
                    f"Auto-route recommends {rec_name} for faster or safer dispatch.",
                    field="printer_name",
                    suggested_fix={"printer_name": rec_name},
                )
            )

    p = _find_printer(effective_printer_name)
    if not p:
        issues.append(_build_issue("unknown_printer", "block", "Selected printer is not configured.", field="printer_name"))
        return {
            "can_print": False,
            "issues": issues,
            "auto_fix_payload": {**payload, **fixes},
            "recommended_printer": recommendation,
        }
    if not p.serial:
        issues.append(_build_issue("missing_serial", "block", "Printer serial is missing in backend config.", field="printer_name"))

    # Fit check from STL geometry.
    try:
        dims = _measure_scaled_xy(
            stl_abs,
            req.scale_percent,
            req.target_max_extent_mm,
            req.orientation_mode,
        )
        if dims.get("available"):
            x_mm = float(dims.get("x_mm", 0))
            y_mm = float(dims.get("y_mm", 0))
            if x_mm > 256.0 or y_mm > 256.0:
                ratio = min(256.0 / max(x_mm, 1e-6), 256.0 / max(y_mm, 1e-6))
                if req.target_max_extent_mm is not None and req.target_max_extent_mm > 0:
                    fixes["target_max_extent_mm"] = round(float(req.target_max_extent_mm) * ratio, 1)
                elif req.scale_percent is not None and req.scale_percent > 0:
                    fixes["scale_percent"] = round(float(req.scale_percent) * ratio, 1)
                else:
                    fixes["target_max_extent_mm"] = round(float(dims.get("max_extent_mm", 0)) * ratio, 1)
                issues.append(
                    _build_issue(
                        "plate_fit",
                        "block",
                        f"Model footprint is too large for 256x256 plate ({x_mm:.1f} x {y_mm:.1f} mm).",
                        field="target_max_extent_mm",
                        suggested_fix={k: fixes[k] for k in ("target_max_extent_mm", "scale_percent") if k in fixes},
                    )
                )
    except Exception as e:
        issues.append(_build_issue("fit_check_failed", "warn", f"Could not validate model fit: {e}"))

    status: dict[str, Any] | None = None
    try:
        status = get_printer_status(
            BambuPrinterConfig(ip=p.ip, access_code=p.access_code, serial=p.serial or "")
        )
    except Exception as e:
        issues.append(_build_issue("status_unavailable", "warn", f"Could not read live printer status: {e}"))

    if status:
        state = str(status.get("gcode_state") or "").upper()
        if state in {"RUNNING", "PREPARE"}:
            subtask = str(status.get("subtask_name") or "unknown job")
            issues.append(
                _build_issue(
                    "printer_busy",
                    ("warn" if ignore_busy else "block"),
                    f"Printer is currently {state.lower()} ({subtask}).",
                    field="printer_name",
                )
            )

        error_code = _to_int(status.get("print_error", 0), 0)
        error_hex = status.get("print_error_hex")
        if error_code:
            issues.append(
                _build_issue(
                    "printer_error",
                    "block",
                    _translate_print_error(error_code, error_hex) or "Printer reported an active error.",
                )
            )

        nozzle_live = _to_float(status.get("nozzle_diameter"))
        if nozzle_live is not None and abs(nozzle_live - float(req.nozzle_mm)) > 0.01:
            fixes["nozzle_mm"] = nozzle_live
            issues.append(
                _build_issue(
                    "nozzle_mm_mismatch",
                    "block",
                    f"Printer nozzle is {nozzle_live:.1f}mm but request is {float(req.nozzle_mm):.1f}mm.",
                    field="nozzle_mm",
                    suggested_fix={"nozzle_mm": nozzle_live},
                )
            )

        nozzle_type_live = str(status.get("nozzle_type") or "").strip().lower()
        nozzle_type_live_norm = _normalize_nozzle_type(nozzle_type_live)
        nozzle_type_req_norm = _normalize_nozzle_type(req.nozzle_type)
        if nozzle_type_live_norm and nozzle_type_req_norm and nozzle_type_live_norm != nozzle_type_req_norm:
            mapped = nozzle_type_live_norm
            fixes["nozzle_type"] = mapped
            issues.append(
                _build_issue(
                    "nozzle_type_mismatch",
                    "block",
                    f"Printer nozzle type is '{nozzle_type_live}' ({nozzle_type_live_norm}), request is '{req.nozzle_type}' ({nozzle_type_req_norm}).",
                    field="nozzle_type",
                    suggested_fix={"nozzle_type": mapped},
                )
            )

        trays = status.get("ams", {}).get("trays", []) if isinstance(status.get("ams"), dict) else []
        if req.use_ams:
            if not trays:
                issues.append(_build_issue("ams_unavailable", "warn", "AMS is not reporting trays."))
            else:
                if _request_is_keychain(req) and len(trays) < 3:
                    issues.append(
                        _build_issue(
                            "ams_multicolor_unavailable",
                            "block",
                            "Bridge keychain multicolor needs at least 3 loaded AMS trays.",
                            field="printer_name",
                        )
                    )
                if req.ams_slot is not None:
                    tray = next((t for t in trays if _to_int(t.get("slot", -1), -1) == _to_int(req.ams_slot, -2)), None)
                    if tray is None:
                        fallback_slot = _preferred_ams_slot(
                            req,
                            trays,
                            active_slot=_to_int(status.get("ams", {}).get("active_slot"), 0),
                        ) or _to_int(trays[0].get("slot", 1), 1)
                        fixes["ams_slot"] = fallback_slot
                        issues.append(
                            _build_issue(
                                "ams_slot_missing",
                                "block",
                                f"Requested AMS slot {req.ams_slot} is not available.",
                                field="ams_slot",
                                suggested_fix={"ams_slot": fallback_slot},
                            )
                        )
                else:
                    active_slot = _to_int(status.get("ams", {}).get("active_slot"), 0)
                    suggested = _preferred_ams_slot(req, trays, active_slot=active_slot) or _to_int(trays[0].get("slot", 1), 1)
                    fixes["ams_slot"] = suggested
                    issues.append(
                        _build_issue(
                            "ams_slot_defaulted",
                            "info",
                            f"No AMS slot selected. Using slot {suggested}.",
                            field="ams_slot",
                            suggested_fix={"ams_slot": suggested},
                        )
                    )

    can_print = not any(i.get("severity") == "block" for i in issues)
    return {
        "can_print": can_print,
        "issues": issues,
        "recommended_printer": recommendation,
        "status_snapshot": (_augment_status_payload(status) if status else None),
        "auto_fix_payload": {**payload, **fixes},
    }


def _ensure_queue_worker() -> None:
    global _QUEUE_THREAD
    if _QUEUE_THREAD and _QUEUE_THREAD.is_alive():
        return
    _QUEUE_STOP.clear()
    _QUEUE_THREAD = threading.Thread(target=_queue_worker_loop, daemon=True, name="printmind-queue-worker")
    _QUEUE_THREAD.start()


def _decode_json_response(resp: JSONResponse) -> dict[str, Any]:
    try:
        return json.loads(resp.body.decode("utf-8", errors="replace"))
    except Exception:
        return {}


def _queue_worker_loop() -> None:
    while not _QUEUE_STOP.is_set():
        job: dict[str, Any] | None = None
        with _QUEUE_LOCK:
            for item in _QUEUE_ITEMS:
                if item.get("status") == "queued":
                    item["status"] = "running"
                    item["started_at"] = _now_iso()
                    job = item
                    break
        if not job:
            time.sleep(0.35)
            continue

        try:
            req = SliceAndSendRequest(**job["request"])
            out = _run_slice_request(req, estimate_only=False, from_queue=True)
            if isinstance(out, JSONResponse):
                err_doc = _decode_json_response(out)
                err_msg = err_doc.get("error") or f"Queue job failed ({out.status_code})"
                pre = err_doc.get("preflight") if isinstance(err_doc, dict) else None
                issues = pre.get("issues") if isinstance(pre, dict) else []
                has_busy = any(str(i.get("code")) == "printer_busy" for i in (issues or []) if isinstance(i, dict))
                retry_busy = False
                if has_busy:
                    with _QUEUE_LOCK:
                        retries = _to_int(job.get("busy_retries", 0), 0) + 1
                        if retries <= 120:
                            job["busy_retries"] = retries
                            job["status"] = "queued"
                            job["error"] = None
                            job.pop("started_at", None)
                            retry_busy = True
                if retry_busy:
                    time.sleep(1.0)
                    continue
                with _QUEUE_LOCK:
                    job["status"] = "failed"
                    job["finished_at"] = _now_iso()
                    job["error"] = err_msg
                    job["result"] = err_doc
            else:
                with _QUEUE_LOCK:
                    job["status"] = "done"
                    job["finished_at"] = _now_iso()
                    job["result"] = out
                    job["error"] = None
        except Exception as e:
            with _QUEUE_LOCK:
                job["status"] = "failed"
                job["finished_at"] = _now_iso()
                job["error"] = str(e)
                job["result"] = None


def _queue_snapshot() -> list[dict[str, Any]]:
    with _QUEUE_LOCK:
        items = []
        for item in _QUEUE_ITEMS:
            items.append(
                {
                    "job_id": item["job_id"],
                    "status": item["status"],
                    "created_at": item["created_at"],
                    "started_at": item.get("started_at"),
                    "finished_at": item.get("finished_at"),
                    "request": {
                        "printer_name": item["request"].get("printer_name"),
                        "job_name": item["request"].get("job_name"),
                        "mode": item["request"].get("mode"),
                        "ams_slot": item["request"].get("ams_slot"),
                        "auto_start": item["request"].get("auto_start"),
                    },
                    "error": item.get("error"),
                }
            )
        return items


def _prewarm_models_worker() -> None:
    global _PREWARM_RESULT
    try:
        svc = _get_shape_service(load_if_missing=True)
        include_text2image = str(os.environ.get("PREWARM_TEXT2IMAGE", "0")).strip().lower() not in ("0", "false", "no")
        keep_text2image_gpu = str(os.environ.get("PREWARM_TEXT2IMAGE_KEEP_GPU", "0")).strip().lower() not in ("0", "false", "no")
        _PREWARM_RESULT = svc.prewarm_models(
            include_text2image=include_text2image,
            keep_text2image_on_gpu=keep_text2image_gpu,
        )
        print(f"[ShapeService] prewarm result: {_PREWARM_RESULT}")
    except Exception as e:
        _PREWARM_RESULT = {"ok": False, "error": str(e)}
        print(f"[ShapeService] prewarm failed: {e}")


@app.on_event("startup")
def _startup_queue_worker():
    global _PREWARM_THREAD
    _ensure_queue_worker()
    prewarm_enabled = str(os.environ.get("PREWARM_MODELS", "0")).strip().lower() not in ("0", "false", "no")
    if prewarm_enabled and (_PREWARM_THREAD is None or not _PREWARM_THREAD.is_alive()):
        _PREWARM_THREAD = threading.Thread(target=_prewarm_models_worker, daemon=True, name="printmind-model-prewarm")
        _PREWARM_THREAD.start()


@app.on_event("shutdown")
def _shutdown_queue_worker():
    _QUEUE_STOP.set()
    if _QUEUE_THREAD and _QUEUE_THREAD.is_alive():
        _QUEUE_THREAD.join(timeout=1.2)


@app.get("/", response_class=HTMLResponse)
def index():
    with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/health")
def health():
    return _shape_payload(_get_shape_service(load_if_missing=False))


@app.get("/api/templates")
def templates():
    payload = {"items": []}
    svc = _get_keychain_service(load_if_missing=False)
    if svc is not None:
        payload["items"].append(svc.template_payload())
        return payload
    try:
        svc = _get_keychain_service(load_if_missing=True)
        payload["items"].append(svc.template_payload())
    except Exception:
        payload["error"] = _KEYCHAIN_IMPORT_ERROR
    return payload


@app.get("/api/printers")
def printers():
    return [
        {
            "name": p.name,
            "ip": p.ip,
            "serial": getattr(p, "serial", None),
            "has_access_code": bool(p.access_code),
        }
        for p in cfg.printers
    ]


@app.get("/api/printers_admin")
def printers_admin():
    # Full editable data, including access_code, for local protected admin UI.
    return {
        "override_path": printers_override_path(),
        "printers": [
            {
                "name": p.name,
                "ip": p.ip,
                "access_code": p.access_code,
                "serial": getattr(p, "serial", None),
            }
            for p in cfg.printers
        ],
    }


@app.post("/api/printers_admin")
def printers_admin_save(req: PrintersAdminSaveRequest):
    cleaned = []
    seen_names = set()
    for item in req.printers:
        name = item.name.strip()
        ip = item.ip.strip()
        access_code = item.access_code.strip()
        serial = item.serial.strip() if item.serial else None
        if not name or not ip or not access_code:
            continue
        k = name.lower()
        if k in seen_names:
            return JSONResponse({"error": f"duplicate printer name: {name}"}, status_code=400)
        seen_names.add(k)
        cleaned.append(
            PrinterConfig(
                name=name,
                ip=ip,
                access_code=access_code,
                serial=(serial or None),
            )
        )

    if not cleaned:
        return JSONResponse({"error": "at least one valid printer is required"}, status_code=400)

    path = save_printers_override(cleaned)
    _reload_cfg()
    return {
        "saved": True,
        "override_path": path,
        "count": len(cleaned),
        "printers": [
            {"name": p.name, "ip": p.ip, "serial": p.serial, "has_access_code": bool(p.access_code)}
            for p in cfg.printers
        ],
    }


@app.get("/api/printer_status")
def printer_status(printer_name: str | None = None):
    if not cfg.printers:
        return JSONResponse({"error": "no printers configured"}, status_code=500)

    p = cfg.printers[0] if not printer_name else next((x for x in cfg.printers if x.name == printer_name), None)
    if not p:
        return JSONResponse({"error": "unknown printer"}, status_code=400)

    if not getattr(p, "serial", None):
        return JSONResponse({"error": "printer serial missing in config"}, status_code=500)

    try:
        status = get_printer_status(
            BambuPrinterConfig(
                ip=p.ip,
                access_code=p.access_code,
                serial=p.serial,
            )
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return {
        "printer_name": p.name,
        **_augment_status_payload(status),
    }


@app.post("/api/printer_stop")
def printer_stop(req: PrinterCommandRequest):
    if not cfg.printers:
        return JSONResponse({"error": "no printers configured"}, status_code=500)

    p = cfg.printers[0] if not req.printer_name else next((x for x in cfg.printers if x.name == req.printer_name), None)
    if not p:
        return JSONResponse({"error": "unknown printer"}, status_code=400)

    if not getattr(p, "serial", None):
        return JSONResponse({"error": "printer serial missing in config"}, status_code=500)

    try:
        result = send_print_command(
            BambuPrinterConfig(
                ip=p.ip,
                access_code=p.access_code,
                serial=p.serial,
            ),
            "stop",
            sequence_id="api_stop",
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return {"printer_name": p.name, **result}


@app.post("/api/printer_resume")
def printer_resume(req: PrinterCommandRequest):
    if not cfg.printers:
        return JSONResponse({"error": "no printers configured"}, status_code=500)

    p = cfg.printers[0] if not req.printer_name else next((x for x in cfg.printers if x.name == req.printer_name), None)
    if not p:
        return JSONResponse({"error": "unknown printer"}, status_code=400)

    if not getattr(p, "serial", None):
        return JSONResponse({"error": "printer serial missing in config"}, status_code=500)

    try:
        result = send_print_command(
            BambuPrinterConfig(
                ip=p.ip,
                access_code=p.access_code,
                serial=p.serial,
            ),
            "resume",
            sequence_id="api_resume",
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return {"printer_name": p.name, **result}


@app.post("/api/generate")
def generate(req: GenerateRequest):
    if not req.prompt.strip():
        return JSONResponse({"error": "prompt required"}, status_code=400)

    if req.quality_preset not in ("fast", "balanced", "quality"):
        return JSONResponse({"error": "quality_preset must be fast, balanced, or quality"}, status_code=400)

    try:
        result = _get_shape_service(load_if_missing=True).generate(
            req.prompt,
            quality_preset=req.quality_preset,
            request_id=req.request_id,
        )
    except Exception as e:
        if _is_generation_cancelled(e):
            return JSONResponse({"error": "generation cancelled by user", "cancelled": True}, status_code=499)
        if isinstance(e, RuntimeError):
            return JSONResponse({"error": str(e)}, status_code=422)
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

    return {
        "request_id": req.request_id,
        "seconds": result["seconds"],
        "faces": result["faces"],
        "stl_path": result["stl_path"],
        "stl_url": f"/api/stl?path={result['stl_path']}",
        "quality_preset": result.get("quality_preset"),
        "generation_config": result.get("generation_config"),
        "perf": result.get("perf"),
        "dimensions_mm": result.get("dimensions_mm"),
    }


@app.post("/api/templates/keychain/build")
def build_keychain(req: KeychainBuildRequest):
    try:
        result = _get_keychain_service(load_if_missing=True).build_keychain(req.name, name_color=req.name_color)
    except Exception as e:
        if isinstance(e, RuntimeError):
            return JSONResponse({"error": str(e)}, status_code=422)
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

    return {
        "seconds": result["seconds"],
        "faces": result["faces"],
        "name": result["name"],
        "stl_path": result["stl_path"],
        "stl_url": f"/api/stl?path={result['stl_path']}",
        "model_3mf_path": result["model_3mf_path"],
        "model_3mf_url": f"/api/model?path={result['model_3mf_path']}&format=3mf",
        "generation_config": result.get("generation_config"),
        "dimensions_mm": result.get("dimensions_mm"),
        "source_type": result.get("source_type"),
        "template_key": result.get("template_key"),
        "preview_parts": [
            {
                "color_index": item["color_index"],
                "color": item["color"],
                "stl_path": item["stl_path"],
                "stl_url": f"/api/model?path={item['stl_path']}&format=stl",
            }
            for item in result.get("preview_parts", [])
        ],
    }


@app.post("/api/generate_image_upload")
async def generate_image_upload(
    request: Request,
    quality_preset: str = "balanced",
    request_id: str | None = None,
):
    if quality_preset not in ("fast", "balanced", "quality"):
        return JSONResponse({"error": "quality_preset must be fast, balanced, or quality"}, status_code=400)

    ctype = str(request.headers.get("content-type") or "").lower()
    if ctype and not ctype.startswith("image/") and ctype != "application/octet-stream":
        return JSONResponse({"error": f"unsupported content-type: {ctype}"}, status_code=400)

    raw = await request.body()
    if not raw:
        return JSONResponse({"error": "image body required"}, status_code=400)
    if len(raw) > 15 * 1024 * 1024:
        return JSONResponse({"error": "image is too large (max 15MB)"}, status_code=400)

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as e:
        return JSONResponse({"error": f"invalid image payload: {e}"}, status_code=400)

    try:
        result = _get_shape_service(load_if_missing=True).generate_from_image(
            image,
            quality_preset=quality_preset,
            source="upload",
            request_id=request_id,
        )
    except Exception as e:
        if _is_generation_cancelled(e):
            return JSONResponse({"error": "generation cancelled by user", "cancelled": True}, status_code=499)
        if isinstance(e, RuntimeError):
            return JSONResponse({"error": str(e)}, status_code=422)
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

    return {
        "request_id": request_id,
        "seconds": result["seconds"],
        "faces": result["faces"],
        "stl_path": result["stl_path"],
        "stl_url": f"/api/stl?path={result['stl_path']}",
        "quality_preset": result.get("quality_preset"),
        "generation_config": result.get("generation_config"),
        "perf": result.get("perf"),
        "dimensions_mm": result.get("dimensions_mm"),
        "source_type": result.get("source_type"),
        "source_image_path": result.get("source_image_path"),
    }


@app.post("/api/generate_image_url")
def generate_image_url(req: GenerateImageUrlRequest):
    if req.quality_preset not in ("fast", "balanced", "quality"):
        return JSONResponse({"error": "quality_preset must be fast, balanced, or quality"}, status_code=400)

    url = (req.image_url or "").strip()
    if not url:
        return JSONResponse({"error": "image_url required"}, status_code=400)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return JSONResponse({"error": "image_url must be http or https"}, status_code=400)

    try:
        with urllib.request.urlopen(url, timeout=25) as resp:
            ctype = str(resp.headers.get("Content-Type") or "").lower()
            if ctype and not ctype.startswith("image/"):
                return JSONResponse({"error": f"url does not point to an image ({ctype})"}, status_code=400)
            raw = resp.read((15 * 1024 * 1024) + 1)
    except Exception as e:
        return JSONResponse({"error": f"failed to download image: {e}"}, status_code=400)

    if len(raw) > 15 * 1024 * 1024:
        return JSONResponse({"error": "image is too large (max 15MB)"}, status_code=400)

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception as e:
        return JSONResponse({"error": f"downloaded content is not a valid image: {e}"}, status_code=400)

    try:
        result = _get_shape_service(load_if_missing=True).generate_from_image(
            image,
            quality_preset=req.quality_preset,
            source="url",
            request_id=req.request_id,
        )
    except Exception as e:
        if _is_generation_cancelled(e):
            return JSONResponse({"error": "generation cancelled by user", "cancelled": True}, status_code=499)
        if isinstance(e, RuntimeError):
            return JSONResponse({"error": str(e)}, status_code=422)
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

    return {
        "request_id": req.request_id,
        "seconds": result["seconds"],
        "faces": result["faces"],
        "stl_path": result["stl_path"],
        "stl_url": f"/api/stl?path={result['stl_path']}",
        "quality_preset": result.get("quality_preset"),
        "generation_config": result.get("generation_config"),
        "perf": result.get("perf"),
        "dimensions_mm": result.get("dimensions_mm"),
        "source_type": result.get("source_type"),
        "source_image_path": result.get("source_image_path"),
    }


@app.get("/api/generation_status")
def generation_status(request_id: str):
    svc = _get_shape_service(load_if_missing=False)
    if svc is None:
        return {"status": "idle", "request_id": request_id, "message": "Generation service not loaded yet"}
    return svc.get_progress(request_id)


@app.get("/api/perf")
def generation_perf(request_id: str):
    svc = _get_shape_service(load_if_missing=False)
    if svc is None:
        return JSONResponse({"status": "idle", "request_id": request_id, "message": "Generation service not loaded yet"}, status_code=404)
    status = svc.get_progress(request_id)
    if status.get("status") in {"missing_request_id", "not_found"}:
        code = 400 if status.get("status") == "missing_request_id" else 404
        return JSONResponse(status, status_code=code)
    return {
        "request_id": status.get("request_id"),
        "status": status.get("status"),
        "mode": status.get("mode"),
        "quality_preset": status.get("quality_preset"),
        "perf": status.get("perf"),
        "result": status.get("result"),
        "error": status.get("error"),
    }


@app.post("/api/generation_cancel")
def generation_cancel(req: GenerationCancelRequest):
    svc = _get_shape_service(load_if_missing=False)
    if svc is None:
        return JSONResponse({"error": "generation service not loaded"}, status_code=404)
    out = svc.request_cancel(req.request_id)
    if out.get("status") in {"missing_request_id", "not_found"}:
        return JSONResponse(out, status_code=404 if out.get("status") == "not_found" else 400)
    return out


def _run_slice_request(req: SliceAndSendRequest, estimate_only: bool = False, from_queue: bool = False):
    stl_abs = os.path.abspath(req.stl_path)
    runs_abs = os.path.abspath(RUNS_DIR)
    model_3mf_abs = os.path.abspath(req.model_3mf_path) if req.model_3mf_path else None

    if not stl_abs.startswith(runs_abs) or not os.path.exists(stl_abs):
        return JSONResponse({"error": "stl not found"}, status_code=404)
    if model_3mf_abs is not None:
        if (not model_3mf_abs.startswith(runs_abs)) or (not os.path.exists(model_3mf_abs)):
            return JSONResponse({"error": "model_3mf_path not found"}, status_code=404)

    if req.ams_slot is not None and req.ams_slot < 1:
        return JSONResponse({"error": "ams_slot must be >= 1 (left-to-right slot number)"}, status_code=400)
    if req.nozzle_mm not in (0.2, 0.4, 0.6, 0.8):
        return JSONResponse({"error": "nozzle_mm must be one of: 0.2, 0.4, 0.6, 0.8"}, status_code=400)
    req_nozzle_type = _normalize_nozzle_type(req.nozzle_type)
    if req_nozzle_type not in ("hardened_steel", "stainless_steel"):
        return JSONResponse({"error": "nozzle_type must be: hardened_steel or stainless_steel"}, status_code=400)
    if req.infill_percent is not None and (req.infill_percent < 0 or req.infill_percent > 100):
        return JSONResponse({"error": "infill_percent must be between 0 and 100"}, status_code=400)
    if req.scale_percent is not None and (req.scale_percent <= 0 or req.scale_percent > 10000):
        return JSONResponse({"error": "scale_percent must be > 0 and <= 10000"}, status_code=400)
    if req.target_max_extent_mm is not None and (req.target_max_extent_mm <= 0 or req.target_max_extent_mm > 250):
        return JSONResponse({"error": "target_max_extent_mm must be > 0 and <= 250"}, status_code=400)
    if req.size_preset is not None and req.size_preset not in ("small", "medium", "large", "custom"):
        return JSONResponse({"error": "size_preset must be small, medium, large, or custom"}, status_code=400)
    if req.orientation_mode not in ("upright_auto", "keep", "x_up", "y_up", "z_up"):
        return JSONResponse(
            {"error": "orientation_mode must be upright_auto, keep, x_up, y_up, or z_up"},
            status_code=400,
        )
    if req.support_mode not in ("auto", "on", "off"):
        return JSONResponse({"error": "support_mode must be auto, on, or off"}, status_code=400)
    if req.support_type not in ("tree(auto)", "normal(auto)"):
        return JSONResponse({"error": "support_type must be tree(auto) or normal(auto)"}, status_code=400)

    effective_printer_name = req.printer_name
    recommendation = None
    if req.auto_route:
        recommendation = _recommend_printer(req)
        rec_name = recommendation.get("recommended_printer_name")
        if rec_name:
            effective_printer_name = str(rec_name)

    req_payload = _model_dump(req)
    req_payload["printer_name"] = effective_printer_name
    req_payload["nozzle_type"] = req_nozzle_type
    effective_req = SliceAndSendRequest(**req_payload)

    p = _find_printer(effective_printer_name)
    if not p:
        return JSONResponse({"error": "unknown printer"}, status_code=400)
    if not getattr(p, "serial", None):
        return JSONResponse({"error": "printer serial missing in config"}, status_code=500)

    preflight = None
    if (not estimate_only) and (not req.skip_preflight):
        preflight = _run_preflight(effective_req)
        if not preflight.get("can_print", False):
            return JSONResponse(
                {
                    "error": "Preflight failed. Resolve blocking issues before printing.",
                    "preflight": preflight,
                },
                status_code=400,
            )

    try:
        out = run_print_pipeline(
            prusa_console_exe=cfg.prusa_console_exe,
            prusa_profile_ini=cfg.prusa_profile_ini,
            slice_dir=cfg.slice_dir,
            stl_path=stl_abs,
            model_3mf_path=model_3mf_abs,
            printer_ip=p.ip,
            printer_access_code=p.access_code,
            printer_serial=p.serial,
            mode=effective_req.mode,
            auto_start=(effective_req.auto_start if not estimate_only else False),
            job_name=effective_req.job_name,
            use_ams=effective_req.use_ams,
            ams_slot=effective_req.ams_slot,
            bed_leveling=effective_req.bed_leveling,
            flow_cali=effective_req.flow_cali,
            vibration_cali=effective_req.vibration_cali,
            layer_inspect=effective_req.layer_inspect,
            timelapse=effective_req.timelapse,
            bed_type=effective_req.bed_type,
            nozzle_mm=effective_req.nozzle_mm,
            nozzle_type=effective_req.nozzle_type,
            infill_percent=effective_req.infill_percent,
            scale_percent=effective_req.scale_percent,
            target_max_extent_mm=effective_req.target_max_extent_mm,
            size_preset=effective_req.size_preset,
            orientation_mode=effective_req.orientation_mode,
            support_mode=effective_req.support_mode,
            support_enabled=effective_req.support_enabled,
            support_type=effective_req.support_type,
            support_on_build_plate_only=effective_req.support_on_build_plate_only,
            estimate_only=estimate_only,
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

    if isinstance(out, dict):
        out["effective_printer_name"] = effective_printer_name
        if recommendation is not None:
            out["printer_recommendation"] = recommendation
        if preflight is not None:
            out["preflight"] = preflight
        if from_queue:
            out["queued_execution"] = True
    return out


@app.post("/api/preflight")
def preflight(req: SliceAndSendRequest):
    stl_abs = os.path.abspath(req.stl_path)
    runs_abs = os.path.abspath(RUNS_DIR)
    if not stl_abs.startswith(runs_abs) or not os.path.exists(stl_abs):
        return JSONResponse({"error": "stl not found"}, status_code=404)
    return _run_preflight(req)


@app.post("/api/printer_recommend")
def printer_recommend(req: SliceAndSendRequest):
    return _recommend_printer(req)


@app.get("/api/queue")
def queue_list():
    items = _queue_snapshot()
    return {
        "active": next((i["job_id"] for i in items if i.get("status") == "running"), None),
        "items": items,
    }


@app.get("/api/control_center")
def control_center(printer_name: str | None = None):
    health_payload = _shape_payload(_get_shape_service(load_if_missing=False))

    printers_payload = [
        {
            "name": p.name,
            "ip": p.ip,
            "serial": getattr(p, "serial", None),
            "has_access_code": bool(p.access_code),
        }
        for p in cfg.printers
    ]

    selected_printer = printer_name
    if not selected_printer and cfg.printers:
        selected_printer = cfg.printers[0].name

    printer_payload = None
    printer_error = None
    if selected_printer:
        p = _find_printer(selected_printer)
        if not p:
            printer_error = "unknown printer"
        elif not getattr(p, "serial", None):
            printer_error = "printer serial missing in config"
        else:
            try:
                status = get_printer_status(
                    BambuPrinterConfig(
                        ip=p.ip,
                        access_code=p.access_code,
                        serial=p.serial,
                    )
                )
                printer_payload = {
                    "printer_name": p.name,
                    **_augment_status_payload(status),
                }
            except Exception as e:
                printer_error = str(e)

    return {
        "health": health_payload,
        "printers": printers_payload,
        "selected_printer": selected_printer,
        "printer_status": printer_payload,
        "printer_status_error": printer_error,
        "queue": queue_list(),
    }


@app.post("/api/queue/enqueue")
def queue_enqueue(req: SliceAndSendRequest):
    if not cfg.printers:
        return JSONResponse({"error": "no printers configured"}, status_code=500)

    pre = _run_preflight(req, ignore_busy=True)
    if not pre.get("can_print", False):
        return JSONResponse(
            {"error": "Preflight failed. Queue item not added.", "preflight": pre},
            status_code=400,
        )

    payload = _model_dump(req)
    payload["skip_preflight"] = False
    job_id = uuid.uuid4().hex
    item = {
        "job_id": job_id,
        "status": "queued",
        "created_at": _now_iso(),
        "request": payload,
        "result": None,
        "error": None,
    }
    with _QUEUE_LOCK:
        _QUEUE_ITEMS.append(item)
        position = sum(1 for i in _QUEUE_ITEMS if i.get("status") == "queued")
    _ensure_queue_worker()
    return {"queued": True, "job_id": job_id, "position": position, "preflight": pre}


@app.post("/api/queue/{job_id}/cancel")
def queue_cancel(job_id: str):
    with _QUEUE_LOCK:
        for item in _QUEUE_ITEMS:
            if item.get("job_id") != job_id:
                continue
            if item.get("status") == "queued":
                item["status"] = "cancelled"
                item["finished_at"] = _now_iso()
                item["error"] = "cancelled by user"
                return {"cancelled": True, "job_id": job_id}
            return JSONResponse(
                {"error": f"job {job_id} is not queued (status={item.get('status')})"},
                status_code=400,
            )
    return JSONResponse({"error": "queue job not found"}, status_code=404)


@app.post("/api/queue/clear")
def queue_clear():
    removed = 0
    with _QUEUE_LOCK:
        for item in _QUEUE_ITEMS:
            if item.get("status") == "queued":
                item["status"] = "cancelled"
                item["finished_at"] = _now_iso()
                item["error"] = "cancelled by queue clear"
                removed += 1
    return {"cleared": removed}


@app.post("/api/slice_send")
def slice_send(req: SliceAndSendRequest):
    return _run_slice_request(req, estimate_only=False)


@app.post("/api/slice_estimate")
def slice_estimate(req: SliceAndSendRequest):
    return _run_slice_request(req, estimate_only=True)


@app.get("/api/stl")
def get_stl(path: str):
    path = _safe_run_path(path)
    if not path:
        return JSONResponse({"error": "not found"}, status_code=404)

    return FileResponse(path, media_type="model/stl", filename="model.stl")


@app.get("/api/model")
def get_model_file(path: str, format: str = "stl"):
    safe_path = _safe_run_path(path)
    if not safe_path:
        return JSONResponse({"error": "not found"}, status_code=404)

    try:
        export_path, media_type, filename = _export_model_variant(safe_path, format)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse({"error": f"failed to export {format}: {e}"}, status_code=500)

    return FileResponse(export_path, media_type=media_type, filename=filename)
