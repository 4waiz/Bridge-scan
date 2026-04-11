from __future__ import annotations

import os
import shutil
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


def slice_stl_to_3mf_with_bambu(
    bambu_studio_exe: str,
    machine_json: str,
    process_json: str,
    filament_json: str,
    stl_path: str,
    out_dir: str,
) -> SliceResult:
    os.makedirs(out_dir, exist_ok=True)

    job_id = uuid.uuid4().hex
    out_3mf_name = f"{job_id}.bambu.3mf"
    out_3mf_path = os.path.join(out_dir, out_3mf_name)
    plate_gcode_default = os.path.join(out_dir, "plate_1.gcode")
    plate_gcode_path = os.path.join(out_dir, f"{job_id}.plate_1.gcode")

    cmd = [
        bambu_studio_exe,
        "--load-settings",
        f"{os.path.abspath(machine_json)};{os.path.abspath(process_json)}",
        "--load-filaments",
        os.path.abspath(filament_json),
        "--load-defaultfila",
        "--convert-unit",
        "--ensure-on-bed",
        "--arrange",
        "1",
        "--slice",
        "0",
        "--export-3mf",
        out_3mf_name,
        "--outputdir",
        os.path.abspath(out_dir),
        os.path.abspath(stl_path),
    ]

    t0 = time.time()
    code, out = _run(cmd)
    dt = time.time() - t0

    if code != 0 or not os.path.exists(out_3mf_path):
        raise RuntimeError(f"Bambu Studio failed (exit={code}). Output:\n{out}")

    if os.path.exists(plate_gcode_default):
        shutil.copy2(plate_gcode_default, plate_gcode_path)
    else:
        plate_gcode_path = ""

    return SliceResult(
        job_id=job_id,
        seconds=dt,
        gcode_path=plate_gcode_path,
        project_3mf_path=out_3mf_path,
        console=out[-6000:],
        backend="bambu_studio",
        machine_json=os.path.abspath(machine_json),
        process_json=os.path.abspath(process_json),
        filament_json=os.path.abspath(filament_json),
    )


def slice_assembled_stls_to_3mf_with_bambu(
    bambu_studio_exe: str,
    machine_json: str,
    process_json: str,
    filament_jsons: list[str],
    filament_ids: list[int],
    stl_paths: list[str],
    out_dir: str,
) -> SliceResult:
    os.makedirs(out_dir, exist_ok=True)

    if not stl_paths:
        raise ValueError("stl_paths must not be empty")
    if not filament_jsons:
        raise ValueError("filament_jsons must not be empty")
    if len(filament_ids) != len(stl_paths):
        raise ValueError("filament_ids must match stl_paths length")

    job_id = uuid.uuid4().hex
    out_3mf_name = f"{job_id}.bambu.3mf"
    out_3mf_path = os.path.join(out_dir, out_3mf_name)
    plate_gcode_default = os.path.join(out_dir, "plate_1.gcode")
    plate_gcode_path = os.path.join(out_dir, f"{job_id}.plate_1.gcode")

    cmd = [
        bambu_studio_exe,
        "--load-settings",
        f"{os.path.abspath(machine_json)};{os.path.abspath(process_json)}",
        "--load-filaments",
        ";".join(os.path.abspath(path) for path in filament_jsons),
        "--load-filament-ids",
        ",".join(str(int(item)) for item in filament_ids),
        "--allow-multicolor-oneplate",
        "--load-defaultfila",
        "--convert-unit",
        "--ensure-on-bed",
        "--assemble",
        "--arrange",
        "0",
        "--slice",
        "0",
        "--export-3mf",
        out_3mf_name,
        "--outputdir",
        os.path.abspath(out_dir),
        *[os.path.abspath(path) for path in stl_paths],
    ]

    t0 = time.time()
    code, out = _run(cmd)
    dt = time.time() - t0

    if code != 0 or not os.path.exists(out_3mf_path):
        raise RuntimeError(f"Bambu Studio assembly slice failed (exit={code}). Output:\n{out}")

    if os.path.exists(plate_gcode_default):
        shutil.copy2(plate_gcode_default, plate_gcode_path)
    else:
        plate_gcode_path = ""

    return SliceResult(
        job_id=job_id,
        seconds=dt,
        gcode_path=plate_gcode_path,
        project_3mf_path=out_3mf_path,
        console=out[-6000:],
        backend="bambu_studio",
        machine_json=os.path.abspath(machine_json),
        process_json=os.path.abspath(process_json),
        filament_json=";".join(os.path.abspath(path) for path in filament_jsons),
        filament_ids=[int(item) for item in filament_ids],
        input_paths=[os.path.abspath(path) for path in stl_paths],
    )
