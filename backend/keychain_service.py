from __future__ import annotations

import os
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont


CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MAT_NS = "http://schemas.microsoft.com/3dmanufacturing/material/2015/02"
PROD_NS = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
BEAM_NS = "http://schemas.microsoft.com/3dmanufacturing/beamlattice/2017/02"
SLICE_NS = "http://schemas.microsoft.com/3dmanufacturing/slice/2015/07"
SEC_NS = "http://schemas.microsoft.com/3dmanufacturing/securecontent/2019/04"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"m": CORE_NS, "mat": MAT_NS}

ET.register_namespace("", CORE_NS)
ET.register_namespace("m", MAT_NS)
ET.register_namespace("p", PROD_NS)
ET.register_namespace("b", BEAM_NS)
ET.register_namespace("s", SLICE_NS)
ET.register_namespace("sc", SEC_NS)


# 1 word up to 10 chars, OR 2 words each up to 10 chars (rendered as one line)
_NAME_RE = re.compile(r"^[^\s]{1,10}(\s[^\s]{1,10})?$")
_FONT_OVERRIDE_BASENAMES = (
    "bridge_font.ttf",
    "bridge_font.otf",
    "font.ttf",
    "font.otf",
)

# Text window: 70% width, centred in the rectangular plate area (below the ring/loop).
# Ring occupies ~top 25% so text centre targets ~Y 0.375 of total body extent.
_NAME_WINDOW_RATIO_MIN = np.array([0.15, 0.10], dtype=float)
_NAME_WINDOW_RATIO_MAX = np.array([0.85, 0.65], dtype=float)


@dataclass(frozen=True)
class _FontChoice:
    family: str
    path: str
    score: float


@dataclass(frozen=True)
class _ColoredMesh:
    name: str
    color: str
    mesh: trimesh.Trimesh


class KeychainService:
    def __init__(self, template_dir: str, runs_dir: str):
        self.template_dir = os.path.abspath(template_dir)
        self.runs_dir = os.path.abspath(runs_dir)
        os.makedirs(self.runs_dir, exist_ok=True)

        self._template_3mf = self._resolve_required_path("master_keychain_clean.3mf", "master_keychain.3mf")
        self._template_step = self._resolve_optional_path("master_keychain_clean.step", "master_keychain.step")
        self._template_f3d = self._resolve_optional_path("master_keychain_clean.f3d", "master_keychain.f3d")

        self._zip_passthrough: dict[str, bytes] = {}
        self._model_meta: dict[str, Any] = {}
        self._base_object_name = "BridgeKeychain"
        self._base_object_uuid = str(uuid.uuid4())
        self._title = "Bridge Keychain"
        self._template_parts: list[_ColoredMesh] = []
        self._template_bounds = np.zeros((2, 3), dtype=float)
        self._body_bounds = np.zeros((2, 3), dtype=float)
        self._logo_ratio = 5.7
        self._colors: list[str] = []
        self._base_color = "#69707AFF"
        self._name_color = "#69707AFF"
        self._text_bounds = np.zeros((2, 3), dtype=float)
        self._text_anchor_center = np.zeros((3,), dtype=float)
        self._back_surface_z = 0.0
        self._name_depth_mm = 0.3
        self._font_path = ""
        self._font_family = ""
        self._font_exact = False
        self._font_mm_per_px = 0.02
        self._font_point_size = 360
        self._font_shear = 0.18

        self._load_template()
        # Force the body to black — the template 3MF uses gray as a placeholder.
        self._remap_base_to_black()
        self._pick_font()

    def template_payload(self) -> dict[str, Any]:
        ext = self._template_bounds[1] - self._template_bounds[0]
        return {
            "template_key": "bridge_keychain",
            "title": "Bridge keychain",
            "name_limit": 7,
            "placeholder_name": "Name",
            "font_family": self._font_family,
            "font_path": self._font_path,
            "font_exact": self._font_exact,
            "colors": self._ordered_colors(),
            "dimensions_mm": {
                "x": round(float(ext[0]), 3),
                "y": round(float(ext[1]), 3),
                "z": round(float(ext[2] + self._name_depth_mm), 3),
            },
            "back_name_bounds": {
                "min": [round(float(v), 3) for v in self._text_bounds[0]],
                "max": [round(float(v), 3) for v in self._text_bounds[1]],
            },
            "sources": {
                "three_mf": self._template_3mf,
                "step": self._template_step,
                "f3d": self._template_f3d,
            },
        }

    def build_keychain(self, name: str, name_color: str | None = None) -> dict[str, Any]:
        # name_color is intentionally ignored — the name always uses the template accent
        # color so that name + accent merge into a single STL (3-color print: body, accent/name, logo).
        clean_name = self._validate_name(name)
        return self._build_keychain_impl(clean_name)

    def _build_keychain_impl(self, clean_name: str) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        job_dir = os.path.join(self.runs_dir, "keychain", job_id)
        os.makedirs(job_dir, exist_ok=True)

        text_mesh = self._build_name_mesh(clean_name)
        all_meshes = [part.mesh.copy() for part in self._template_parts] + [text_mesh.copy()]
        preview_mesh = trimesh.util.concatenate(all_meshes)

        stl_path = os.path.join(job_dir, "model.stl")
        preview_mesh.export(stl_path)

        model_3mf_path = os.path.join(job_dir, "model.3mf")
        self._write_personalized_3mf(
            out_path=model_3mf_path,
            text_mesh=text_mesh,
            title=f"Bridge Keychain - {clean_name}",
        )

        preview_parts = self._export_preview_parts(job_dir=job_dir, text_mesh=text_mesh)
        bounds = preview_mesh.bounds
        ext = bounds[1] - bounds[0]

        return {
            "job_id": job_id,
            "stl_path": stl_path,
            "model_3mf_path": model_3mf_path,
            "name": clean_name,
            "faces": int(len(preview_mesh.faces)),
            "seconds": 0.0,
            "source_type": "template_keychain",
            "template_key": "bridge_keychain",
            "preview_parts": preview_parts,
            "generation_config": {
                "engine": "bridge-keychain-template",
                "template": "bridge_keychain",
                "font_family": self._font_family,
                "font_path": self._font_path,
                "font_exact": self._font_exact,
                "colors": self._ordered_colors(),
                "source_3mf": self._template_3mf,
                "source_step": self._template_step,
                "source_f3d": self._template_f3d,
            },
            "dimensions_mm": {
                "x": float(ext[0]),
                "y": float(ext[1]),
                "z": float(ext[2]),
            },
        }

    def _load_template(self) -> None:
        with zipfile.ZipFile(self._template_3mf, "r") as zf:
            for entry in zf.infolist():
                if entry.filename == "3D/3dmodel.model":
                    continue
                self._zip_passthrough[entry.filename] = zf.read(entry.filename)
            model_root = ET.fromstring(zf.read("3D/3dmodel.model"))

        self._title = str(
            model_root.findtext("m:metadata[@name='Title']", default="Bridge Keychain", namespaces=NS)
        ) or "Bridge Keychain"
        self._model_meta = {
            "unit": model_root.get("unit", "millimeter"),
            "lang": model_root.get(f"{{{XML_NS}}}lang", "en-US"),
        }

        resources = model_root.find("m:resources", NS)
        if resources is None:
            raise RuntimeError("Invalid 3MF: missing resources")

        build = model_root.find("m:build", NS)
        if build is None:
            raise RuntimeError("Invalid 3MF: missing build items")

        objects = {str(node.get("id")): node for node in resources.findall("m:object", NS)}
        color_groups = {
            str(node.get("id")): [str(child.get("color") or "#FFFFFFFF") for child in node]
            for node in resources.findall("mat:colorgroup", NS)
        }

        parts: list[_ColoredMesh] = []
        for item in build:
            object_id = str(item.get("objectid") or "")
            obj = objects.get(object_id)
            if obj is None:
                continue
            mesh_node = obj.find("m:mesh", NS)
            if mesh_node is None:
                continue

            vertices = np.array(
                [
                    [float(v.get("x", "0")), float(v.get("y", "0")), float(v.get("z", "0"))]
                    for v in mesh_node.find("m:vertices", NS) or []
                ],
                dtype=float,
            )
            faces = np.array(
                [
                    [int(t.get("v1", "0")), int(t.get("v2", "0")), int(t.get("v3", "0"))]
                    for t in mesh_node.find("m:triangles", NS) or []
                ],
                dtype=int,
            )
            if len(vertices) == 0 or len(faces) == 0:
                continue

            transform = self._parse_transform(item.get("transform"))
            if transform is not None:
                homog = np.concatenate([vertices, np.ones((len(vertices), 1), dtype=float)], axis=1)
                vertices = (homog @ transform.T)[:, :3]

            default_color = self._triangle_color(
                color_groups=color_groups,
                pid=str(obj.get("pid") or ""),
                pindex=str(obj.get("pindex") or "0"),
            )
            face_colors = []
            for tri in mesh_node.find("m:triangles", NS) or []:
                face_colors.append(
                    self._triangle_color(
                        color_groups=color_groups,
                        pid=str(tri.get("pid") or obj.get("pid") or ""),
                        pindex=str(tri.get("p1") or obj.get("pindex") or "0"),
                        fallback=default_color,
                    )
                )
            face_colors_arr = np.asarray(face_colors, dtype=object)

            name = str(obj.get("name") or f"Object{object_id}")
            for color in sorted(set(face_colors_arr.tolist())):
                face_idx = np.where(face_colors_arr == color)[0]
                if len(face_idx) == 0:
                    continue
                part_mesh = trimesh.Trimesh(
                    vertices=vertices.copy(),
                    faces=faces[face_idx].copy(),
                    process=False,
                )
                part_mesh.remove_unreferenced_vertices()
                parts.append(_ColoredMesh(name=name, color=color, mesh=part_mesh))

        if not parts:
            raise RuntimeError("Template 3MF does not contain any printable geometry")

        self._template_parts = parts
        self._base_object_name = "BridgeKeychain"
        self._base_color = self._detect_base_color(parts)
        self._colors = self._ordered_colors_from_parts(parts)
        self._name_color = self._detect_name_color(self._colors, self._base_color)
        self._template_bounds = self._combined_bounds([part.mesh for part in parts])
        self._body_bounds = self._detect_body_bounds(parts, self._base_color)
        self._back_surface_z = float(self._body_bounds[0][2])
        self._text_bounds = self._build_text_bounds(self._body_bounds)
        self._text_anchor_center = self._text_bounds.mean(axis=0)
        self._logo_ratio = self._detect_logo_ratio(parts, self._body_bounds, self._base_color)

    def _remap_base_to_black(self) -> None:
        """Replace the template's gray body color with black throughout."""
        _BLACK = "#1A1A1AFF"
        old = self._base_color
        if old == _BLACK:
            return
        self._template_parts = [
            _ColoredMesh(name=p.name, color=_BLACK if p.color == old else p.color, mesh=p.mesh)
            for p in self._template_parts
        ]
        self._base_color = _BLACK
        self._colors = self._ordered_colors_from_parts(self._template_parts)
        self._name_color = self._detect_name_color(self._colors, self._base_color)

    def _build_text_bounds(self, body_bounds: np.ndarray) -> np.ndarray:
        ext = body_bounds[1] - body_bounds[0]
        text_min = np.array(
            [
                float(body_bounds[0][0] + (ext[0] * _NAME_WINDOW_RATIO_MIN[0])),
                float(body_bounds[0][1] + (ext[1] * _NAME_WINDOW_RATIO_MIN[1])),
                float(body_bounds[0][2] - self._name_depth_mm),
            ],
            dtype=float,
        )
        text_max = np.array(
            [
                float(body_bounds[0][0] + (ext[0] * _NAME_WINDOW_RATIO_MAX[0])),
                float(body_bounds[0][1] + (ext[1] * _NAME_WINDOW_RATIO_MAX[1])),
                float(body_bounds[0][2]),
            ],
            dtype=float,
        )
        return np.array([text_min, text_max], dtype=float)

    def _pick_font(self) -> None:
        override_path = self._find_font_override()
        if override_path:
            self._font_path = override_path
            self._font_family = Path(override_path).stem
            self._font_exact = True
            self._font_shear = 0.0
            self._calibrate_font()
            return

        preferred_families = [
            "Franklin Gothic Demi Cond",
            "Franklin Gothic Medium Cond",
            "Gill Sans Ultra Bold Condensed",
            "Gill Sans MT Condensed",
            "Agency FB",
            "Impact",
            "Bahnschrift",
            "Arial Narrow",
            "Arial",
        ]
        family_rank = {name.lower(): idx for idx, name in enumerate(preferred_families)}
        choices: list[_FontChoice] = []

        for entry in font_manager.fontManager.ttflist:
            family = (entry.name or "").strip()
            if not family:
                continue
            family_key = family.lower()
            rank = family_rank.get(family_key, len(preferred_families))
            if rank >= len(preferred_families) and not any(token in family_key for token in ("franklin", "gill", "agency", "impact", "bahnschrift", "arial", "ocr")):
                continue
            try:
                ratio = self._render_ratio(entry.fname, "BRIDGE")
            except Exception:
                continue
            style = str(getattr(entry, "style", "") or "").lower()
            weight_raw = getattr(entry, "weight", "")
            try:
                weight_num = float(weight_raw)
            except Exception:
                weight_num = 0.0
            is_bold = ("bold" in str(weight_raw).lower()) or weight_num >= 700
            is_italic = style in {"italic", "oblique"}
            penalty = rank * 0.22
            penalty += 0.1 if not is_bold else 0.0
            penalty += 0.06 if not is_italic else 0.0
            choices.append(_FontChoice(family=family, path=entry.fname, score=abs(ratio - self._logo_ratio) + penalty))

        if not choices:
            raise RuntimeError("No usable fallback font found for the keychain template")

        preferred_choices = [item for item in choices if any(k in item.family.lower() for k in ("franklin", "gill", "agency", "impact"))]
        best = sorted((preferred_choices or choices), key=lambda item: item.score)[0]
        self._font_path = best.path
        self._font_family = best.family
        self._font_exact = False
        self._font_shear = 0.0 if any(k in best.family.lower() for k in ("franklin", "gill", "impact")) else (0.08 if "agency" in best.family.lower() else 0.12)
        self._calibrate_font()

    def _calibrate_font(self) -> None:
        font = ImageFont.truetype(self._font_path, self._font_point_size)
        bbox = ImageDraw.Draw(Image.new("L", (5000, 1800), 0)).textbbox((0, 0), "BRIDGE", font=font)
        height_px = max(1, int(bbox[3] - bbox[1]))
        target_height_mm = float(self._text_bounds[1][1] - self._text_bounds[0][1])
        self._font_mm_per_px = target_height_mm / float(height_px)

    def _build_name_mesh(self, name: str) -> trimesh.Trimesh:
        mask = self._render_text_mask(name)
        depth = float(self._name_depth_mm)
        layers = max(3, min(10, int(round(depth / 0.08))))
        volume = np.zeros((mask.shape[1] + 2, mask.shape[0] + 2, layers + 2), dtype=bool)
        volume[1:-1, 1:-1, 1 : 1 + layers] = mask.T[:, :, None]

        mesh = trimesh.voxel.ops.matrix_to_marching_cubes(
            volume,
            pitch=(self._font_mm_per_px, self._font_mm_per_px, depth / float(layers)),
        )
        mesh.apply_scale([-1.0, -1.0, 1.0])
        mesh.apply_translation(-mesh.bounds.mean(axis=0))
        mesh = self._fit_text_mesh(mesh)
        mesh.apply_translation(
            [
                float(self._text_anchor_center[0]),
                float(self._text_anchor_center[1]),
                float(self._back_surface_z + (depth * 0.5)),
            ]
        )
        mesh.remove_unreferenced_vertices()
        return mesh

    def _fit_text_mesh(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        bounds = np.asarray(mesh.bounds, dtype=float)
        ext = bounds[1] - bounds[0]
        target = self._text_bounds[1] - self._text_bounds[0]
        sx = float(target[0] * 0.90) / max(float(ext[0]), 0.001)
        sy = float(target[1] * 0.88) / max(float(ext[1]), 0.001)
        scale = min(sx, sy)
        if np.isfinite(scale) and scale > 0:
            mesh.apply_scale(scale)
            mesh.apply_translation(-mesh.bounds.mean(axis=0))
        return mesh

    def _render_text_mask(self, name: str) -> np.ndarray:
        font = ImageFont.truetype(self._font_path, self._font_point_size)
        # Always single-line — let _fit_text_mesh scale it to fill the back panel.
        return self._render_singleline_mask(name.strip(), font)

    def _render_singleline_mask(self, text: str, font) -> np.ndarray:
        scratch = Image.new("L", (6000, 2200), 0)
        draw = ImageDraw.Draw(scratch)
        bbox = draw.textbbox((0, 0), text, font=font)
        margin = 180
        width = int((bbox[2] - bbox[0]) + margin * 2)
        height = int((bbox[3] - bbox[1]) + margin * 2)
        image = Image.new("L", (max(width, 4), max(height, 4)), 0)
        draw = ImageDraw.Draw(image)
        draw.text((margin - bbox[0], margin - bbox[1]), text, fill=255, font=font)
        return self._shear_and_crop(image)

    def _render_multiline_mask(self, words: list[str], font) -> np.ndarray:
        """Render two words stacked vertically, each centred, both filling the back panel."""
        scratch = Image.new("L", (6000, 2200), 0)
        draw = ImageDraw.Draw(scratch)
        bboxes = [draw.textbbox((0, 0), w, font=font) for w in words]
        widths = [b[2] - b[0] for b in bboxes]
        heights = [b[3] - b[1] for b in bboxes]
        max_w = max(widths)
        line_gap = max(4, int(heights[0] * 0.06))
        margin = 120
        canvas_w = max_w + margin * 2
        canvas_h = sum(heights) + line_gap + margin * 2
        image = Image.new("L", (max(canvas_w, 4), max(canvas_h, 4)), 0)
        draw = ImageDraw.Draw(image)
        y = margin
        for word, bbox, h in zip(words, bboxes, heights):
            x = margin + (max_w - (bbox[2] - bbox[0])) // 2 - bbox[0]
            draw.text((x, y - bbox[1]), word, fill=255, font=font)
            y += h + line_gap
        return self._shear_and_crop(image)

    def _shear_and_crop(self, image: Image.Image) -> np.ndarray:
        if self._font_shear:
            extra = int(abs(self._font_shear) * image.height) + 4
            sheared = Image.new("L", (image.width + extra, image.height), 0)
            sheared.paste(image, (0, 0))
            coeffs = (1, -self._font_shear, extra if self._font_shear > 0 else 0, 0, 1, 0)
            image = sheared.transform(
                sheared.size,
                Image.Transform.AFFINE,
                coeffs,
                resample=Image.Resampling.BICUBIC,
            )
        arr = np.array(image, dtype=np.uint8)
        mask = arr > 32
        ys, xs = np.where(mask)
        if len(xs) == 0 or len(ys) == 0:
            raise RuntimeError("Failed to render personalization text")
        return mask[ys.min(): ys.max() + 1, xs.min(): xs.max() + 1]

    def _export_preview_parts(self, *, job_dir: str, text_mesh: trimesh.Trimesh) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        by_color: dict[str, list[trimesh.Trimesh]] = {}
        for part in self._template_parts:
            by_color.setdefault(part.color, []).append(part.mesh.copy())
        by_color.setdefault(self._name_color, []).append(text_mesh.copy())

        effective_colors = self._ordered_colors()
        if self._name_color not in effective_colors:
            effective_colors = effective_colors + [self._name_color]

        for color in effective_colors:
            meshes = by_color.get(color) or []
            if not meshes:
                continue
            merged = trimesh.util.concatenate(meshes) if len(meshes) > 1 else meshes[0]
            merged.remove_unreferenced_vertices()
            out_path = os.path.join(job_dir, f"preview_{color.strip('#').lower()}.stl")
            merged.export(out_path)
            parts.append(
                {
                    "color": color,
                    "stl_path": out_path,
                    "color_index": effective_colors.index(color),
                }
            )
        return parts

    def _write_personalized_3mf(self, *, out_path: str, text_mesh: trimesh.Trimesh, title: str) -> None:
        palette = self._ordered_colors()
        # Custom name colour (e.g. from AMS tray) may not be in the template palette — add it.
        if self._name_color not in palette:
            palette = palette + [self._name_color]
        color_to_index = {color: idx for idx, color in enumerate(palette)}

        merged_vertices: list[np.ndarray] = []
        merged_faces: list[np.ndarray] = []
        merged_face_colors: list[np.ndarray] = []
        vertex_offset = 0

        for part in self._template_parts:
            verts = np.asarray(part.mesh.vertices, dtype=float)
            faces = np.asarray(part.mesh.faces, dtype=int)
            if len(verts) == 0 or len(faces) == 0:
                continue
            merged_vertices.append(verts)
            merged_faces.append(faces + vertex_offset)
            merged_face_colors.append(np.full(len(faces), color_to_index[part.color], dtype=int))
            vertex_offset += len(verts)

        verts = np.asarray(text_mesh.vertices, dtype=float)
        faces = np.asarray(text_mesh.faces, dtype=int)
        merged_vertices.append(verts)
        merged_faces.append(faces + vertex_offset)
        merged_face_colors.append(np.full(len(faces), color_to_index[self._name_color], dtype=int))

        model = ET.Element(
            f"{{{CORE_NS}}}model",
            {
                "unit": str(self._model_meta.get("unit", "millimeter")),
                f"{{{XML_NS}}}lang": str(self._model_meta.get("lang", "en-US")),
            },
        )
        ET.SubElement(
            model,
            f"{{{CORE_NS}}}metadata",
            {
                "name": "Title",
                "type": "QName",
                "preserve": "1",
            },
        ).text = title

        resources = ET.SubElement(model, f"{{{CORE_NS}}}resources")
        colorgroup = ET.SubElement(resources, f"{{{MAT_NS}}}colorgroup", {"id": "2"})
        for color in palette:
            ET.SubElement(colorgroup, f"{{{MAT_NS}}}color", {"color": color})

        model_object = ET.SubElement(
            resources,
            f"{{{CORE_NS}}}object",
            {
                "id": "1",
                "name": self._base_object_name,
                "type": "model",
                f"{{{PROD_NS}}}UUID": self._base_object_uuid,
                "pid": "2",
                "pindex": str(color_to_index[self._base_color]),
            },
        )
        self._append_mesh(
            parent=model_object,
            vertices=np.vstack(merged_vertices),
            faces=np.vstack(merged_faces),
            face_color_index=np.concatenate(merged_face_colors),
            default_color_index=color_to_index[self._base_color],
        )

        build = ET.SubElement(model, f"{{{CORE_NS}}}build")
        ET.SubElement(build, f"{{{CORE_NS}}}item", {"objectid": "1", f"{{{PROD_NS}}}UUID": str(uuid.uuid4())})

        xml_bytes = ET.tostring(model, encoding="utf-8", xml_declaration=True)
        with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("3D/3dmodel.model", xml_bytes)
            for filename, data in self._zip_passthrough.items():
                zf.writestr(filename, data)

    @staticmethod
    def _append_mesh(
        *,
        parent: ET.Element,
        vertices: np.ndarray,
        faces: np.ndarray,
        face_color_index: np.ndarray,
        default_color_index: int,
    ) -> None:
        mesh = ET.SubElement(parent, f"{{{CORE_NS}}}mesh")
        vertices_el = ET.SubElement(mesh, f"{{{CORE_NS}}}vertices")
        for vx, vy, vz in np.asarray(vertices, dtype=float):
            ET.SubElement(
                vertices_el,
                f"{{{CORE_NS}}}vertex",
                {
                    "x": KeychainService._fmt(vx),
                    "y": KeychainService._fmt(vy),
                    "z": KeychainService._fmt(vz),
                },
            )
        triangles_el = ET.SubElement(mesh, f"{{{CORE_NS}}}triangles")
        for idx, (v1, v2, v3) in enumerate(np.asarray(faces, dtype=int)):
            attrs = {"v1": str(int(v1)), "v2": str(int(v2)), "v3": str(int(v3))}
            color_index = int(face_color_index[idx])
            if color_index != int(default_color_index):
                attrs["pid"] = "2"
                attrs["p1"] = str(color_index)
            ET.SubElement(triangles_el, f"{{{CORE_NS}}}triangle", attrs)

    def _triangle_color(
        self,
        *,
        color_groups: dict[str, list[str]],
        pid: str,
        pindex: str,
        fallback: str = "#FFFFFFFF",
    ) -> str:
        colors = color_groups.get(str(pid or ""))
        if not colors:
            return fallback
        try:
            idx = int(pindex or "0")
        except Exception:
            idx = 0
        if idx < 0 or idx >= len(colors):
            return fallback
        return str(colors[idx])

    def _ordered_colors(self) -> list[str]:
        if self._colors:
            return list(self._colors)
        return self._ordered_colors_from_parts(self._template_parts)

    def _ordered_colors_from_parts(self, parts: list[_ColoredMesh]) -> list[str]:
        seen: list[str] = []
        for part in parts:
            if part.color not in seen:
                seen.append(part.color)
        if self._base_color and self._base_color in seen:
            seen = [self._base_color] + [color for color in seen if color != self._base_color]
        accents = [color for color in seen if color != self._base_color]
        accents.sort(key=self._color_sort_key)
        ordered = ([self._base_color] if self._base_color and self._base_color in seen else []) + accents
        return ordered or seen

    def _color_sort_key(self, color: str) -> tuple[int, float]:
        r, g, b = self._hex_rgb(color)
        saturation = max(r, g, b) - min(r, g, b)
        luminance = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
        orange_like = 1 if (r > 200 and g > 70 and g < 140 and b < 80 and saturation > 90) else 0
        return (-orange_like, -luminance)

    def _detect_base_color(self, parts: list[_ColoredMesh]) -> str:
        best_color = parts[0].color
        best_score = float("-inf")
        for part in parts:
            bounds = np.asarray(part.mesh.bounds, dtype=float)
            ext = bounds[1] - bounds[0]
            score = float(ext[0] * ext[1] * max(ext[2], 0.1))
            if ext[2] >= 2.0:
                score += 100000.0
            if score > best_score:
                best_color = part.color
                best_score = score
        return best_color

    def _detect_name_color(self, colors: list[str], base_color: str) -> str:
        for color in colors:
            if color != base_color:
                return color
        return base_color

    def _detect_body_bounds(self, parts: list[_ColoredMesh], base_color: str) -> np.ndarray:
        candidates = [part for part in parts if part.color == base_color]
        if not candidates:
            candidates = list(parts)
        best_bounds = np.asarray(candidates[0].mesh.bounds, dtype=float)
        best_score = float("-inf")
        for part in candidates:
            bounds = np.asarray(part.mesh.bounds, dtype=float)
            ext = bounds[1] - bounds[0]
            score = float(ext[0] * ext[1] * max(ext[2], 0.1))
            if ext[2] >= 2.0:
                score += 100000.0
            if score > best_score:
                best_bounds = bounds
                best_score = score
        return best_bounds

    def _detect_logo_ratio(self, parts: list[_ColoredMesh], body_bounds: np.ndarray, base_color: str) -> float:
        by_color: dict[str, list[trimesh.Trimesh]] = {}
        for part in parts:
            if part.color == base_color:
                continue
            if float(part.mesh.bounds[0][2]) < float(body_bounds[1][2]) - 0.05:
                continue
            by_color.setdefault(part.color, []).append(part.mesh)

        if not by_color:
            for part in parts:
                if part.color != base_color:
                    by_color.setdefault(part.color, []).append(part.mesh)

        if not by_color:
            return 5.7
        best_meshes = max(
            by_color.values(),
            key=lambda meshes: sum(int(len(mesh.faces)) for mesh in meshes),
        )
        bounds = self._combined_bounds(best_meshes)
        ext = bounds[1] - bounds[0]
        return float(ext[0]) / max(float(ext[1]), 0.1)

    def _combined_bounds(self, meshes: list[trimesh.Trimesh]) -> np.ndarray:
        mins = np.vstack([np.asarray(mesh.bounds[0], dtype=float) for mesh in meshes])
        maxs = np.vstack([np.asarray(mesh.bounds[1], dtype=float) for mesh in meshes])
        return np.array([mins.min(axis=0), maxs.max(axis=0)], dtype=float)

    def _render_ratio(self, font_path: str, text: str) -> float:
        image = Image.new("L", (4000, 1600), 0)
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype(font_path, 400)
        bbox = draw.textbbox((0, 0), text, font=font)
        width = max(1, int(bbox[2] - bbox[0]))
        height = max(1, int(bbox[3] - bbox[1]))
        return width / float(height)

    def _validate_name(self, raw_name: str) -> str:
        name = str(raw_name or "").strip()
        if not _NAME_RE.fullmatch(name):
            raise RuntimeError("Name must be 1-2 words, up to 7 characters each (e.g. 'Aisha' or 'Ahmed Ali').")
        return name

    def _find_font_override(self) -> str | None:
        for basename in _FONT_OVERRIDE_BASENAMES:
            path = os.path.join(self.template_dir, basename)
            if os.path.exists(path):
                return path
        for entry in os.listdir(self.template_dir):
            if entry.lower().endswith((".ttf", ".otf")):
                return os.path.join(self.template_dir, entry)
        return None

    def _resolve_required_path(self, *candidates: str) -> str:
        for filename in candidates:
            path = os.path.join(self.template_dir, filename)
            if os.path.exists(path):
                return path
        raise RuntimeError(f"Missing keychain template file in {self.template_dir}: tried {', '.join(candidates)}")

    def _resolve_optional_path(self, *candidates: str) -> str | None:
        for filename in candidates:
            path = os.path.join(self.template_dir, filename)
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def _parse_transform(raw: str | None) -> np.ndarray | None:
        if not raw:
            return None
        try:
            values = [float(part) for part in str(raw).strip().split()]
        except Exception:
            return None
        if len(values) != 12:
            return None
        return np.array(
            [
                [values[0], values[1], values[2], values[3]],
                [values[4], values[5], values[6], values[7]],
                [values[8], values[9], values[10], values[11]],
                [0.0, 0.0, 0.0, 1.0],
            ],
            dtype=float,
        )

    @staticmethod
    def _hex_rgb(color: str) -> tuple[int, int, int]:
        raw = str(color or "").strip().lstrip("#")
        if len(raw) == 8:
            raw = raw[:6]
        if len(raw) != 6:
            return (255, 255, 255)
        try:
            return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
        except Exception:
            return (255, 255, 255)

    @staticmethod
    def _fmt(value: float) -> str:
        return f"{float(value):.6f}"
