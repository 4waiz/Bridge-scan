# backend/shap_e_service.py
# Image -> 3D : Hunyuan3D-2 (primary) + Shap-E image300M (fallback)
# Text  -> 3D : Hunyuan text2image -> Hunyuan3D-2 (primary) + Shap-E text300M (fallback)
import os
import sys
import time
import uuid
import importlib
import types
import threading
import warnings
import torch
import trimesh
from PIL import Image

TEXT2IMAGE_AVAILABLE = False
AutoPipelineForText2Image = None
try:
    from diffusers import AutoPipelineForText2Image as _AutoT2I
    AutoPipelineForText2Image = _AutoT2I
    TEXT2IMAGE_AVAILABLE = True
except Exception as _t2i_err:
    print(f"[ShapeService] Text-to-image pipeline unavailable ({_t2i_err})")

# ── Inject Hunyuan3D-2 source root into sys.path ───────────────────────────
_THIS_DIR    = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT    = os.path.abspath(os.path.join(_THIS_DIR, ".."))
HUNYUAN_ROOT = os.path.abspath(
    os.path.join(_APP_ROOT, "..", "hunyuan", "Hunyuan3D-2")
)
if os.path.isdir(HUNYUAN_ROOT) and HUNYUAN_ROOT not in sys.path:
    sys.path.insert(0, HUNYUAN_ROOT)
    print(f"[ShapeService] Hunyuan3D-2 root added: {HUNYUAN_ROOT}")

# ── Try importing Hunyuan3D-2 ──────────────────────────────────────────────
HUNYUAN_AVAILABLE            = False
HUNYUAN_IMPORT_ERROR         = None
HUNYUAN_PIPELINE_NAME        = ""
HunyuanPipelineClass         = None
HunyuanFloaterRemover        = None
HunyuanFaceReducer           = None
HunyuanDegenerateFaceRemover = None

try:
    # Support both older and current Hunyuan class names.
    _PIPELINE_CANDIDATES = [
        ("hy3dgen.shapegen", "Hunyuan3DPipeline"),
        ("hy3dgen.shapegen", "Hunyuan3DDiTFlowMatchingPipeline"),
        ("hy3dgen.shapegen", "Hunyuan3DDiTPipeline"),
    ]
    _last_import_err = None
    for _module_name, _class_name in _PIPELINE_CANDIDATES:
        try:
            _mod = importlib.import_module(_module_name)
            _cls = getattr(_mod, _class_name)
            HunyuanPipelineClass = _cls
            HUNYUAN_PIPELINE_NAME = f"{_module_name}.{_class_name}"
            break
        except Exception as _e:
            _last_import_err = _e
            continue
    if HunyuanPipelineClass is None:
        raise RuntimeError(_last_import_err or "No compatible Hunyuan pipeline class found")

    try:
        from hy3dgen.shapegen import (
            FloaterRemover        as _FR,
            FaceReducer           as _FCR,
            DegenerateFaceRemover as _DFR,
        )
        HunyuanFloaterRemover        = _FR
        HunyuanFaceReducer           = _FCR
        HunyuanDegenerateFaceRemover = _DFR
    except ImportError:
        pass  # post-processors are optional extras

    HUNYUAN_AVAILABLE = True
    print(f"[ShapeService] Hunyuan3D-2 found ({HUNYUAN_PIPELINE_NAME})")
except Exception as _he:
    HUNYUAN_IMPORT_ERROR = _he
    print(f"[ShapeService] Hunyuan3D-2 not available ({_he}) - will use Shap-E image fallback")
REMBG_AVAILABLE = False
try:
    from rembg import remove as _rembg_fn
    REMBG_AVAILABLE = True
    print("[ShapeService] rembg background removal ready")
except ImportError:
    print("[ShapeService] rembg missing - run: pip install rembg[gpu]")

# ── Silence Shap-E deprecation warnings ───────────────────────────────────
warnings.filterwarnings("ignore", category=FutureWarning,
                        message=r".*torch\.cuda\.amp\.custom_fwd.*")
warnings.filterwarnings("ignore", category=FutureWarning,
                        message=r".*torch\.cuda\.amp\.custom_bwd.*")

from shap_e.diffusion.sample            import sample_latents
from shap_e.diffusion.gaussian_diffusion import diffusion_from_config
from shap_e.models.download             import load_model, load_config as shap_e_load_config
from shap_e.util.notebooks              import decode_latent_mesh

from mesh_clean import clean_and_decimate

# ── Hunyuan3D-2 quality presets ────────────────────────────────────────────
_H3D_PRESETS: dict[str, dict] = {
    "fast":     {"num_inference_steps": 16, "guidance_scale": 5.0, "octree_resolution": 256},
    "balanced": {"num_inference_steps": 24, "guidance_scale": 6.0, "octree_resolution": 256},
    "quality":  {"num_inference_steps": 36, "guidance_scale": 7.0, "octree_resolution": 288},
}

# Hunyuan3D-2 expects repo IDs here (or local IDs via HY3DGEN_MODELS cache path).
_H3D_MODEL_ID = (os.environ.get("HUNYUAN_MODEL_ID") or "tencent/Hunyuan3D-2").strip()
_H3D_MODEL_SOURCES = []
for _src in (_H3D_MODEL_ID, "tencent/Hunyuan3D-2"):
    if _src and _src not in _H3D_MODEL_SOURCES:
        _H3D_MODEL_SOURCES.append(_src)

_HUNYUAN_TEXT2IMAGE_ENABLED = str(
    os.environ.get("HUNYUAN_TEXT2IMAGE_ENABLED", "1")
).strip().lower() not in ("0", "false", "no")
_HUNYUAN_TEXT2IMAGE_MODEL_ID = (
    os.environ.get("HUNYUAN_TEXT2IMAGE_MODEL_ID")
    or "Tencent-Hunyuan/HunyuanDiT-v1.1-Diffusers-Distilled"
).strip()
_HUNYUAN_TEXT2IMAGE_PRESETS: dict[str, dict] = {
    "fast": {"steps": 10, "width": 1024, "height": 1024, "guidance_scale": 4.0},
    "balanced": {"steps": 12, "width": 1024, "height": 1024, "guidance_scale": 4.5},
    "quality": {"steps": 16, "width": 1024, "height": 1024, "guidance_scale": 5.0},
}


# ══════════════════════════════════════════════════════════════════════════════

class GenerationCancelledError(RuntimeError):
    pass


class ShapeService:
    """
    3D generation service.
      Text  → 3D  :  Shap-E text300M  (fast, no extra download required)
      Image → 3D  :  Hunyuan3D-2      (primary, huge quality jump)
                     Shap-E image300M  (automatic fallback)
    """

    # Shap-E text-to-3D presets (unchanged from v1)
    GENERATION_PRESETS = {
        "fast":     {"guidance_scale": 14.0, "karras_steps": 48,  "sigma_max": 140.0},
        "balanced": {"guidance_scale": 18.0, "karras_steps": 80,  "sigma_max": 180.0},
        "quality":  {"guidance_scale": 20.0, "karras_steps": 128, "sigma_max": 200.0},
    }

    # Shap-E image-to-3D presets (fallback only)
    IMAGE_GENERATION_PRESETS = {
        "fast":     {"guidance_scale": 3.0, "karras_steps": 44, "sigma_max": 120.0},
        "balanced": {"guidance_scale": 4.0, "karras_steps": 64, "sigma_max": 140.0},
        "quality":  {"guidance_scale": 5.0, "karras_steps": 88, "sigma_max": 160.0},
    }

    def __init__(self, runs_dir: str):
        self.runs_dir = runs_dir
        os.makedirs(self.runs_dir, exist_ok=True)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if self.device.type == "cuda":
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            torch.backends.cudnn.benchmark = True
        print(f"[ShapeService] Device: {self.device}")

        # Shap-E models are fallback-only in the revamp app, so keep them lazy.
        self.text_model = None
        self.diffusion = None
        self.transmitter = None
        self.image_model = None
        self._shap_e_lock = threading.Lock()

        # Hunyuan3D-2 pipeline — lazy-loaded on first image-to-3D call
        self._hunyuan: object  = None
        self._hunyuan_failed   = False
        self._hunyuan_lock     = threading.Lock()
        self._hunyuan_last_error = str(HUNYUAN_IMPORT_ERROR) if HUNYUAN_IMPORT_ERROR else ""

        # Optional text->image model for Hunyuan-first text generation.
        self._text2img = None
        self._text2img_failed = False
        self._text2img_lock = threading.Lock()
        self._text2img_last_error = ""
        self._text2img_execution_mode = "unknown"

        # Progress tracking for frontend polling.
        self._progress_lock = threading.Lock()
        self._progress_state: dict[str, dict] = {}
        self._hunyuan_tqdm_patch_lock = threading.Lock()

        # GPU capability hints for safer preset behavior on 8GB-class cards.
        self._gpu_vram_gb = 0.0
        if self.device.type == "cuda":
            try:
                self._gpu_vram_gb = (
                    float(torch.cuda.get_device_properties(self.device).total_memory) / (1024.0 ** 3)
                )
            except Exception:
                self._gpu_vram_gb = 0.0
        self._low_vram_mode = self.device.type == "cuda" and self._gpu_vram_gb > 0 and self._gpu_vram_gb <= 8.5
        self._strict_gpu_mode = str(os.environ.get("STRICT_GPU_MODE", "1")).strip().lower() not in ("0", "false", "no")
        self._disable_quality_fallback = str(os.environ.get("DISABLE_QUALITY_FALLBACK", "1")).strip().lower() not in ("0", "false", "no")
        print(
            f"[ShapeService] strict_gpu_mode={self._strict_gpu_mode} "
            f"disable_quality_fallback={self._disable_quality_fallback} "
            f"vram_gb={round(self._gpu_vram_gb, 2)}"
        )

    # ══ Device helpers ════════════════════════════════════════════════════════

    def _module_device(self, module) -> torch.device:
        try:
            return next(module.parameters()).device
        except Exception:
            return torch.device("cpu")

    def _move_model_to_device(self, model, target: torch.device) -> None:
        """Deep move — walks all submodules and buffers (needed for CLIP internals)."""
        model.to(target)
        for _, sub in model.named_modules():
            try:
                sub.to(target)
            except Exception:
                pass
        module_map = dict(model.named_modules())
        for buf_name, buf in model.named_buffers():
            if buf is not None and buf.device != target:
                parts = buf_name.rsplit(".", 1)
                try:
                    parent = module_map[parts[0]] if len(parts) == 2 else model
                    parent.register_buffer(parts[-1], buf.to(target))
                except Exception:
                    pass
        torch.cuda.empty_cache()

    def _shap_e_to_cpu(self):
        """Move all Shap-E weights to CPU to free VRAM for Hunyuan3D-2."""
        if self.device.type != "cuda":
            return
        models = [m for m in (self.text_model, self.transmitter) if m is not None]
        if self.image_model is not None:
            models.append(self.image_model)
        for m in models:
            try:
                if self._module_device(m).type == "cuda":
                    self._move_model_to_device(m, torch.device("cpu"))
            except Exception:
                pass
        torch.cuda.empty_cache()

    def _shap_e_to_gpu(self):
        """Restore Shap-E text + transmitter to GPU."""
        if self.device.type != "cuda":
            return
        for m in [self.text_model, self.transmitter]:
            if m is None:
                continue
            if self._module_device(m).type != "cuda":
                self._move_model_to_device(m, self.device)

    def _pipeline_device(self, pipe) -> torch.device:
        if pipe is None:
            return torch.device("cpu")
        for name in ("transformer", "unet", "vae", "text_encoder", "text_encoder_2"):
            mod = getattr(pipe, name, None)
            if mod is not None:
                d = self._module_device(mod)
                if d is not None:
                    return d
        comps = getattr(pipe, "components", None)
        if isinstance(comps, dict):
            for mod in comps.values():
                if hasattr(mod, "parameters"):
                    d = self._module_device(mod)
                    if d is not None:
                        return d
        return torch.device("cpu")

    def _text2img_to_cpu(self):
        """
        Offload text2image weights to CPU RAM when idle.
        Keeps the pipeline object alive so _get_text2image() can move it back
        to GPU without a full disk reload (CPU<->GPU ~30s vs disk reload ~3-5min).
        """
        with self._text2img_lock:
            pipe = self._text2img
            if pipe is None:
                return
            try:
                if self.device.type == "cuda" and hasattr(pipe, "to"):
                    pipe.to("cpu")
                    torch.cuda.empty_cache()
                    self._text2img_execution_mode = "cpu"
            except Exception as e:
                # CPU move failed — fall back to hard evict rather than leaving
                # weights on GPU and risking OOM for the Hunyuan3D stage.
                print(f"[ShapeService] text2image CPU offload failed ({e}), evicting")
                self._text2img = None
                del pipe
                torch.cuda.empty_cache()
                self._text2img_execution_mode = "evicted"

    def _hunyuan_evict(self):
        """Free Hunyuan3D pipeline VRAM so text2image can run at full speed on 8GB GPUs."""
        if self.device.type != "cuda":
            return
        with self._hunyuan_lock:
            pipe = self._hunyuan
            if pipe is None:
                return
            try:
                self._hunyuan = None
                del pipe
                torch.cuda.empty_cache()
                self._hunyuan_last_error = ""
                print("[ShapeService] Hunyuan3D-2 evicted from VRAM for text2image stage")
            except Exception:
                pass

    # ══ Hunyuan3D-2 helpers ═══════════════════════════════════════════════════

    def _get_hunyuan(self, request_id: str | None = None):
        """Lazy-load Hunyuan3D-2 pipeline once; cache it for subsequent calls."""
        self._raise_if_cancelled(request_id)
        self._enforce_strict_gpu("Hunyuan3D-2")
        if not HUNYUAN_AVAILABLE:
            if not self._hunyuan_last_error and HUNYUAN_IMPORT_ERROR:
                self._hunyuan_last_error = str(HUNYUAN_IMPORT_ERROR)
            return None
        if self._hunyuan_failed:
            return None
        with self._hunyuan_lock:
            if self._hunyuan is not None:
                return self._hunyuan
            # Free Shap-E VRAM before loading the bigger model
            self._shap_e_to_cpu()
            self._progress_update(
                request_id,
                stage_key="model_loading",
                stage_label="Loading Weights",
                message="Loading Hunyuan3D-2 into memory...",
                progress=0.0,
                current=0,
                total=1,
            )
            last_err = None
            for src in _H3D_MODEL_SOURCES:
                try:
                    self._raise_if_cancelled(request_id)
                    print(f"[ShapeService] Loading Hunyuan3D-2 from '{src}'...")
                    load_kwargs = {
                        "device": str(self.device),
                        "dtype": torch.float16 if self.device.type == "cuda" else torch.float32,
                    }
                    try:
                        pipe = HunyuanPipelineClass.from_pretrained(src, **load_kwargs)
                    except TypeError:
                        # Older wrappers often accept torch_dtype instead of dtype/device.
                        legacy_kwargs = {
                            "torch_dtype": torch.float16 if self.device.type == "cuda" else torch.float32,
                        }
                        pipe = HunyuanPipelineClass.from_pretrained(src, **legacy_kwargs)
                    if hasattr(pipe, "to"):
                        pipe.to(self.device)
                    self._hunyuan = pipe
                    self._hunyuan_last_error = ""
                    print(f"[ShapeService] Hunyuan3D-2 ready on {self.device}")
                    self._progress_update(
                        request_id,
                        stage_key="model_loading",
                        stage_label="Loading Weights",
                        message="Hunyuan3D-2 loaded.",
                        progress=1.0,
                        current=1,
                        total=1,
                    )
                    return self._hunyuan
                except Exception as e:
                    last_err = e
                    print(f"[ShapeService]   tried '{src}': {e}")
            self._hunyuan_last_error = str(last_err) if last_err else "Unknown Hunyuan load error"
            print(f"[ShapeService] All Hunyuan3D-2 sources failed: {last_err}")
            self._hunyuan_failed = True
            return None

    def _remove_background(self, image: Image.Image) -> Image.Image:
        """Strip background with rembg; returns RGBA. Falls back silently."""
        if not REMBG_AVAILABLE:
            return image
        try:
            return _rembg_fn(image.convert("RGBA"))
        except Exception as e:
            print(f"[ShapeService] rembg error (continuing): {e}")
            return image

    def _prepare_for_hunyuan(self, image: Image.Image) -> Image.Image:
        """Remove bg → composite on white → square-crop → 512×512 RGB."""
        rgba = self._remove_background(image)
        if rgba.mode == "RGBA":
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[3])
            out = bg.convert("RGB")
        else:
            out = rgba.convert("RGB")
        w, h  = out.size
        side  = min(w, h)
        left  = (w - side) // 2
        top   = (h - side) // 2
        out   = out.crop((left, top, left + side, top + side))
        rs    = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        return out.resize((512, 512), rs)

    def _extract_mesh(self, result) -> "trimesh.Trimesh | None":
        """Normalise whatever Hunyuan3D-2 returns into a trimesh.Trimesh."""
        # Direct trimesh
        if isinstance(result, trimesh.Trimesh):
            return result
        # List / tuple
        if isinstance(result, (list, tuple)) and result:
            for item in result:
                mesh = self._extract_mesh(item)
                if isinstance(mesh, trimesh.Trimesh):
                    return mesh
        # Object with .mesh or .meshes attribute
        for attr in ("mesh", "meshes"):
            if hasattr(result, attr):
                m = getattr(result, attr)
                if isinstance(m, (list, tuple)):
                    for item in m:
                        mesh = self._extract_mesh(item)
                        if isinstance(mesh, trimesh.Trimesh):
                            return mesh
                elif isinstance(m, trimesh.Trimesh):
                    return m
        return None

    def _hunyuan_postprocess(self, mesh: trimesh.Trimesh) -> trimesh.Trimesh:
        """Apply Hunyuan post-processors when available, then standard clean."""
        for cls in [HunyuanFloaterRemover, HunyuanDegenerateFaceRemover]:
            if cls is not None:
                try:
                    mesh = cls()(mesh)
                except Exception:
                    pass
        if HunyuanFaceReducer is not None:
            try:
                mesh = HunyuanFaceReducer()(mesh, max_facenum=80_000)
            except Exception:
                pass
        return clean_and_decimate(mesh)

    def _get_text2image(self, request_id: str | None = None):
        """Lazy-load text->image model used for Hunyuan-first text generation."""
        self._raise_if_cancelled(request_id)
        self._enforce_strict_gpu("Hunyuan text-to-image")
        if self._low_vram_mode:
            # Avoid VRAM contention between Hunyuan3D and text2image on 8GB cards.
            self._hunyuan_evict()
        if not _HUNYUAN_TEXT2IMAGE_ENABLED:
            self._text2img_last_error = "HUNYUAN_TEXT2IMAGE_ENABLED=0"
            return None
        if not TEXT2IMAGE_AVAILABLE:
            self._text2img_last_error = "diffusers AutoPipelineForText2Image is unavailable"
            return None
        if self._text2img_failed:
            return None
        with self._text2img_lock:
            if self._text2img is not None:
                if self.device.type == "cuda" and self._pipeline_device(self._text2img).type != "cuda":
                    self._raise_if_cancelled(request_id)
                    self._progress_update(
                        request_id,
                        stage_key="model_loading",
                        stage_label="Loading Weights",
                        message="Moving text model to CUDA...",
                        progress=0.0,
                        current=0,
                        total=1,
                    )
                    try:
                        if hasattr(self._text2img, "to"):
                            self._text2img.to(self.device)
                            self._text2img_execution_mode = "cuda"
                        else:
                            raise RuntimeError("text2image pipeline has no .to(device) method")
                    except Exception as e:
                        if self._strict_gpu_mode:
                            raise RuntimeError(
                                "Strict GPU mode: text2image could not move to CUDA. "
                                f"Original error: {e}"
                            ) from e
                        self._text2img_execution_mode = "cpu"
                    self._progress_update(
                        request_id,
                        stage_key="model_loading",
                        stage_label="Loading Weights",
                        message="Text model ready on CUDA.",
                        progress=1.0,
                        current=1,
                        total=1,
                    )
                return self._text2img
            self._shap_e_to_cpu()
            try:
                dtype = torch.float16 if self.device.type == "cuda" else torch.float32
                self._raise_if_cancelled(request_id)
                self._progress_update(
                    request_id,
                    stage_key="model_loading",
                    stage_label="Loading Pipeline Components",
                    message="Loading Hunyuan text-to-image model...",
                    progress=0.0,
                    current=0,
                    total=1,
                )
                print(f"[ShapeService] Loading Hunyuan text2image model '{_HUNYUAN_TEXT2IMAGE_MODEL_ID}'...")
                pipe = AutoPipelineForText2Image.from_pretrained(
                    _HUNYUAN_TEXT2IMAGE_MODEL_ID,
                    torch_dtype=dtype,
                )
                if hasattr(pipe, "set_progress_bar_config"):
                    pipe.set_progress_bar_config(disable=True)
                if self.device.type == "cuda":
                    moved = False
                    if hasattr(pipe, "to"):
                        try:
                            pipe.to(self.device)
                            moved = True
                        except Exception:
                            moved = False
                    if not moved:
                        if self._strict_gpu_mode:
                            raise RuntimeError(
                                "Strict GPU mode: text2image could not stay on CUDA. "
                                "CPU offload is disabled."
                            )
                        if hasattr(pipe, "enable_model_cpu_offload"):
                            pipe.enable_model_cpu_offload()
                            self._text2img_execution_mode = "cpu_offload"
                        else:
                            self._text2img_execution_mode = "cpu"
                    else:
                        self._text2img_execution_mode = "cuda"
                elif hasattr(pipe, "to"):
                    pipe.to(self.device)
                    self._text2img_execution_mode = "cpu"
                self._text2img = pipe
                self._text2img_last_error = ""
                print(f"[ShapeService] Hunyuan text2image ready ({self._text2img_execution_mode})")
                self._progress_update(
                    request_id,
                    stage_key="model_loading",
                    stage_label="Loading Pipeline Components",
                    message="Hunyuan text-to-image model loaded.",
                    progress=1.0,
                    current=1,
                    total=1,
                )
                return self._text2img
            except Exception as e:
                self._text2img_failed = True
                self._text2img_last_error = str(e)
                print(f"[ShapeService] Failed to load text2image model: {e}")
                return None

    def _prompt_to_reference_image(
        self,
        prompt: str,
        quality_preset: str,
        request_id: str | None = None,
    ) -> tuple[Image.Image, dict]:
        """Generate a single-object reference image from text."""
        self._raise_if_cancelled(request_id)
        pipe = self._get_text2image(request_id=request_id)
        if pipe is None:
            raise RuntimeError(self._text2img_last_error or "text2image unavailable")

        pk = (quality_preset or "balanced").strip().lower()
        cfg = self._effective_text2image_preset(pk)
        final_prompt = (
            f"{prompt.strip()}, single 3D-printable object, centered product render, "
            "plain white background, studio lighting, no text, no watermark"
        )
        negative_prompt = (
            "multiple objects, human, hands, cluttered background, text, watermark, logo, "
            "cropped, blurry, low quality"
        )

        seed = int(time.time() * 1000) % (2**31 - 1)
        generator = None
        if self.device.type == "cuda":
            generator = torch.Generator(device=self.device).manual_seed(seed)

        self._progress_update(
            request_id,
            stage_key="text2image",
            stage_label="Diffusion Sampling",
            progress=0.0,
            current=0,
            total=int(cfg["steps"]),
            message="Sampling reference image from text",
        )

        call_kwargs = dict(
            prompt=final_prompt,
            negative_prompt=negative_prompt,
            width=int(cfg["width"]),
            height=int(cfg["height"]),
            num_inference_steps=int(cfg["steps"]),
            guidance_scale=float(cfg["guidance_scale"]),
            generator=generator,
        )
        has_live_step_callback = False
        if request_id:
            def _t2i_cb(_pipe, step, _timestep, cb_kwargs):
                self._raise_if_cancelled(request_id)
                total_steps = int(cfg["steps"])
                pct = float(step + 1) / float(max(total_steps, 1))
                self._progress_update(
                    request_id,
                    stage_key="text2image",
                    stage_label="Diffusion Sampling",
                    progress=pct,
                    current=int(step + 1),
                    total=total_steps,
                    message="Sampling reference image from text",
                )
                return cb_kwargs

            call_kwargs["callback_on_step_end"] = _t2i_cb
            call_kwargs["callback_on_step_end_tensor_inputs"] = []

        try:
            self._raise_if_cancelled(request_id)
            out = pipe(**call_kwargs)
            has_live_step_callback = bool(request_id)
        except TypeError:
            # Some pipelines support legacy callback/callback_steps instead.
            legacy_kwargs = dict(call_kwargs)
            legacy_kwargs.pop("callback_on_step_end", None)
            legacy_kwargs.pop("callback_on_step_end_tensor_inputs", None)
            if request_id:
                def _legacy_cb(step, _timestep, _latents):
                    self._raise_if_cancelled(request_id)
                    total_steps = int(cfg["steps"])
                    pct = float(step + 1) / float(max(total_steps, 1))
                    self._progress_update(
                        request_id,
                        stage_key="text2image",
                        stage_label="Diffusion Sampling",
                        progress=pct,
                        current=int(step + 1),
                        total=total_steps,
                        message="Sampling reference image from text",
                    )
                legacy_kwargs["callback"] = _legacy_cb
                legacy_kwargs["callback_steps"] = 1
            try:
                self._raise_if_cancelled(request_id)
                out = pipe(**legacy_kwargs)
                has_live_step_callback = bool(request_id)
            except TypeError:
                # Last fallback: no callback API; still execute and update once at end.
                legacy_kwargs.pop("callback", None)
                legacy_kwargs.pop("callback_steps", None)
                self._raise_if_cancelled(request_id)
                out = pipe(**legacy_kwargs)
                has_live_step_callback = False

        self._raise_if_cancelled(request_id)
        images = getattr(out, "images", None)
        if not images:
            raise RuntimeError("text2image returned no images")
        if request_id and not has_live_step_callback:
            self._progress_update(
                request_id,
                stage_key="text2image",
                stage_label="Diffusion Sampling",
                progress=0.95,
                current=max(int(cfg["steps"]) - 1, 0),
                total=int(cfg["steps"]),
                message="Finalizing reference image",
            )
        self._progress_update(
            request_id,
            stage_key="text2image",
            stage_label="Diffusion Sampling",
            progress=1.0,
            current=int(cfg["steps"]),
            total=int(cfg["steps"]),
            message="Reference image ready",
        )
        img = images[0].convert("RGB")
        meta = {
            "model_id": _HUNYUAN_TEXT2IMAGE_MODEL_ID,
            "seed": seed,
            "steps": int(cfg["steps"]),
            "width": int(cfg["width"]),
            "height": int(cfg["height"]),
            "guidance_scale": float(cfg["guidance_scale"]),
        }
        return img, meta

    # ══ Shap-E CLIP patch (for image300M fallback) ════════════════════════════

    def _patch_cached_model_kwargs(self, model) -> None:
        device = self.device
        orig   = model.cached_model_kwargs

        def patched(batch_size, model_kwargs):
            result = orig(batch_size, model_kwargs)
            return {k: v.to(device) if isinstance(v, torch.Tensor) else v
                    for k, v in result.items()}

        model.cached_model_kwargs = types.MethodType(
            lambda self_m, b, mk: patched(b, mk), model
        )

    def _shap_e_storage_device(self) -> torch.device:
        return torch.device("cpu") if self.device.type == "cuda" else self.device

    def _ensure_shap_e_core(self, request_id: str | None = None, *, include_text_model: bool) -> None:
        needs_text = include_text_model and self.text_model is None
        needs_diffusion = self.diffusion is None
        needs_transmitter = self.transmitter is None
        if not (needs_text or needs_diffusion or needs_transmitter):
            return

        total = int(needs_text) + int(needs_diffusion) + int(needs_transmitter)
        done = 0
        load_device = self._shap_e_storage_device()

        with self._shap_e_lock:
            needs_text = include_text_model and self.text_model is None
            needs_diffusion = self.diffusion is None
            needs_transmitter = self.transmitter is None
            total = int(needs_text) + int(needs_diffusion) + int(needs_transmitter)
            if total <= 0:
                return

            def _update(message: str) -> None:
                self._progress_update(
                    request_id,
                    stage_key="model_loading",
                    stage_label="Loading Fallback Weights",
                    progress=(float(done) / float(total)) if total > 0 else 1.0,
                    current=done,
                    total=total,
                    message=message,
                )

            _update("Loading Shap-E fallback components...")
            if needs_diffusion:
                self._raise_if_cancelled(request_id)
                self.diffusion = diffusion_from_config(shap_e_load_config("diffusion"))
                done += 1
                _update("Shap-E diffusion config loaded")
            if needs_transmitter:
                self._raise_if_cancelled(request_id)
                self.transmitter = load_model("transmitter", device=load_device)
                done += 1
                _update(f"Shap-E transmitter loaded on {load_device}")
            if needs_text:
                self._raise_if_cancelled(request_id)
                self.text_model = load_model("text300M", device=load_device)
                done += 1
                _update(f"Shap-E text model loaded on {load_device}")

    def _ensure_shap_e_image_model(self, request_id: str | None = None) -> None:
        if self.image_model is not None:
            return
        with self._shap_e_lock:
            if self.image_model is not None:
                return
            self._progress_update(
                request_id,
                stage_key="model_loading",
                stage_label="Loading Fallback Weights",
                progress=0.0,
                current=0,
                total=1,
                message="Loading Shap-E image fallback model...",
            )
            self._raise_if_cancelled(request_id)
            self.image_model = load_model("image300M", device=self._shap_e_storage_device())
            self._patch_cached_model_kwargs(self.image_model)
            self._progress_update(
                request_id,
                stage_key="model_loading",
                stage_label="Loading Fallback Weights",
                progress=1.0,
                current=1,
                total=1,
                message="Shap-E image fallback model loaded",
            )
            print("[ShapeService] Shap-E image300M loaded")

    # ══ Utility ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _mesh_dims(mesh: trimesh.Trimesh) -> dict:
        ext = mesh.extents if mesh.extents is not None else [0.0, 0.0, 0.0]
        d = {
            "x": float(ext[0]) if len(ext) > 0 else 0.0,
            "y": float(ext[1]) if len(ext) > 1 else 0.0,
            "z": float(ext[2]) if len(ext) > 2 else 0.0,
        }
        d["max_extent"] = float(max(d["x"], d["y"], d["z"]))
        return d

    def _effective_h3d_preset(self, quality_preset: str) -> dict:
        pk = (quality_preset or "balanced").strip().lower()
        base = dict(_H3D_PRESETS.get(pk, _H3D_PRESETS["balanced"]))
        if self._low_vram_mode:
            if pk == "fast":
                base["num_inference_steps"] = min(int(base["num_inference_steps"]), 14)
                base["octree_resolution"] = min(int(base["octree_resolution"]), 224)
            elif pk == "balanced":
                base["num_inference_steps"] = min(int(base["num_inference_steps"]), 18)
                base["octree_resolution"] = min(int(base["octree_resolution"]), 256)
            elif pk == "quality":
                base["num_inference_steps"] = min(int(base["num_inference_steps"]), 30)
                base["octree_resolution"] = min(int(base["octree_resolution"]), 256)
        return base

    def _effective_text2image_preset(self, quality_preset: str) -> dict:
        pk = (quality_preset or "balanced").strip().lower()
        base = dict(_HUNYUAN_TEXT2IMAGE_PRESETS.get(pk, _HUNYUAN_TEXT2IMAGE_PRESETS["balanced"]))
        if self._low_vram_mode:
            if pk == "fast":
                base["steps"] = min(int(base["steps"]), 10)
                base["width"] = min(int(base["width"]), 1024)
                base["height"] = min(int(base["height"]), 1024)
            elif pk == "balanced":
                base["steps"] = min(int(base["steps"]), 12)
                base["width"] = min(int(base["width"]), 1024)
                base["height"] = min(int(base["height"]), 1024)
            elif pk == "quality":
                base["steps"] = min(int(base["steps"]), 14)
                base["width"] = min(int(base["width"]), 1024)
                base["height"] = min(int(base["height"]), 1024)
        return base

    def _enforce_strict_gpu(self, context: str):
        if self._strict_gpu_mode and self.device.type != "cuda":
            raise RuntimeError(f"Strict GPU mode requires CUDA for {context}, but CUDA is unavailable.")

    def prewarm_models(self, include_text2image: bool = False, keep_text2image_on_gpu: bool = False) -> dict:
        started = time.time()
        out: dict = {
            "device": str(self.device),
            "strict_gpu_mode": bool(self._strict_gpu_mode),
            "disable_quality_fallback": bool(self._disable_quality_fallback),
            "gpu_vram_gb": round(float(self._gpu_vram_gb), 2),
            "hunyuan3d_ready": False,
            "text2image_ready": False,
            "text2image_execution_mode": self._text2img_execution_mode,
            "include_text2image": bool(include_text2image),
            "keep_text2image_on_gpu": bool(keep_text2image_on_gpu),
            "errors": [],
        }
        try:
            p = self._get_hunyuan(request_id=None)
            out["hunyuan3d_ready"] = p is not None
        except Exception as e:
            out["errors"].append(f"hunyuan3d: {e}")
        try:
            if include_text2image and _HUNYUAN_TEXT2IMAGE_ENABLED:
                p2 = self._get_text2image(request_id=None)
                out["text2image_ready"] = p2 is not None
                out["text2image_execution_mode"] = self._text2img_execution_mode
                if p2 is not None and self.device.type == "cuda" and not keep_text2image_on_gpu:
                    self._text2img_to_cpu()
                    out["text2image_execution_mode"] = self._text2img_execution_mode
        except Exception as e:
            out["errors"].append(f"text2image: {e}")
        out["seconds"] = round(time.time() - started, 3)
        return out

    @staticmethod
    def _progress_fraction(
        progress: float | None,
        current: int | None,
        total: int | None,
    ) -> float | None:
        try:
            if progress is not None:
                return max(0.0, min(1.0, float(progress)))
        except Exception:
            pass
        try:
            if total is not None and int(total) > 0 and current is not None:
                return max(0.0, min(1.0, float(current) / float(total)))
        except Exception:
            pass
        return None

    @staticmethod
    def _progress_bar_name(stage_key: str | None) -> str | None:
        key = str(stage_key or "").strip().lower()
        if key in {"queued", "model_loading", "preprocess", "text2image"}:
            return "prep"
        if key in {"diffusion_sampling", "shap_e_sampling"}:
            return "diffusion"
        if key in {"volume_decoding", "shap_e_decode", "postprocess", "finalize"}:
            return "decode"
        return None

    @classmethod
    def _progress_sync_bars_locked(cls, st: dict) -> None:
        bars = dict(st.get("bars") or {})
        for name in ("prep", "diffusion", "decode"):
            try:
                bars[name] = max(0.0, min(1.0, float(bars.get(name, 0.0) or 0.0)))
            except Exception:
                bars[name] = 0.0

        stage_key = str(st.get("stage_key") or "")
        status = str(st.get("status") or "")
        active_bar = cls._progress_bar_name(stage_key)
        pct = cls._progress_fraction(
            st.get("progress"),
            st.get("current"),
            st.get("total"),
        )

        if status == "done" or stage_key == "done":
            bars["prep"] = 1.0
            bars["diffusion"] = 1.0
            bars["decode"] = 1.0
            active_bar = None
        elif active_bar == "prep":
            if pct is not None:
                bars["prep"] = max(bars["prep"], pct)
        elif active_bar == "diffusion":
            bars["prep"] = 1.0
            if pct is not None:
                bars["diffusion"] = max(bars["diffusion"], pct)
        elif active_bar == "decode":
            bars["prep"] = 1.0
            bars["diffusion"] = 1.0
            if pct is not None:
                bars["decode"] = max(bars["decode"], pct)

        if status in {"error", "cancelled"}:
            active_bar = None

        st["bars"] = {k: round(v, 4) for k, v in bars.items()}
        st["active_bar"] = active_bar

    def _progress_gc(self):
        now = time.time()
        stale_keys = []
        with self._progress_lock:
            for k, v in self._progress_state.items():
                ts = float(v.get("updated_at_unix") or 0.0)
                if ts > 0 and (now - ts) > (60.0 * 60.0):
                    stale_keys.append(k)
            for k in stale_keys:
                self._progress_state.pop(k, None)

    def _progress_start(self, request_id: str | None, *, mode: str, quality_preset: str, source: str):
        if not request_id:
            return
        self._progress_gc()
        now = time.time()
        with self._progress_lock:
            self._progress_state[request_id] = {
                "request_id": request_id,
                "status": "running",
                "mode": mode,
                "source": source,
                "quality_preset": quality_preset,
                "stage_key": "queued",
                "stage_label": "Queued",
                "message": "Job accepted",
                "progress": 0.0,
                "current": 0,
                "total": None,
                "started_at_unix": now,
                "stage_started_at_unix": now,
                "completed_at_unix": None,
                "stage_times": {},
                "updated_at_unix": now,
                "error": None,
                "cancel_requested": False,
                "bars": {"prep": 0.0, "diffusion": 0.0, "decode": 0.0},
                "active_bar": "prep",
            }
            self._progress_sync_bars_locked(self._progress_state[request_id])

    def _progress_has_request(self, request_id: str | None) -> bool:
        rid = str(request_id or "").strip()
        if not rid:
            return False
        with self._progress_lock:
            return rid in self._progress_state

    @staticmethod
    def _close_stage_time_locked(st: dict, now: float) -> None:
        stage_key = str(st.get("stage_key") or "")
        stage_started = float(st.get("stage_started_at_unix") or 0.0)
        if not stage_key or stage_started <= 0.0:
            return
        elapsed = max(0.0, now - stage_started)
        stage_times = dict(st.get("stage_times") or {})
        stage_times[stage_key] = float(stage_times.get(stage_key, 0.0) or 0.0) + elapsed
        st["stage_times"] = stage_times
        st["stage_started_at_unix"] = now

    @staticmethod
    def _build_perf_payload(stage_times: dict, started_at_unix: float | int | None, ended_at_unix: float | int | None) -> dict:
        st = {str(k): float(v) for k, v in (stage_times or {}).items() if isinstance(v, (int, float))}

        def _sum(keys: tuple[str, ...]) -> float:
            return float(sum(float(st.get(k, 0.0) or 0.0) for k in keys))

        total = 0.0
        try:
            s = float(started_at_unix or 0.0)
            e = float(ended_at_unix or 0.0)
            if s > 0.0 and e > s:
                total = e - s
        except Exception:
            total = 0.0
        if total <= 0.0:
            total = float(sum(st.values()))

        perf = {
            "total_s": round(total, 3),
            "model_loading_s": round(_sum(("model_loading",)), 3),
            "text2image_s": round(_sum(("text2image",)), 3),
            "preprocess_s": round(_sum(("preprocess",)), 3),
            "diffusion_sampling_s": round(_sum(("diffusion_sampling", "shap_e_sampling")), 3),
            "volume_decoding_s": round(_sum(("volume_decoding", "shap_e_decode")), 3),
            "postprocess_s": round(_sum(("postprocess",)), 3),
            "finalize_s": round(_sum(("finalize",)), 3),
            "stage_times_s": {k: round(v, 3) for k, v in st.items()},
        }
        return perf

    def _progress_update(
        self,
        request_id: str | None,
        *,
        stage_key: str,
        stage_label: str,
        progress: float | None = None,
        current: int | None = None,
        total: int | None = None,
        message: str | None = None,
    ):
        if not request_id:
            return
        with self._progress_lock:
            st = self._progress_state.get(request_id)
            if not st:
                return
            if st.get("status") == "cancelled":
                return
            prev_stage = str(st.get("stage_key") or "")
            now = time.time()
            stage_changed = stage_key != prev_stage
            if stage_changed:
                self._close_stage_time_locked(st, now)
                st["stage_key"] = stage_key
                st["stage_label"] = stage_label
                st["progress"] = (
                    max(0.0, min(1.0, float(progress)))
                    if progress is not None else 0.0
                )
                st["current"] = int(current) if current is not None else 0
                st["total"] = int(total) if total is not None else None
            else:
                st["stage_key"] = stage_key
                st["stage_label"] = stage_label
            if progress is not None and not stage_changed:
                st["progress"] = max(0.0, min(1.0, float(progress)))
            if current is not None and not stage_changed:
                st["current"] = int(current)
            if total is not None and not stage_changed:
                st["total"] = int(total)
            if message is not None:
                st["message"] = str(message)
            elif stage_changed:
                st["message"] = str(stage_label)
            st["updated_at_unix"] = now
            self._progress_sync_bars_locked(st)

    def _progress_done(self, request_id: str | None, *, result: dict | None = None):
        if not request_id:
            return
        with self._progress_lock:
            st = self._progress_state.get(request_id)
            if not st:
                return
            if st.get("status") in {"done", "error", "cancelled"}:
                return
            now = time.time()
            self._close_stage_time_locked(st, now)
            st["status"] = "done"
            st["stage_key"] = "done"
            st["stage_label"] = "Complete"
            st["progress"] = 1.0
            st["message"] = "Generation complete"
            st["completed_at_unix"] = now
            st["updated_at_unix"] = now
            perf = self._build_perf_payload(
                st.get("stage_times") or {},
                st.get("started_at_unix"),
                now,
            )
            st["perf"] = perf
            self._progress_sync_bars_locked(st)
            if result:
                result["perf"] = perf
                st["result"] = {
                    "seconds": float(result.get("seconds", 0.0)),
                    "faces": int(result.get("faces", 0)),
                    "quality_preset": result.get("quality_preset"),
                    "source_type": result.get("source_type"),
                    "perf": perf,
                }

    def _progress_error(self, request_id: str | None, error_text: str):
        if not request_id:
            return
        with self._progress_lock:
            st = self._progress_state.get(request_id)
            if not st:
                return
            if st.get("status") == "cancelled":
                return
            now = time.time()
            self._close_stage_time_locked(st, now)
            st["status"] = "error"
            st["stage_key"] = "error"
            st["stage_label"] = "Failed"
            st["message"] = str(error_text or "Generation failed")
            st["error"] = str(error_text or "Generation failed")
            st["completed_at_unix"] = now
            st["updated_at_unix"] = now
            st["perf"] = self._build_perf_payload(
                st.get("stage_times") or {},
                st.get("started_at_unix"),
                now,
            )
            self._progress_sync_bars_locked(st)

    def get_progress(self, request_id: str) -> dict:
        rid = str(request_id or "").strip()
        if not rid:
            return {"status": "missing_request_id"}
        with self._progress_lock:
            st = self._progress_state.get(rid)
            if not st:
                return {"request_id": rid, "status": "not_found"}
            out = dict(st)
            now = time.time()
            stage_times_live = dict(out.get("stage_times") or {})
            if out.get("status") in {"running", "cancelling"}:
                stage_key = str(out.get("stage_key") or "")
                stage_started = float(out.get("stage_started_at_unix") or 0.0)
                if stage_key and stage_started > 0.0:
                    stage_times_live[stage_key] = float(stage_times_live.get(stage_key, 0.0) or 0.0) + max(0.0, now - stage_started)
            end_ts = out.get("completed_at_unix") or now
            out["perf"] = self._build_perf_payload(
                stage_times_live,
                out.get("started_at_unix"),
                end_ts,
            )
        return out

    def request_cancel(self, request_id: str) -> dict:
        rid = str(request_id or "").strip()
        if not rid:
            return {"status": "missing_request_id"}
        with self._progress_lock:
            st = self._progress_state.get(rid)
            if not st:
                return {"request_id": rid, "status": "not_found"}
            st["cancel_requested"] = True
            if st.get("status") == "running":
                st["status"] = "cancelling"
            st["stage_key"] = "cancelling"
            st["stage_label"] = "Cancelling"
            st["message"] = "Cancellation requested"
            st["updated_at_unix"] = time.time()
            self._progress_sync_bars_locked(st)
            return {"request_id": rid, "status": st.get("status"), "cancel_requested": True}

    def _progress_cancelled(self, request_id: str | None, reason: str = "Cancelled by user"):
        if not request_id:
            return
        with self._progress_lock:
            st = self._progress_state.get(request_id)
            if not st:
                return
            now = time.time()
            self._close_stage_time_locked(st, now)
            st["status"] = "cancelled"
            st["stage_key"] = "cancelled"
            st["stage_label"] = "Cancelled"
            st["message"] = str(reason or "Cancelled")
            st["error"] = str(reason or "Cancelled")
            st["progress"] = max(0.0, min(1.0, float(st.get("progress") or 0.0)))
            st["completed_at_unix"] = now
            st["updated_at_unix"] = now
            st["perf"] = self._build_perf_payload(
                st.get("stage_times") or {},
                st.get("started_at_unix"),
                now,
            )
            self._progress_sync_bars_locked(st)

    def _is_cancel_requested(self, request_id: str | None) -> bool:
        rid = str(request_id or "").strip()
        if not rid:
            return False
        with self._progress_lock:
            st = self._progress_state.get(rid)
            if not st:
                return False
            return bool(st.get("cancel_requested"))

    def _raise_if_cancelled(self, request_id: str | None):
        if self._is_cancel_requested(request_id):
            self._progress_cancelled(request_id, "Generation cancelled by user")
            raise GenerationCancelledError("generation cancelled by user")

    def _hunyuan_progress_desc_update(self, request_id: str | None, desc: str, i: int, total: int | None):
        if not request_id:
            return
        self._raise_if_cancelled(request_id)
        desc_l = (desc or "").strip().lower()
        if total and total > 400 and (i % 8 != 0) and i != int(total):
            # Reduce lock/update overhead on long decode loops without losing useful UX updates.
            return
        if "diffusion" in desc_l:
            pct = (float(i) / float(total)) if total and total > 0 else None
            self._progress_update(
                request_id,
                stage_key="diffusion_sampling",
                stage_label="Diffusion Sampling",
                progress=pct,
                current=i,
                total=total,
                message="Diffusion Sampling",
            )
            return
        if "volume decoding" in desc_l:
            pct = (float(i) / float(total)) if total and total > 0 else None
            self._progress_update(
                request_id,
                stage_key="volume_decoding",
                stage_label="Volume Decoding",
                progress=pct,
                current=i,
                total=total,
                message="Volume Decoding",
            )
            return
        if total and total > 0:
            pct = float(i) / float(total)
            self._progress_update(
                request_id,
                stage_key="diffusion_sampling",
                stage_label=(desc or "Sampling").strip()[:48] or "Sampling",
                progress=pct,
                current=i,
                total=total,
                message=(desc or "Sampling"),
            )

    def _hunyuan_progress_patch(self, request_id: str | None):
        if not request_id:
            class _NoopCtx:
                def __enter__(self_inner):
                    return self_inner
                def __exit__(self_inner, exc_type, exc, tb):
                    return False
            return _NoopCtx()

        service = self

        class _PatchCtx:
            def __enter__(self_inner):
                service._hunyuan_tqdm_patch_lock.acquire()
                import hy3dgen.shapegen.pipelines as _hp
                import hy3dgen.shapegen.models.autoencoders.volume_decoders as _vd

                self_inner._hp = _hp
                self_inner._vd = _vd
                self_inner._orig_hp_tqdm = _hp.tqdm
                self_inner._orig_vd_tqdm = _vd.tqdm

                def _wrap_tqdm(orig_fn):
                    def _wrapped(iterable, *args, **kwargs):
                        kwargs = dict(kwargs)
                        desc = str(kwargs.get("desc") or "")
                        total = kwargs.get("total")
                        if total is None:
                            try:
                                total = len(iterable)
                            except Exception:
                                total = None
                        kwargs["disable"] = True
                        kwargs.setdefault("leave", False)
                        it = orig_fn(iterable, *args, **kwargs)
                        for idx, item in enumerate(it, 1):
                            service._raise_if_cancelled(request_id)
                            service._hunyuan_progress_desc_update(request_id, desc, idx, total)
                            yield item
                    return _wrapped

                _hp.tqdm = _wrap_tqdm(self_inner._orig_hp_tqdm)
                _vd.tqdm = _wrap_tqdm(self_inner._orig_vd_tqdm)
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                try:
                    self_inner._hp.tqdm = self_inner._orig_hp_tqdm
                    self_inner._vd.tqdm = self_inner._orig_vd_tqdm
                finally:
                    service._hunyuan_tqdm_patch_lock.release()
                return False

        return _PatchCtx()

    def _shap_e_progress_patch(
        self,
        request_id: str | None,
        *,
        stage_key: str,
        stage_label: str,
        message: str,
    ):
        if not request_id:
            class _NoopCtx:
                def __enter__(self_inner):
                    return self_inner
                def __exit__(self_inner, exc_type, exc, tb):
                    return False
            return _NoopCtx()

        service = self

        class _PatchCtx:
            def __enter__(self_inner):
                import tqdm.auto as _tqdm_auto

                self_inner._tqdm_auto = _tqdm_auto
                self_inner._orig_tqdm = _tqdm_auto.tqdm

                def _wrapped(iterable=None, *args, **kwargs):
                    kwargs = dict(kwargs)
                    total = kwargs.get("total")
                    if total is None and iterable is not None:
                        try:
                            total = len(iterable)
                        except Exception:
                            total = None
                    kwargs["disable"] = True
                    kwargs.setdefault("leave", False)
                    it = self_inner._orig_tqdm(iterable, *args, **kwargs)
                    for idx, item in enumerate(it, 1):
                        service._raise_if_cancelled(request_id)
                        pct = (float(idx) / float(total)) if total and total > 0 else None
                        service._progress_update(
                            request_id,
                            stage_key=stage_key,
                            stage_label=stage_label,
                            progress=pct,
                            current=idx,
                            total=total,
                            message=message,
                        )
                        yield item

                self_inner._tqdm_auto.tqdm = _wrapped
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                self_inner._tqdm_auto.tqdm = self_inner._orig_tqdm
                return False

        return _PatchCtx()

    # ══ PRIVATE: Text → 3D  (legacy Shap-E text300M fallback) ═════════════════

    def _generate_text_shap_e(
        self,
        prompt: str,
        quality_preset: str = "balanced",
        request_id: str | None = None,
    ) -> dict:
        job_id  = uuid.uuid4().hex
        job_dir = os.path.join(self.runs_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        t0 = time.time()

        pk     = (quality_preset or "balanced").strip().lower()
        preset = self.GENERATION_PRESETS.get(pk, self.GENERATION_PRESETS["balanced"])

        self._raise_if_cancelled(request_id)
        self._ensure_shap_e_core(request_id=request_id, include_text_model=True)
        self._shap_e_to_gpu()
        self._progress_update(
            request_id,
            stage_key="shap_e_sampling",
            stage_label="Diffusion Sampling",
            progress=0.0,
            current=0,
            total=int(preset["karras_steps"]),
            message="Sampling with Shap-E fallback",
        )

        with torch.inference_mode():
            with self._shap_e_progress_patch(
                request_id,
                stage_key="shap_e_sampling",
                stage_label="Diffusion Sampling",
                message="Sampling with Shap-E fallback",
            ):
                latents = sample_latents(
                    batch_size=1,
                    model=self.text_model,
                    diffusion=self.diffusion,
                    guidance_scale=float(preset["guidance_scale"]),
                    model_kwargs=dict(texts=[prompt]),
                    device=self.device,
                    progress=bool(request_id),
                    clip_denoised=True,
                    use_fp16=(self.device.type == "cuda"),
                    use_karras=True,
                    karras_steps=int(preset["karras_steps"]),
                    sigma_min=1e-3,
                    sigma_max=float(preset["sigma_max"]),
                    s_churn=0.0,
                )
            self._raise_if_cancelled(request_id)
            self._progress_update(
                request_id,
                stage_key="shap_e_decode",
                stage_label="Volume Decoding",
                progress=0.0,
                current=0,
                total=1,
                message="Decoding mesh from Shap-E latent",
            )
            decoded = decode_latent_mesh(self.transmitter, latents[0])
        self._raise_if_cancelled(request_id)
        self._progress_update(
            request_id,
            stage_key="shap_e_decode",
            stage_label="Volume Decoding",
            progress=1.0,
            current=1,
            total=1,
            message="Shap-E latent decoded",
        )

        self._progress_update(
            request_id,
            stage_key="postprocess",
            stage_label="Post-processing",
            progress=0.0,
            current=0,
            total=1,
            message="Cleaning mesh topology",
        )
        tri  = decoded.tri_mesh()
        mesh = trimesh.Trimesh(vertices=tri.verts, faces=tri.faces, process=False)
        mesh = clean_and_decimate(mesh)
        self._progress_update(
            request_id,
            stage_key="postprocess",
            stage_label="Post-processing",
            progress=1.0,
            current=1,
            total=1,
            message="Mesh cleaned",
        )

        stl_path = os.path.join(job_dir, "model.stl")
        self._progress_update(
            request_id,
            stage_key="finalize",
            stage_label="Finalize",
            progress=0.0,
            current=0,
            total=1,
            message="Exporting STL",
        )
        mesh.export(stl_path)
        self._progress_update(
            request_id,
            stage_key="finalize",
            stage_label="Finalize",
            progress=1.0,
            current=1,
            total=1,
            message="Mesh export complete",
        )

        return {
            "job_id": job_id,
            "seconds": time.time() - t0,
            "faces": len(mesh.faces),
            "stl_path": stl_path,
            "quality_preset": pk if pk in self.GENERATION_PRESETS else "balanced",
            "generation_config": {
                "engine":         "shap-e-text300M",
                "execution_mode": ("cuda" if self.device.type == "cuda" else "cpu"),
                "guidance_scale": float(preset["guidance_scale"]),
                "karras_steps":   int(preset["karras_steps"]),
                "sigma_max":      float(preset["sigma_max"]),
                "gpu_vram_gb":    round(float(self._gpu_vram_gb), 2),
                "low_vram_mode":  bool(self._low_vram_mode),
                "strict_gpu_mode": bool(self._strict_gpu_mode),
            },
            "dimensions_mm": self._mesh_dims(mesh),
        }

    # ══ PUBLIC: Text → 3D  (Hunyuan-first chain) ══════════════════════════════

    def generate(
        self,
        prompt: str,
        quality_preset: str = "balanced",
        request_id: str | None = None,
    ) -> dict:
        pk = (quality_preset or "balanced").strip().lower()
        t0 = time.time()
        self._enforce_strict_gpu("text generation")
        self._progress_start(
            request_id,
            mode="text",
            quality_preset=pk if pk in ("fast", "balanced", "quality") else "balanced",
            source="text_prompt",
        )
        self._raise_if_cancelled(request_id)

        # Preferred path: text -> reference image -> Hunyuan image->3D
        if HUNYUAN_AVAILABLE:
            try:
                ref_img, t2i_meta = self._prompt_to_reference_image(prompt, pk, request_id=request_id)
                self._raise_if_cancelled(request_id)
                t2i_seconds = time.time() - t0
                # Free VRAM before Hunyuan3D stage; on 8GB cards this avoids very slow decode.
                self._text2img_to_cpu()
                self._progress_update(
                    request_id,
                    stage_key="preprocess",
                    stage_label="Image preprocessing",
                    progress=0.0,
                    message="Preparing reference image for 3D reconstruction",
                )
                result = self.generate_from_image(
                    ref_img,
                    quality_preset=pk,
                    source="text_prompt",
                    request_id=request_id,
                )
                result["seconds"] = float(result.get("seconds", 0.0)) + t2i_seconds
                cfg = dict(result.get("generation_config") or {})
                cfg.update(
                    {
                        "engine": f"hunyuan-text2image->{cfg.get('engine', 'hunyuan3d-2')}",
                        "text2image_execution_mode": self._text2img_execution_mode,
                        "text2image_model_id": t2i_meta["model_id"],
                        "text2image_seed": t2i_meta["seed"],
                        "text2image_steps": t2i_meta["steps"],
                        "text2image_size": f"{t2i_meta['width']}x{t2i_meta['height']}",
                        "text2image_guidance_scale": t2i_meta["guidance_scale"],
                        "text2image_seconds": round(t2i_seconds, 3),
                        "strict_gpu_mode": bool(self._strict_gpu_mode),
                    }
                )
                result["generation_config"] = cfg
                result["source_type"] = "text_prompt"
                self._progress_done(request_id, result=result)
                return result
            except GenerationCancelledError:
                self._progress_cancelled(request_id, "Generation cancelled by user")
                raise
            except Exception as e:
                self._text2img_last_error = str(e)
                if pk == "quality" and self._disable_quality_fallback:
                    msg = (
                        "Quality mode requires Hunyuan text->3D on CUDA. "
                        f"Primary path failed: {e}"
                    )
                    self._progress_error(request_id, msg)
                    raise RuntimeError(msg)
                print(f"[ShapeService] Hunyuan text->3D chain failed, using Shap-E text fallback ({e})")

        if pk == "quality" and self._disable_quality_fallback:
            msg = (
                "Quality mode requires Hunyuan text->3D on CUDA, "
                "but primary models are unavailable."
            )
            self._progress_error(request_id, msg)
            raise RuntimeError(msg)

        # Last fallback: original Shap-E text pipeline.
        try:
            fallback = self._generate_text_shap_e(prompt, quality_preset=pk, request_id=request_id)
            cfg = dict(fallback.get("generation_config") or {})
            cfg.update(
                {
                    "fallback_from": "hunyuan-text2image->hunyuan3d-2",
                    "fallback_reason": self._text2img_last_error or self._hunyuan_last_error or "Hunyuan text pipeline unavailable",
                }
            )
            fallback["generation_config"] = cfg
            self._progress_done(request_id, result=fallback)
            return fallback
        except GenerationCancelledError:
            self._progress_cancelled(request_id, "Generation cancelled by user")
            raise
        except Exception as e:
            self._progress_error(request_id, str(e))
            raise

    # ══ PUBLIC: Image → 3D  (Hunyuan3D-2  ▷  Shap-E fallback) ════════════════

    def generate_from_image(
        self,
        image: Image.Image,
        quality_preset: str = "balanced",
        source: str = "upload",
        request_id: str | None = None,
    ) -> dict:
        job_id  = uuid.uuid4().hex
        job_dir = os.path.join(self.runs_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        t0 = time.time()

        pk       = (quality_preset or "balanced").strip().lower()
        self._enforce_strict_gpu("image generation")
        src_path = os.path.join(job_dir, "source.png")
        image.save(src_path, format="PNG")
        if not self._progress_has_request(request_id):
            self._progress_start(
                request_id,
                mode="image",
                quality_preset=pk if pk in ("fast", "balanced", "quality") else "balanced",
                source=source,
            )
        self._raise_if_cancelled(request_id)
        self._progress_update(
            request_id,
            stage_key="preprocess",
            stage_label="Image preprocessing",
            progress=0.0,
            message="Preparing image for 3D reconstruction",
        )
        # If text2image is cached on CUDA from previous text runs, offload it now.
        self._text2img_to_cpu()

        # ── Attempt Hunyuan3D-2 ───────────────────────────────────────────
        pipe = self._get_hunyuan(request_id=request_id)
        if pipe is not None:
            try:
                self._raise_if_cancelled(request_id)
                hp      = self._effective_h3d_preset(pk)
                prepped = self._prepare_for_hunyuan(image)
                prepped.save(os.path.join(job_dir, "source_prepared.png"), format="PNG")
                self._progress_update(
                    request_id,
                    stage_key="preprocess",
                    stage_label="Image preprocessing",
                    progress=1.0,
                    message="Image prepared",
                )

                with torch.inference_mode():
                    with self._hunyuan_progress_patch(request_id):
                        try:
                            # Full parameter set (most Hunyuan3D-2 versions)
                            self._raise_if_cancelled(request_id)
                            print(f"[ShapeService] Hunyuan3D-2 diffusion running "
                                f"({hp['num_inference_steps']} steps, "
                                f"octree_res={hp['octree_resolution']}) — please wait...")
                            result = pipe(
                                image=prepped,
                                num_inference_steps=int(hp["num_inference_steps"]),
                                guidance_scale=float(hp["guidance_scale"]),
                                octree_resolution=int(hp["octree_resolution"]),
                                remove_bg=False,   # already done by rembg above
                                enable_pbar=bool(request_id),
                            )
                        except TypeError:
                            # Older or minimal API — just pass image
                            self._raise_if_cancelled(request_id)
                            result = pipe(image=prepped)

                self._raise_if_cancelled(request_id)
                self._progress_update(
                    request_id,
                    stage_key="postprocess",
                    stage_label="Post-processing",
                    progress=0.0,
                    current=0,
                    total=1,
                    message="Cleaning mesh topology",
                )

                mesh = self._extract_mesh(result)
                if mesh is None:
                    raise ValueError("Hunyuan3D-2 returned no valid mesh object")

                mesh     = self._hunyuan_postprocess(mesh)
                self._progress_update(
                    request_id,
                    stage_key="postprocess",
                    stage_label="Post-processing",
                    progress=1.0,
                    current=1,
                    total=1,
                    message="Mesh cleaned",
                )
                stl_path = os.path.join(job_dir, "model.stl")
                self._progress_update(
                    request_id,
                    stage_key="finalize",
                    stage_label="Finalize",
                    progress=0.0,
                    current=0,
                    total=1,
                    message="Exporting STL",
                )
                mesh.export(stl_path)
                self._progress_update(
                    request_id,
                    stage_key="finalize",
                    stage_label="Finalize",
                    progress=1.0,
                    current=1,
                    total=1,
                    message="Mesh export complete",
                )
                out = {
                    "job_id": job_id,
                    "seconds": time.time() - t0,
                    "faces": len(mesh.faces),
                    "stl_path": stl_path,
                    "source_image_path": src_path,
                    "source_type": source,
                    "quality_preset": pk,
                    "generation_config": {
                        "engine":              "hunyuan3d-2",
                        "execution_mode":      ("cuda" if self.device.type == "cuda" else "cpu"),
                        "num_inference_steps": int(hp["num_inference_steps"]),
                        "guidance_scale":      float(hp["guidance_scale"]),
                        "octree_resolution":   int(hp["octree_resolution"]),
                        "rembg_applied":       REMBG_AVAILABLE,
                        "gpu_vram_gb":         round(float(self._gpu_vram_gb), 2),
                        "low_vram_mode":       bool(self._low_vram_mode),
                        "strict_gpu_mode":     bool(self._strict_gpu_mode),
                    },
                    "dimensions_mm": self._mesh_dims(mesh),
                }
                self._progress_done(request_id, result=out)
                return out

            except GenerationCancelledError:
                self._progress_cancelled(request_id, "Generation cancelled by user")
                raise
            except Exception as e:
                import traceback
                self._hunyuan_last_error = str(e)
                if pk == "quality" and self._disable_quality_fallback:
                    msg = (
                        "Quality mode requires Hunyuan3D-2 on CUDA. "
                        f"Primary path failed: {e}"
                    )
                    self._progress_error(request_id, msg)
                    raise RuntimeError(msg)
                print(f"[ShapeService] Hunyuan3D-2 failed - falling back to Shap-E ({e})")
                traceback.print_exc()

        if pk == "quality" and self._disable_quality_fallback:
            msg = (
                "Quality mode requires Hunyuan3D-2 on CUDA, "
                "but primary model is unavailable."
            )
            self._progress_error(request_id, msg)
            raise RuntimeError(msg)

        # ── Shap-E image300M fallback ─────────────────────────────────────
        print("[ShapeService] Using Shap-E image300M (fallback path)")
        try:
            self._raise_if_cancelled(request_id)
            out = self._shap_e_image_fallback(image, job_id, job_dir, src_path, source, pk, t0, request_id=request_id)
            self._progress_done(request_id, result=out)
            return out
        except GenerationCancelledError:
            self._progress_cancelled(request_id, "Generation cancelled by user")
            raise
        except Exception as e:
            self._progress_error(request_id, str(e))
            raise

    # ── private: Shap-E image300M ─────────────────────────────────────────────

    def _shap_e_image_fallback(
        self, image, job_id, job_dir, src_path, source, pk, t0, request_id: str | None = None
    ) -> dict:
        self._raise_if_cancelled(request_id)
        preset = self.IMAGE_GENERATION_PRESETS.get(pk, self.IMAGE_GENERATION_PRESETS["balanced"])
        self._progress_update(
            request_id,
            stage_key="shap_e_sampling",
            stage_label="Diffusion Sampling",
            progress=0.0,
            current=0,
            total=int(preset["karras_steps"]),
            message="Sampling with Shap-E image fallback",
        )

        self._ensure_shap_e_core(request_id=request_id, include_text_model=False)
        self._ensure_shap_e_image_model(request_id=request_id)
        self._shap_e_to_gpu()
        if self.device.type == "cuda" and self._module_device(self.image_model).type != "cuda":
            self._move_model_to_device(self.image_model, self.device)

        img = image.convert("RGB")
        w, h  = img.size
        side  = min(w, h)
        img   = img.crop(((w - side) // 2, (h - side) // 2,
                           (w + side) // 2, (h + side) // 2))
        rs    = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS
        img   = img.resize((256, 256), rs)

        with torch.inference_mode():
            with self._shap_e_progress_patch(
                request_id,
                stage_key="shap_e_sampling",
                stage_label="Diffusion Sampling",
                message="Sampling with Shap-E image fallback",
            ):
                latents = sample_latents(
                    batch_size=1,
                    model=self.image_model,
                    diffusion=self.diffusion,
                    guidance_scale=float(preset["guidance_scale"]),
                    model_kwargs={"images": [img]},
                    device=self.device,
                    progress=bool(request_id),
                    clip_denoised=True,
                    use_fp16=(self.device.type == "cuda"),
                    use_karras=True,
                    karras_steps=int(preset["karras_steps"]),
                    sigma_min=1e-3,
                    sigma_max=float(preset["sigma_max"]),
                    s_churn=0.0,
                )
            self._raise_if_cancelled(request_id)
            self._progress_update(
                request_id,
                stage_key="shap_e_decode",
                stage_label="Volume Decoding",
                progress=0.0,
                current=0,
                total=1,
                message="Decoding mesh from Shap-E latent",
            )
            decoded = decode_latent_mesh(self.transmitter, latents[0])
        self._raise_if_cancelled(request_id)
        self._progress_update(
            request_id,
            stage_key="shap_e_decode",
            stage_label="Volume Decoding",
            progress=1.0,
            current=1,
            total=1,
            message="Shap-E latent decoded",
        )

        self._progress_update(
            request_id,
            stage_key="postprocess",
            stage_label="Post-processing",
            progress=0.0,
            current=0,
            total=1,
            message="Cleaning mesh topology",
        )
        tri  = decoded.tri_mesh()
        mesh = trimesh.Trimesh(vertices=tri.verts, faces=tri.faces, process=False)
        mesh = clean_and_decimate(mesh)
        self._progress_update(
            request_id,
            stage_key="postprocess",
            stage_label="Post-processing",
            progress=1.0,
            current=1,
            total=1,
            message="Mesh cleaned",
        )

        stl_path = os.path.join(job_dir, "model.stl")
        self._progress_update(
            request_id,
            stage_key="finalize",
            stage_label="Finalize",
            progress=0.0,
            current=0,
            total=1,
            message="Exporting STL",
        )
        mesh.export(stl_path)
        self._raise_if_cancelled(request_id)
        self._progress_update(
            request_id,
            stage_key="finalize",
            stage_label="Finalize",
            progress=1.0,
            current=1,
            total=1,
            message="Mesh export complete",
        )

        return {
            "job_id": job_id,
            "seconds": time.time() - t0,
            "faces": len(mesh.faces),
            "stl_path": stl_path,
            "source_image_path": src_path,
            "source_type": source,
            "quality_preset": pk if pk in self.IMAGE_GENERATION_PRESETS else "balanced",
            "generation_config": {
                "engine":         "shap-e-image300M",
                "execution_mode": ("cuda" if self.device.type == "cuda" else "cpu"),
                "guidance_scale": float(preset["guidance_scale"]),
                "karras_steps":   int(preset["karras_steps"]),
                "sigma_max":      float(preset["sigma_max"]),
                "fallback_from":  "hunyuan3d-2",
                "fallback_reason": self._hunyuan_last_error or "Hunyuan unavailable",
                "gpu_vram_gb":    round(float(self._gpu_vram_gb), 2),
                "low_vram_mode":  bool(self._low_vram_mode),
                "strict_gpu_mode": bool(self._strict_gpu_mode),
            },
            "dimensions_mm": self._mesh_dims(mesh),
        }
