import os
import subprocess

PRUSA_CLI = r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe"

# You must export a config bundle from PrusaSlicer GUI first.
# File → Export → Export Config Bundle
# Save it as:
# backend\prusaconfig.ini

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "prusaconfig.ini")


def slice_stl_to_gcode(stl_path: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)

    gcode_path = os.path.join(output_dir, "print.gcode")

    command = [
        PRUSA_CLI,
        "--load", CONFIG_PATH,
        "--export-gcode",
        stl_path,
        "--output", gcode_path
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"Slicing failed:\n{result.stderr}")

    if not os.path.exists(gcode_path):
        raise RuntimeError("G-code not generated.")

    return gcode_path