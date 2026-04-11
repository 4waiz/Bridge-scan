from __future__ import annotations

from dataclasses import dataclass
import ftplib
from io import BytesIO
import zipfile
import ssl
import time
import json
import re
import os

import bambulabs_api as bl
import paho.mqtt.client as mqtt
from PIL import Image, ImageDraw


@dataclass(frozen=True)
class BambuPrinterConfig:
    ip: str
    access_code: str
    serial: str


_MOVE_RE = re.compile(r"([XYEF])([-+]?[0-9]*\.?[0-9]+)")


def _tls_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _render_gcode_thumbnail_png(gcode_text: str, size: int) -> bytes:
    x = 0.0
    y = 0.0
    e = 0.0
    abs_xyz = True
    abs_e = True
    segments: list[tuple[float, float, float, float]] = []

    for raw in gcode_text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue

        if line.startswith("G90"):
            abs_xyz = True
            continue
        if line.startswith("G91"):
            abs_xyz = False
            continue
        if line.startswith("M82"):
            abs_e = True
            continue
        if line.startswith("M83"):
            abs_e = False
            continue
        if line.startswith("G92"):
            vals = dict(_MOVE_RE.findall(line))
            if "E" in vals:
                e = float(vals["E"])
            continue

        if not (line.startswith("G0") or line.startswith("G1")):
            continue

        vals = dict(_MOVE_RE.findall(line))
        nx = x
        ny = y
        ne = e

        if "X" in vals:
            vx = float(vals["X"])
            nx = vx if abs_xyz else (x + vx)
        if "Y" in vals:
            vy = float(vals["Y"])
            ny = vy if abs_xyz else (y + vy)
        if "E" in vals:
            ve = float(vals["E"])
            ne = ve if abs_e else (e + ve)

        is_extrude = ("E" in vals) and (ne > e + 1e-6)
        if is_extrude and (nx != x or ny != y):
            segments.append((x, y, nx, ny))

        x, y, e = nx, ny, ne

    img = Image.new("RGB", (size, size), (242, 244, 247))
    draw = ImageDraw.Draw(img)

    if not segments:
        draw.rectangle((0, 0, size - 1, size - 1), outline=(170, 176, 184), width=2)
        bio = BytesIO()
        img.save(bio, format="PNG", optimize=True)
        return bio.getvalue()

    xs = [v for s in segments for v in (s[0], s[2])]
    ys = [v for s in segments for v in (s[1], s[3])]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    dx = max(1e-6, max_x - min_x)
    dy = max(1e-6, max_y - min_y)

    pad = int(size * 0.08)
    inner = max(1, size - 2 * pad)
    scale = min(inner / dx, inner / dy)
    ox = pad + (inner - dx * scale) * 0.5
    oy = pad + (inner - dy * scale) * 0.5

    width = max(1, int(size * 0.006))
    for x1, y1, x2, y2 in segments:
        px1 = ox + (x1 - min_x) * scale
        py1 = size - (oy + (y1 - min_y) * scale)
        px2 = ox + (x2 - min_x) * scale
        py2 = size - (oy + (y2 - min_y) * scale)
        draw.line((px1, py1, px2, py2), fill=(24, 54, 82), width=width)

    draw.rectangle((0, 0, size - 1, size - 1), outline=(170, 176, 184), width=2)

    bio = BytesIO()
    img.save(bio, format="PNG", optimize=True)
    return bio.getvalue()


def build_3mf_from_gcode_text(
    gcode_text: str,
    gcode_location: str = "Metadata/plate_1.gcode",
) -> BytesIO:
    bio = BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(gcode_location, gcode_text)
        thumb_mid = _render_gcode_thumbnail_png(gcode_text, size=512)
        thumb_small = _render_gcode_thumbnail_png(gcode_text, size=256)
        zf.writestr("Metadata/plate_1.png", thumb_mid)
        zf.writestr("Metadata/plate_1_small.png", thumb_small)
        zf.writestr("Metadata/top_1.png", thumb_mid)
        zf.writestr("Metadata/pick_1.png", thumb_mid)
    bio.seek(0)
    return bio


class _ImplicitFTPTLSSessionReuse(ftplib.FTP_TLS):
    """Implicit FTPS client that reuses TLS session for data connections."""

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,
            )
        return conn, size


def _upload_file_via_ftps(
    printer: BambuPrinterConfig,
    file_obj: BytesIO,
    remote_name: str,
) -> str:
    ftps = _ImplicitFTPTLSSessionReuse()
    ftps.context = ssl.create_default_context()
    ftps.context.check_hostname = False
    ftps.context.verify_mode = ssl.CERT_NONE

    ftps.connect(host=printer.ip, port=990, timeout=20)
    ftps.login("bblp", printer.access_code)
    ftps.prot_p()

    try:
        file_obj.seek(0)
        return ftps.storbinary(f"STOR {remote_name}", file_obj, blocksize=32768)
    finally:
        try:
            ftps.close()
        except Exception:
            pass


def _connect(printer: BambuPrinterConfig):
    # bambulabs_api.Printer expects (ip, access_code, serial)
    p = bl.Printer(printer.ip, printer.access_code, printer.serial)

    try:
        p._ssl_context = _tls_context()
    except Exception:
        pass

    # Avoid camera thread start/stop bugs in bambulabs-api that can block
    # disconnect() forever on some versions.
    try:
        cam = p._Printer__printerCamera
        cam.start = lambda *args, **kwargs: None
        cam.stop = lambda *args, **kwargs: None
    except Exception:
        pass

    p.connect()

    # connect() is async; wait briefly so start_print doesn't race MQTT setup.
    try:
        mqtt_client = p._Printer__printerMQTTClient._client
        deadline = time.time() + 10
        while time.time() < deadline:
            if mqtt_client.is_connected():
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("MQTT handshake timed out")
    except Exception:
        raise

    return p


def upload_3mf(
    printer: BambuPrinterConfig,
    gcode_text: str,
    upload_name: str,
) -> str:

    if not upload_name.endswith(".3mf"):
        upload_name = upload_name + ".3mf"

    io_file = build_3mf_from_gcode_text(gcode_text)
    try:
        _upload_file_via_ftps(printer, io_file, upload_name)
    except Exception as e:
        raise RuntimeError(f"FTPS upload failed: {e}")

    return upload_name


def upload_3mf_file(
    printer: BambuPrinterConfig,
    local_3mf_path: str,
    upload_name: str | None = None,
) -> str:

    if not os.path.exists(local_3mf_path):
        raise RuntimeError(f"3MF not found: {local_3mf_path}")

    remote_name = upload_name or os.path.basename(local_3mf_path)
    if not remote_name.endswith(".3mf"):
        remote_name = remote_name + ".3mf"

    with open(local_3mf_path, "rb") as f:
        io_file = BytesIO(f.read())

    try:
        _upload_file_via_ftps(printer, io_file, remote_name)
    except Exception as e:
        raise RuntimeError(f"FTPS upload failed: {e}")

    return remote_name


def _to_int(value, default=0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def get_printer_status(printer: BambuPrinterConfig) -> dict:
    state: dict = {}
    topic_request = f"device/{printer.serial}/request"
    topic_report = f"device/{printer.serial}/report"

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set("bblp", printer.access_code)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    def _on_connect(c, _u, _f, _rc, _p=None):
        c.subscribe(topic_report)
        c.publish(topic_request, json.dumps({"pushing": {"command": "pushall"}}))

    def _on_message(_c, _u, msg):
        try:
            doc = json.loads(msg.payload.decode("utf-8", errors="replace"))
            if "print" in doc and isinstance(doc["print"], dict):
                state.update(doc["print"])
        except Exception:
            pass

    client.on_connect = _on_connect
    client.on_message = _on_message

    client.connect(printer.ip, 8883, 60)
    client.loop_start()
    try:
        for _ in range(10):
            if state:
                break
            client.publish(topic_request, json.dumps({"pushing": {"command": "pushall"}}))
            time.sleep(0.5)
    finally:
        client.loop_stop()
        client.disconnect()

    data = dict(state)
    error_code = _to_int(data.get("print_error", 0), 0)

    ams_data = data.get("ams") if isinstance(data.get("ams"), dict) else {}
    trays: list[dict] = []
    active_slot: int | None = None

    tray_now = str(ams_data.get("tray_now", "255"))
    if tray_now.isdigit():
        now_raw = int(tray_now)
        if now_raw != 255:
            active_slot = now_raw + 1

    ams_units = ams_data.get("ams", []) if isinstance(ams_data.get("ams", []), list) else []
    for ams_unit in ams_units:
        if not isinstance(ams_unit, dict):
            continue
        ams_id = _to_int(ams_unit.get("id", 0), 0)
        for tray in ams_unit.get("tray", []) or []:
            if not isinstance(tray, dict):
                continue
            tray_id = _to_int(tray.get("id", 0), 0)
            slot = ams_id * 4 + tray_id + 1
            trays.append(
                {
                    "slot": slot,
                    "tray_id": tray_id,
                    "ams_id": ams_id,
                    "type": tray.get("tray_type"),
                    "sub_brand": tray.get("tray_sub_brands"),
                    "color": tray.get("tray_color"),
                    "state": tray.get("state"),
                }
            )

    return {
        "gcode_state": data.get("gcode_state"),
        "percent": _to_int(data.get("mc_percent", 0), 0),
        "remaining_minutes": _to_int(data.get("mc_remaining_time", 0), 0),
        "print_error": error_code,
        "print_error_hex": (f"{error_code:08X}" if error_code else None),
        "subtask_name": data.get("subtask_name"),
        "gcode_file": data.get("gcode_file"),
        "nozzle_diameter": data.get("nozzle_diameter"),
        "nozzle_type": data.get("nozzle_type"),
        "nozzle_temper": data.get("nozzle_temper"),
        "nozzle_target_temper": data.get("nozzle_target_temper"),
        "bed_temper": data.get("bed_temper"),
        "bed_target_temper": data.get("bed_target_temper"),
        "stg_cur": data.get("stg_cur"),
        "ams": {
            "active_slot": active_slot,
            "trays": trays,
        },
        "raw": data,
    }


def send_print_command(printer: BambuPrinterConfig, command: str, sequence_id: str = "manual") -> dict:
    state: dict = {}
    ack: dict = {}
    connected = False

    topic_request = f"device/{printer.serial}/request"
    topic_report = f"device/{printer.serial}/report"

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set("bblp", printer.access_code)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    def _on_connect(c, _u, _f, _rc, _p=None):
        nonlocal connected
        connected = True
        c.subscribe(topic_report)
        c.publish(topic_request, json.dumps({"pushing": {"command": "pushall"}}))

    def _on_message(_c, _u, msg):
        try:
            doc = json.loads(msg.payload.decode("utf-8", errors="replace"))
            pdoc = doc.get("print")
            if isinstance(pdoc, dict):
                state.update(pdoc)
                if pdoc.get("command") == command:
                    ack.clear()
                    ack.update(pdoc)
        except Exception:
            pass

    client.on_connect = _on_connect
    client.on_message = _on_message

    def _publish(payload: dict):
        msg = client.publish(topic_request, json.dumps(payload))
        msg.wait_for_publish(timeout=3)

    client.connect(printer.ip, 8883, 60)
    client.loop_start()
    try:
        for _ in range(10):
            if connected:
                break
            time.sleep(0.2)
        if not connected:
            raise RuntimeError("MQTT handshake timed out")

        _publish({"pushing": {"command": "pushall"}})
        time.sleep(0.5)
        _publish({"print": {"command": command, "sequence_id": str(sequence_id)}})

        for _ in range(8):
            time.sleep(0.5)
            _publish({"pushing": {"command": "pushall"}})
            time.sleep(0.2)
            if ack:
                break

        return {
            "command": command,
            "ack": dict(ack),
            "state": {
                "gcode_state": state.get("gcode_state"),
                "print_error": _to_int(state.get("print_error", 0), 0),
                "subtask_name": state.get("subtask_name"),
            },
        }
    finally:
        client.loop_stop()
        client.disconnect()


def start_print(
    printer: BambuPrinterConfig,
    upload_name: str,
    plate: int = 1,
    use_ams: bool = True,
    ams_slot: int | None = None,
    ams_mapping: list[int] | None = None,
    bed_leveling: bool = True,
    flow_cali: bool = True,
    vibration_cali: bool = True,
    layer_inspect: bool = False,
    timelapse: bool = False,
):

    if not upload_name.endswith(".3mf"):
        upload_name = upload_name + ".3mf"
    state: dict = {}
    project_ack: dict = {}
    connected = False

    topic_request = f"device/{printer.serial}/request"
    topic_report = f"device/{printer.serial}/report"

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set("bblp", printer.access_code)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS, cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)

    def _on_connect(c, _u, _f, _rc, _p=None):
        nonlocal connected
        connected = True
        c.subscribe(topic_report)
        c.publish(topic_request, json.dumps({"pushing": {"command": "pushall"}}))

    def _on_message(_c, _u, msg):
        try:
            doc = json.loads(msg.payload.decode("utf-8", errors="replace"))
            pdoc = doc.get("print")
            if isinstance(pdoc, dict):
                state.update(pdoc)
                if pdoc.get("command") == "project_file":
                    project_ack.clear()
                    project_ack.update(pdoc)
        except Exception:
            pass

    client.on_connect = _on_connect
    client.on_message = _on_message

    def _publish(payload: dict):
        msg = client.publish(topic_request, json.dumps(payload))
        msg.wait_for_publish(timeout=3)

    def _refresh_state(rounds: int = 2, delay_s: float = 0.5):
        for _ in range(rounds):
            _publish({"pushing": {"command": "pushall"}})
            time.sleep(delay_s)

    client.connect(printer.ip, 8883, 60)
    client.loop_start()
    try:
        for _ in range(10):
            if connected:
                break
            time.sleep(0.2)
        if not connected:
            raise RuntimeError("MQTT handshake timed out")

        # Refresh initial state.
        _refresh_state(rounds=2, delay_s=0.5)

        st0 = str(state.get("gcode_state", "")).upper()
        err0 = _to_int(state.get("print_error", 0), 0)
        subtask0 = str(state.get("subtask_name", "") or "")

        # Do not kill an active print unless it is this same file.
        if st0 in {"RUNNING", "PREPARE"} and subtask0 and subtask0 != upload_name:
            raise RuntimeError(
                f"Printer is busy with another job (state={st0}, subtask={subtask0})"
            )

        # Clear stale paused/failed/error sessions, otherwise project_file may be rejected.
        if st0 in {"FAILED", "PAUSE"} or err0 != 0:
            _publish({"print": {"command": "stop", "sequence_id": "cleanup"}})
            time.sleep(1.0)
            _refresh_state(rounds=2, delay_s=0.6)

        effective_ams_mapping = [0]
        if use_ams and ams_mapping:
            effective_ams_mapping = [int(item) for item in ams_mapping if int(item) >= 0]
        elif use_ams and ams_slot is not None and ams_slot > 0:
            effective_ams_mapping = [ams_slot - 1]

        payload = {
            "print": {
                "command": "project_file",
                "sequence_id": "0",
                "param": f"Metadata/plate_{int(plate)}.gcode",
                "subtask_name": upload_name,
                "url": f"ftp://{upload_name}",
                "bed_leveling": bool(bed_leveling),
                "flow_cali": bool(flow_cali),
                "vibration_cali": bool(vibration_cali),
                "layer_inspect": bool(layer_inspect),
                "timelapse": bool(timelapse),
                "use_ams": bool(use_ams),
                "ams_mapping": effective_ams_mapping,
            }
        }
        _publish(payload)
        retried_after_error_state = False

        # Retry resume because X1C may pause on warnings before RUNNING.
        for attempt in range(12):
            time.sleep(1.2)
            _refresh_state(rounds=1, delay_s=0.4)

            st = str(state.get("gcode_state", "")).upper()
            err = _to_int(state.get("print_error", 0), 0)
            subtask = str(state.get("subtask_name", "") or "")

            if project_ack.get("result", "").upper() == "FAIL":
                reason = str(project_ack.get("reason", "") or "")
                if (
                    (not retried_after_error_state)
                    and reason.upper() == "ERROR STATE"
                ):
                    _publish({"print": {"command": "stop", "sequence_id": "cleanup_retry"}})
                    time.sleep(1.0)
                    _refresh_state(rounds=2, delay_s=0.6)
                    project_ack.clear()
                    _publish(payload)
                    retried_after_error_state = True
                    continue
                raise RuntimeError(
                    f"Printer rejected project_file (reason={reason or 'UNKNOWN'})"
                )

            if st in {"RUNNING", "PREPARE"} and subtask == upload_name and err == 0:
                return

            if st == "PAUSE" or err != 0:
                _publish({"print": {"command": "resume", "sequence_id": str(attempt)}})

        final_state = str(state.get("gcode_state", "")).upper()
        final_error = _to_int(state.get("print_error", 0), 0)
        final_subtask = str(state.get("subtask_name", "") or "")
        raise RuntimeError(
            f"Printer did not start job (state={final_state or 'UNKNOWN'}, "
            f"print_error={final_error}, subtask={final_subtask or 'UNKNOWN'})"
        )
    finally:
        client.loop_stop()
        client.disconnect()
