import os
import subprocess
import time
import uuid

class SliceResult(dict):
    pass

def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
    )
    return p.returncode, p.stdout

def slice_stl_to_gcode(
    prusa_console_exe: str,
    profile_ini: str,
    stl_path: str,
    out_dir: str,
    mode: str,
    infill_percent: int | None = None,
) -> SliceResult:
    """
    mode: "decorative" | "durable" | "draft"
    Uses a single exported PrusaSlicer config bundle (profile_ini).
    Mode is implemented via an extra .ini override file we generate on the fly.
    """
    os.makedirs(out_dir, exist_ok=True)

    job_id = uuid.uuid4().hex
    gcode_path = os.path.join(out_dir, f"{job_id}.gcode")
    override_ini = os.path.join(out_dir, f"{job_id}.override.ini")

    # Minimal “mode” overrides. These keys are standard Slic3r/PrusaSlicer FFF keys.
    # Keep this conservative; it will work as long as your base profile is valid.
    if mode == "draft":
        override_map = {
            "layer_height": "0.28",
            "perimeters": "2",
            "top_solid_layers": "3",
            "bottom_solid_layers": "3",
            "fill_density": "10%",
        }
    elif mode == "durable":
        override_map = {
            "layer_height": "0.20",
            "perimeters": "4",
            "top_solid_layers": "6",
            "bottom_solid_layers": "6",
            "fill_density": "25%",
        }
    else:  # decorative
        override_map = {
            "layer_height": "0.16",
            "perimeters": "3",
            "top_solid_layers": "5",
            "bottom_solid_layers": "5",
            "fill_density": "15%",
        }

    if infill_percent is not None:
        clamped = max(0, min(100, int(infill_percent)))
        override_map["fill_density"] = f"{clamped}%"

    with open(override_ini, "w", encoding="utf-8") as f:
        f.write("[print:override]\n")
        for k, v in override_map.items():
            f.write(f"{k} = {v}\n")

    t0 = time.time()

    # PrusaSlicer CLI reference: load config from .ini/.3mf then export gcode.  [oai_citation:2‡GitHub](https://github.com/prusa3d/PrusaSlicer/wiki/Command-Line-Interface/f305485eae189f41e905a9012c24a396f3073586?utm_source=chatgpt.com)
    cmd = [
        prusa_console_exe,
        "--load", profile_ini,
        "--load", override_ini,
        "--export-gcode",
        "--output", gcode_path,
        os.path.abspath(stl_path),
    ]

    code, out = _run(cmd)
    dt = time.time() - t0

    if code != 0 or not os.path.exists(gcode_path):
        raise RuntimeError(f"PrusaSlicer failed (exit={code}). Output:\n{out}")

    return SliceResult(
        job_id=job_id,
        seconds=dt,
        gcode_path=gcode_path,
        console=out[-4000:],  # keep last part
        mode=mode,
        infill_percent=infill_percent,
    )
