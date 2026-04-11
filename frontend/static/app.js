import * as THREE from "./vendor/three.module.js";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { STLLoader } from "./vendor/STLLoader.js";

const $ = (id) => document.getElementById(id);

const els = {
  presetButtons: Array.from(document.querySelectorAll(".preset-btn")),
  modeButtons: Array.from(document.querySelectorAll(".mode-btn")),
  modePanels: {
    text: $("modeTextPanel"),
    image: $("modeImagePanel"),
    gallery: $("modeGalleryPanel"),
    keychain: $("modeKeychainPanel"),
  },
  promptInput: $("promptInput"),
  charCount: $("charCount"),
  keychainNameInput: $("keychainNameInput"),
  keychainCharCount: $("keychainCharCount"),
  templateFacts: $("templateFacts"),
  sourceSummary: $("sourceSummary"),
  imageDropzone: $("imageDropzone"),
  cameraCaptureBtn: $("cameraCaptureBtn"),
  imageUploadInput: $("imageUploadInput"),
  cameraInput: $("cameraInput"),
  sourcePreview: $("sourcePreview"),
  sourcePreviewImage: $("sourcePreviewImage"),
  sourcePreviewTitle: $("sourcePreviewTitle"),
  sourcePreviewMeta: $("sourcePreviewMeta"),
  clearSourceBtn: $("clearSourceBtn"),
  recipeRack: $("recipeRack"),
  generateBtn: $("generateBtn"),
  cancelBtn: $("cancelBtn"),
  statusLine: $("statusLine"),
  microMode: $("microMode"),
  microPreset: $("microPreset"),
  microOutput: $("microOutput"),
  microReadiness: $("microReadiness"),
  viewer: $("viewer"),
  templateStage: $("templateStage"),
  templateStageNote: $("templateStageNote"),
  keychainFrontBtn: $("keychainFrontBtn"),
  keychainBackBtn: $("keychainBackBtn"),
  viewerEmpty: $("viewerEmpty"),
  viewerFrame: $("viewerFrame"),
  previewStageCard: $("previewStageCard"),
  viewerTitle: $("viewerTitle"),
  viewer3dBtn: $("viewer3dBtn"),
  viewerPlateBtn: $("viewerPlateBtn"),
  viewerFullscreenBtn: $("viewerFullscreenBtn"),
  previewOverlayCloseBtn: $("previewOverlayCloseBtn"),
  progressDock: $("progressDock"),
  progressStage: $("progressStage"),
  progressMessage: $("progressMessage"),
  progressPrepFill: $("progressPrepFill"),
  progressPrepValue: $("progressPrepValue"),
  progressDiffusionFill: $("progressDiffusionFill"),
  progressDiffusionValue: $("progressDiffusionValue"),
  progressDecodeFill: $("progressDecodeFill"),
  progressDecodeValue: $("progressDecodeValue"),
  resultSeconds: $("resultSeconds"),
  resultFaces: $("resultFaces"),
  resultDimensions: $("resultDimensions"),
  resultEngine: $("resultEngine"),
  exportMenuBtn: $("exportMenuBtn"),
  exportMenu: $("exportMenu"),
  exportStlBtn: $("exportStlBtn"),
  exportObjBtn: $("exportObjBtn"),
  export3mfBtn: $("export3mfBtn"),
  healthPill: $("healthPill"),
  queuePill: $("queuePill"),
  clockPill: $("clockPill"),
  refreshSnapshotBtn: $("refreshSnapshotBtn"),
  printerSelect: $("printerSelect"),
  printerStage: $("printerStage"),
  printerJob: $("printerJob"),
  printerProgress: $("printerProgress"),
  printerTemps: $("printerTemps"),
  printerRemaining: $("printerRemaining"),
  printerTimeline: $("printerTimeline"),
  printerHint: $("printerHint"),
  amsTrayRail: $("amsTrayRail"),
  resumeBtn: $("resumeBtn"),
  stopBtn: $("stopBtn"),
  intentButtons: Array.from(document.querySelectorAll("[data-intent]")),
  sizeRange: $("sizeRange"),
  sizeReadout: $("sizeReadout"),
  scaleReadout: $("scaleReadout"),
  sizePresetButtons: Array.from(document.querySelectorAll("[data-size]")),
  supportButtons: Array.from(document.querySelectorAll("[data-support]")),
  autoStartToggle: $("autoStartToggle"),
  useAmsToggle: $("useAmsToggle"),
  amsSlotSelect: $("amsSlotSelect"),
  jobNameInput: $("jobNameInput"),
  estimateBtn: $("estimateBtn"),
  preflightBtn: $("preflightBtn"),
  queueBtn: $("queueBtn"),
  printBtn: $("printBtn"),
  manufactureSummary: $("manufactureSummary"),
  perfTotal: $("perfTotal"),
  perfSampling: $("perfSampling"),
  perfDecode: $("perfDecode"),
  queueList: $("queueList"),
  galleryFilters: $("galleryFilters"),
  galleryRail: $("galleryRail"),
  toast: $("toast"),
  themeToggle: $("themeToggle"),
  keychainSwatches: $("keychainSwatches"),
  amsSwatchHint: $("amsSwatchHint"),
  bedPaneInfo: $("bedPaneInfo"),
  bedPaneSubtitle: $("bedPaneSubtitle") || document.querySelector(".bed-pane-subtitle"),
  viewerMain: $("viewerMain"),
  viewerBedPane: $("viewerBedPane"),
  bedCanvasWrap: $("bedCanvasWrap"),
  bedPreviewCanvas: $("bedPreviewCanvas"),
  bedFocusBtn: $("bedFocusBtn"),
  bedFullBtn: $("bedFullBtn"),
  sizeSettingRow: $("sizeSettingRow"),
  supportSettingRow: $("supportSettingRow"),
  templatePrintLockNote: $("templatePrintLockNote"),
  printReviewOverlay: $("printReviewOverlay"),
  printReviewTitle: $("printReviewTitle"),
  printReviewCloseBtn: $("printReviewCloseBtn"),
  printReviewPreviewImage: $("printReviewPreviewImage"),
  printReviewPreviewFrame: $("printReviewPreviewFrame"),
  printReviewPreviewFallback: $("printReviewPreviewFallback"),
  printReviewPreviewCaption: $("printReviewPreviewCaption"),
  printReviewLead: $("printReviewLead"),
  printReviewGrid: $("printReviewGrid"),
  printReviewFilamentNote: $("printReviewFilamentNote"),
  printReviewFilaments: $("printReviewFilaments"),
  printReviewNote: $("printReviewNote"),
  printReviewBackBtn: $("printReviewBackBtn"),
  printReviewConfirmBtn: $("printReviewConfirmBtn"),
};

const PROMPT_MAX = 320;
const SNAPSHOT_INTERVAL_MS = 12000;
const PROGRESS_INTERVAL_MS = 500;

const CATEGORY_LABELS = {
  all: "All",
  home_objects: "Home",
  automotive_parts: "Auto",
  cosmetics_packaging: "Cosmetics",
  desk_accessories: "Desk",
  games_toys: "Games",
  industrial_parts: "Industrial",
  abstract_decor: "Abstract",
  architecture_models: "Architecture",
};

const TEXT_RECIPES = [
  {
    title: "Architectural decor",
    prompt: "A sculptural desktop decor object with a monolithic profile, softened edges, and a premium stone-like silhouette.",
  },
  {
    title: "Automotive helper",
    prompt: "A compact automotive cable guide with reinforced clips, rounded contact faces, and clean printable geometry.",
  },
  {
    title: "Desk organizer",
    prompt: "A modular desk organizer tray with subtle ribs, cable relief channels, and a precise modern finish.",
  },
  {
    title: "Hospitality piece",
    prompt: "A premium incense holder with a stable base, hidden ash channel, and elegant architectural proportion.",
  },
  {
    title: "Retail display",
    prompt: "A branded product display stand with layered terraces, stable feet, and soft edge transitions.",
  },
  {
    title: "Industrial bracket",
    prompt: "A reinforced corner bracket with ribs, counterbored holes, and thick fillets designed for clean printing.",
  },
];

const SIZE_PRESETS = {
  small: 48,
  medium: 70,
  large: 110,
};

const INTENT_PRESETS = {
  balanced: { label: "Balanced", mode: "decorative", infillPercent: 18 },
  decorative: { label: "Decor", mode: "decorative", infillPercent: 12 },
  durable: { label: "Durable", mode: "durable", infillPercent: 30 },
};

// ── 3-D Bed Viewer (Bambu X1C textured PEI plate) ───────────────────────────
const BED_MM = 256;

const bedViewer3D = {
  renderer: null,
  scene:    null,
  camera:   null,
  controls: null,
  modelMesh: null,
  axes: null,
  frameHalfSpan: 140,
};

function isPrinterStateLive(gcodeState) {
  const state = String(gcodeState || "").toUpperCase();
  return state === "RUNNING" || state === "PREPARE" || state === "FINISH";
}

function buildBedAxisArrow(direction, color, length, shaftRadius = 1.2, tipRadius = 3.0, tipLength = 8) {
  const group = new THREE.Group();
  const axis = direction.clone().normalize();
  const shaftLength = Math.max(6, length - tipLength);
  const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis);
  const material = new THREE.MeshStandardMaterial({ color, metalness: 0.12, roughness: 0.42 });

  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(shaftRadius, shaftRadius, shaftLength, 12),
    material,
  );
  shaft.position.copy(axis.clone().multiplyScalar(shaftLength * 0.5));
  shaft.quaternion.copy(quat);
  group.add(shaft);

  const tip = new THREE.Mesh(
    new THREE.ConeGeometry(tipRadius, tipLength, 16),
    material,
  );
  tip.position.copy(axis.clone().multiplyScalar(shaftLength + (tipLength * 0.5)));
  tip.quaternion.copy(quat);
  group.add(tip);

  return group;
}

function buildBedAxesMarker() {
  const group = new THREE.Group();
  group.add(buildBedAxisArrow(new THREE.Vector3(1, 0, 0), 0xff6456, 30));
  group.add(buildBedAxisArrow(new THREE.Vector3(0, 1, 0), 0x5fcf78, 26));
  group.add(buildBedAxisArrow(new THREE.Vector3(0, 0, -1), 0x4d8fff, 30));
  group.position.set(-(BED_MM * 0.46), 0.12, (BED_MM * 0.46));
  return group;
}

const state = {
  mode: "text",
  preset: "balanced",
  galleryFilter: "all",
  prompt: "",
  keychainName: "",
  keychainNameColor: "#F5641EFF",
  keychainColorSlots: [],
  source: null,
  isGenerating: false,
  requestId: null,
  progress: null,
  currentModel: null,
  health: null,
  printers: [],
  selectedPrinter: "",
  printerStatus: null,
  printerStatusError: null,
  queue: null,
  library: [],
  templates: [],
  intent: "balanced",
  supportMode: "auto",
  sizePreset: "medium",
  targetMaxExtentMm: SIZE_PRESETS.medium,
  autoStart: false,
  useAms: true,
  amsSlot: "",
  jobName: "",
  estimate: null,
  preflight: null,
  manufactureBusy: "",
  manufactureSummaryOverride: null,
  lastPerf: null,
  abortCtrl: null,
  progressTimer: null,
  snapshotTimer: null,
  toastTimer: null,
  previewPane: "3d",
  previewExpanded: false,
  bedViewMode: "focus",
  printReviewOpen: false,
  printReviewSending: false,
};

const viewer = {
  scene: null,
  camera: null,
  renderer: null,
  controls: null,
  loader: new STLLoader(),
  mesh: null,
  renderMesh: null,
  stage: null,
  ring: null,
  isTemplateModel: false,
  templateView: "front",
  templatePivot: null,
  loadToken: 0,
  resizeObserver: null,
};

function makeRequestId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch (_) {
    data = null;
  }
  if (!res.ok) {
    const msg = data?.error || text || `${res.status} ${res.statusText}`;
    throw new Error(msg);
  }
  return data;
}

function showToast(message, timeoutMs = 2800) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => {
    els.toast.hidden = true;
  }, timeoutMs);
}

function setStatus(message) {
  els.statusLine.textContent = message;
}

function formatPercent(value) {
  return `${Math.round(Math.max(0, Math.min(1, Number(value || 0))) * 100)}%`;
}

function formatSeconds(seconds) {
  const n = Number(seconds || 0);
  return n > 0 ? `${n.toFixed(1)}s` : "--";
}

function formatMinutes(minutes) {
  const m = Number(minutes || 0);
  if (!Number.isFinite(m) || m <= 0) return "--";
  const h = Math.floor(m / 60);
  const min = Math.round(m % 60);
  if (h <= 0) return `${min}m`;
  return `${h}h ${min}m`;
}

function normalizeDimensions(raw) {
  if (!raw || typeof raw !== "object") return null;
  const x = Number(raw.x ?? raw.width ?? raw.size_x ?? 0);
  const y = Number(raw.y ?? raw.depth ?? raw.size_y ?? 0);
  const z = Number(raw.z ?? raw.height ?? raw.size_z ?? 0);
  if (x <= 0 || y <= 0 || z <= 0) return null;
  return { x, y, z };
}

function formatDimensions(dimensions) {
  if (!dimensions) return "--";
  return `${dimensions.x.toFixed(0)} x ${dimensions.y.toFixed(0)} x ${dimensions.z.toFixed(0)} mm`;
}

function maxModelExtent(dimensions) {
  if (!dimensions) return 0;
  return Math.max(Number(dimensions.x || 0), Number(dimensions.y || 0), Number(dimensions.z || 0));
}

function computedScalePercent() {
  const extent = maxModelExtent(state.currentModel?.dimensionsMm);
  if (!extent) return 100;
  return Math.max(1, Math.round((Number(state.targetMaxExtentMm) / extent) * 100));
}

function formatEngine(config) {
  if (!config || typeof config !== "object") return "--";
  const engine = String(config.engine || "unknown");
  const mode = String(config.execution_mode || config.text2image_execution_mode || "");
  return mode ? `${engine}/${mode}` : engine;
}

function hexToCssColor(hex) {
  const clean = String(hex || "").replace("#", "").trim();
  if (clean.length === 8) return `#${clean.slice(0, 6)}`;
  if (clean.length === 6) return `#${clean}`;
  return "var(--surface-4)";
}

function normalizeHex8(hex) {
  const clean = String(hex || "").replace("#", "").trim().toUpperCase();
  if (clean.length === 8) return `#${clean}`;
  if (clean.length === 6) return `#${clean}FF`;
  return null;
}

function hexToRgb(hex) {
  const norm = normalizeHex8(hex);
  if (!norm) return null;
  return {
    r: parseInt(norm.slice(1, 3), 16),
    g: parseInt(norm.slice(3, 5), 16),
    b: parseInt(norm.slice(5, 7), 16),
  };
}

function colorDistance(a, b) {
  const ca = hexToRgb(a);
  const cb = hexToRgb(b);
  if (!ca || !cb) return Number.POSITIVE_INFINITY;
  const dr = ca.r - cb.r;
  const dg = ca.g - cb.g;
  const db = ca.b - cb.b;
  return Math.sqrt((dr * dr) + (dg * dg) + (db * db));
}

function colorLuminance(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return 999;
  return 0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b;
}

function isOrangeLike(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return false;
  const { r, g, b } = rgb;
  return r > 190 && g > 70 && g < 180 && b < 110;
}

function isLightColor(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return false;
  const luminance = (0.2126 * rgb.r) + (0.7152 * rgb.g) + (0.0722 * rgb.b);
  return luminance >= 205;
}

function pickClosestTraySlot(targetColor) {
  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  if (!trays.length) return "";
  let bestSlot = "";
  let bestScore = Number.POSITIVE_INFINITY;
  trays.forEach((tray) => {
    const trayColor = normalizeHex8(tray.color);
    if (!trayColor) return;
    const score = colorDistance(trayColor, targetColor);
    if (score < bestScore) {
      bestScore = score;
      bestSlot = String(tray.slot);
    }
  });
  return bestSlot;
}

function effectiveAmsSlot() {
  if (!state.useAms) return "";
  if (state.amsSlot) return String(state.amsSlot);
  if (state.currentModel?.templateKey === "bridge_keychain" || state.mode === "keychain") {
    return pickClosestTraySlot(state.keychainNameColor || "#F5641EFF");
  }
  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  const active = String(state.printerStatus?.ams?.active_slot || "");
  if (active) return active;
  return trays[0] ? String(trays[0].slot) : "";
}

function selectedTrayLabel() {
  const slot = effectiveAmsSlot();
  if (!slot) return state.useAms ? "Auto AMS" : "Manual spool";
  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  const tray = trays.find((item) => String(item.slot) === String(slot));
  if (!tray) return `Slot ${slot}`;
  return `Slot ${slot}${tray.type ? ` · ${tray.type}` : ""}`;
}

function materialTypeShortLabel(type) {
  const raw = String(type || "").trim();
  if (!raw) return "";
  const upper = raw.toUpperCase();
  if (upper.includes("ABS")) return "ABS";
  if (upper.includes("PLA")) return "PLA";
  if (upper.includes("PETG")) return "PETG";
  if (upper.includes("ASA")) return "ASA";
  if (upper.includes("TPU")) return "TPU";
  if (upper.includes("PVA")) return "PVA";
  if (upper.includes("HIPS")) return "HIPS";
  if (upper.includes("SUPPORT")) return "Support";
  if (/\bPA\d*\b/.test(upper) || upper.includes("NYLON")) return "PA";
  if (/\bPC\b/.test(upper) || upper.includes("POLYCARBONATE")) return "PC";
  return raw.split(/\s+/).slice(-1)[0].slice(0, 10);
}

function displayColorName(hex) {
  const norm = normalizeHex8(hex);
  if (!norm) return "Color";
  const palette = [
    { name: "Orange", hex: "#F5641EFF" },
    { name: "White", hex: "#EBEBE6FF" },
    { name: "Grey", hex: "#69707AFF" },
    { name: "Black", hex: "#000000FF" },
    { name: "Silver", hex: "#A7AEB7FF" },
    { name: "Red", hex: "#E24B4BFF" },
    { name: "Blue", hex: "#4D8FFFFF" },
    { name: "Green", hex: "#5FCF78FF" },
    { name: "Yellow", hex: "#F4C74BFF" },
    { name: "Beige", hex: "#D9C4A2FF" },
    { name: "Brown", hex: "#8D684BFF" },
  ];
  let bestName = palette[0].name;
  let bestScore = Number.POSITIVE_INFINITY;
  palette.forEach((entry) => {
    const score = colorDistance(norm, entry.hex);
    if (score < bestScore) {
      bestScore = score;
      bestName = entry.name;
    }
  });
  return bestName;
}

function compactFilamentLabel(color, type) {
  const colorLabel = displayColorName(color);
  const typeLabel = materialTypeShortLabel(type);
  return [colorLabel, typeLabel].filter(Boolean).join(" ").trim();
}

function formatKeychainAmsMapping(meta) {
  const slots = Array.isArray(meta?.slots) ? meta.slots : [];
  if (!slots.length) return "";
  const parts = slots.map((item) => {
    const slot = item?.slot ? `Slot ${item.slot}` : "Unmapped";
    const trayType = item?.tray_type ? ` · ${item.tray_type}` : "";
    return `${displayColorName(item?.color)} -> ${slot}${trayType}`;
  });
  return `AMS mapping: ${parts.join(", ")}`;
}

function keychainColorRole(hex) {
  const norm = normalizeHex8(hex);
  if (!norm) return "Part";
  const selectedNameColor = normalizeHex8(state.keychainNameColor);
  if (selectedNameColor && colorDistance(norm, selectedNameColor) < 16) return "Name";
  if (colorDistance(norm, "#F5641EFF") < 24) return "Accent";
  if (colorDistance(norm, "#EBEBE6FF") < 20 || colorDistance(norm, "#FFFFFFFF") < 14) return "Logo";
  if (colorDistance(norm, "#1A1A1AFF") < 30 || colorDistance(norm, "#69707AFF") < 28 || colorDistance(norm, "#87909AFF") < 30) return "Body";
  return "Part";
}

function inferredKeychainAmsPlan() {
  if (state.currentModel?.templateKey !== "bridge_keychain") return [];
  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  const parts = Array.isArray(state.currentModel?.previewParts) ? state.currentModel.previewParts : [];
  const uniqueColors = [...new Set(
    parts
      .map((part) => normalizeHex8(part.color))
      .filter(Boolean),
  )];
  if (!uniqueColors.length) return [];

  const roleOrder = { Body: 0, Logo: 1, Name: 2, Accent: 3, Part: 4 };
  const colors = uniqueColors.sort((a, b) => {
    const ra = keychainColorRole(a);
    const rb = keychainColorRole(b);
    return (roleOrder[ra] ?? 99) - (roleOrder[rb] ?? 99);
  });

  const usedSlots = new Set();
  return colors.map((color) => {
    const role = keychainColorRole(color);
    let tray = null;
    if (trays.length) {
      const available = trays.filter((t) => !usedSlots.has(Number(t?.slot || 0)));
      const pool = available.length ? available : trays;
      if (role === "Body") {
        // Match backend: assign the body (largest part) to the darkest loaded AMS slot
        tray = [...pool].sort((a, b) => colorLuminance(normalizeHex8(a?.color)) - colorLuminance(normalizeHex8(b?.color)))[0] || null;
      } else {
        tray = [...pool].sort((a, b) => {
          const distA = colorDistance(normalizeHex8(a?.color), color);
          const distB = colorDistance(normalizeHex8(b?.color), color);
          if (distA !== distB) return distA - distB;
          return Number(a?.slot || 0) - Number(b?.slot || 0);
        })[0] || null;
      }
      if (tray?.slot) usedSlots.add(Number(tray.slot));
    }
    return {
      slot: tray?.slot ? Number(tray.slot) : null,
      tray_color: normalizeHex8(tray?.color),
      tray_type: String(tray?.type || ""),
      color,
      role,
    };
  });
}

function keychainAmsPlan() {
  const direct = Array.isArray(state.estimate?.keychain_multicolor?.slots)
    ? state.estimate.keychain_multicolor.slots
    : (Array.isArray(state.estimate?.slice?.keychain_multicolor?.slots)
      ? state.estimate.slice.keychain_multicolor.slots
      : []);
  if (direct.length) {
    return direct.map((item) => ({
      ...item,
      role: keychainColorRole(item?.color),
    }));
  }
  return inferredKeychainAmsPlan();
}

function setManufactureFeedback(text, tone = "neutral") {
  state.manufactureSummaryOverride = text ? { text, tone } : null;
  renderManufactureSummary();
}

function clearManufactureFeedback() {
  if (state.manufactureBusy) return;
  state.manufactureSummaryOverride = null;
}

function idlePrintActionLabel() {
  const templateLocked = state.currentModel?.templateKey === "bridge_keychain";
  return state.autoStart
    ? "Start print"
    : (templateLocked ? "Prepare 3-color job" : "Prepare job");
}

function defaultJobName() {
  const base =
    state.jobName.trim() ||
    state.currentModel?.name ||
    state.keychainName.trim() ||
    state.prompt.trim() ||
    state.source?.label ||
    "printmind-job";
  return base
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "printmind-job";
}

function synthesizePromptFromLibrary(entry) {
  const title = String(entry.title || "Object");
  const detail = String(entry.detail || "Clean printable design.");
  return `${title}. ${detail}. Premium industrial design object, isolated subject, clean printable silhouette.`;
}

function clearSourcePreviewUrl() {
  if (state.source?.revokeUrl) {
    URL.revokeObjectURL(state.source.previewUrl);
  }
}

function setSource(source) {
  clearSourcePreviewUrl();
  state.source = source;
  renderSourceState();
}

function clearSource() {
  clearSourcePreviewUrl();
  state.source = null;
  renderSourceState();
}

function renderSourceState() {
  if (!state.source || state.mode !== "image") {
    els.sourcePreview.hidden = true;
    if (state.mode === "text") {
      els.sourceSummary.textContent = "Text-only";
    } else if (state.mode === "keychain") {
      els.sourceSummary.textContent = "Bridge keychain";
    } else if (state.mode === "gallery") {
      els.sourceSummary.textContent = "Library guided";
    } else {
      els.sourceSummary.textContent = "No source";
    }
    return;
  }
  els.sourcePreview.hidden = false;
  els.sourcePreviewImage.src = state.source.previewUrl;
  els.sourcePreviewTitle.textContent = state.source.label || "Reference ready";
  els.sourcePreviewMeta.textContent = state.source.meta || "Image prepared";
  els.sourceSummary.textContent = state.source.meta || "Reference ready";
}

function setMode(mode) {
  state.mode = mode;
  els.modeButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.mode === mode);
  });
  Object.entries(els.modePanels).forEach(([key, panel]) => {
    if (!panel) return;
    panel.classList.toggle("is-active", key === mode);
    panel.hidden = key !== mode;
  });
  els.microMode.textContent = mode === "text"
    ? "Text brief"
    : mode === "image"
      ? "Image input"
      : mode === "gallery"
        ? "Inspiration"
        : "Template";
  document.getElementById("presetStrip")?.classList.toggle("is-hidden", mode === "keychain");
  updateGenerateButtonLabel();
  renderSourceState();
  renderStagePresentation();
}

function setPreset(preset) {
  state.preset = preset;
  els.presetButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.preset === preset);
  });
  els.microPreset.textContent = preset.charAt(0).toUpperCase() + preset.slice(1);
}

function renderRecipes() {
  els.recipeRack.innerHTML = "";
  TEXT_RECIPES.forEach((recipe) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "recipe-btn";
    button.innerHTML = `<strong>${recipe.title}</strong><span>${recipe.prompt}</span>`;
    button.addEventListener("click", () => {
      setMode("text");
      state.prompt = recipe.prompt;
      els.promptInput.value = recipe.prompt;
      updatePromptCount();
      setStatus("Recipe loaded into the brief.");
    });
    els.recipeRack.appendChild(button);
  });
}

function renderGalleryFilters() {
  els.galleryFilters.innerHTML = "";
  Object.entries(CATEGORY_LABELS).forEach(([key, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "gallery-filter";
    button.classList.toggle("is-active", state.galleryFilter === key);
    button.textContent = label;
    button.addEventListener("click", () => {
      state.galleryFilter = key;
      renderGalleryFilters();
      renderGallery();
    });
    els.galleryFilters.appendChild(button);
  });
}

function renderGallery() {
  els.galleryRail.innerHTML = "";
  const filtered = state.library.filter((item) => {
    return state.galleryFilter === "all" || item.category === state.galleryFilter;
  });

  if (!filtered.length) {
    const empty = document.createElement("div");
    empty.className = "queue-empty";
    empty.textContent = "No items in this category.";
    els.galleryRail.appendChild(empty);
    return;
  }

  filtered.slice(0, 18).forEach((entry) => {
    const card = document.createElement("article");
    card.className = "gallery-item";

    const image = document.createElement("img");
    image.src = entry.image_url;
    image.alt = entry.title || "Gallery reference";
    card.appendChild(image);

    const body = document.createElement("div");
    body.className = "gallery-copy";

    const title = document.createElement("h3");
    title.textContent = entry.title || "Reference";
    body.appendChild(title);

    const copy = document.createElement("p");
    copy.textContent = entry.detail || "Reference image";
    body.appendChild(copy);

    const actions = document.createElement("div");
    actions.className = "gallery-actions";

    const useImage = document.createElement("button");
    useImage.type = "button";
    useImage.className = "ghost-btn sm-btn";
    useImage.textContent = "Use image";
    useImage.addEventListener("click", () => {
      setMode("image");
      setSource({
        kind: "local-url",
        url: entry.image_url,
        previewUrl: entry.image_url,
        revokeUrl: false,
        label: entry.title || "Gallery reference",
        meta: `${CATEGORY_LABELS[entry.category] || "Gallery"} ref`,
      });
      if (!els.promptInput.value.trim()) {
        state.prompt = synthesizePromptFromLibrary(entry);
        els.promptInput.value = state.prompt;
        updatePromptCount();
      }
      setStatus("Gallery reference loaded.");
    });

    const useBrief = document.createElement("button");
    useBrief.type = "button";
    useBrief.className = "primary-btn sm-btn";
    useBrief.textContent = "Use brief";
    useBrief.addEventListener("click", () => {
      setMode("text");
      const prompt = synthesizePromptFromLibrary(entry);
      state.prompt = prompt;
      els.promptInput.value = prompt;
      updatePromptCount();
      setStatus("Gallery brief loaded.");
    });

    actions.appendChild(useImage);
    actions.appendChild(useBrief);
    body.appendChild(actions);
    card.appendChild(body);
    els.galleryRail.appendChild(card);
  });
}

function updatePromptCount() {
  state.prompt = els.promptInput.value;
  els.charCount.textContent = `${state.prompt.length} / ${PROMPT_MAX}`;
}

function updateKeychainCount() {
  state.keychainName = String(els.keychainNameInput?.value || "").trim();
  if (els.keychainCharCount) {
    els.keychainCharCount.textContent = `${state.keychainName.length} / 21`;
  }
  renderTemplateStage();
  renderStagePresentation();
}

function updateGenerateButtonLabel() {
  if (!els.generateBtn) return;
  els.generateBtn.textContent = state.mode === "keychain" ? "Build keychain" : "Generate model";
}

function renderTemplateFacts() {
  if (!els.templateFacts) return;
  const template = state.templates.find((item) => item.template_key === "bridge_keychain");
  if (!template) return;
  const colors = Array.isArray(template.colors) ? template.colors.length : 3;
  els.templateFacts.innerHTML = `
    <div class="template-fact">
      <span class="micro-label">Template</span>
      <strong>${colors}-color keychain</strong>
    </div>
    <div class="template-fact">
      <span class="micro-label">Front</span>
      <strong>BRIDGE fixed</strong>
    </div>
    <div class="template-fact">
      <span class="micro-label">Back</span>
      <strong>Custom name</strong>
    </div>
    <div class="template-fact">
      <span class="micro-label">Font</span>
      <strong>${template.font_exact ? template.font_family : `${template.font_family} fallback`}</strong>
    </div>
  `;
}

function keychainPreviewName() {
  const placeholder = state.templates.find((item) => item.template_key === "bridge_keychain")?.placeholder_name || "Name";
  return state.currentModel?.templateKey === "bridge_keychain"
    ? (state.currentModel.name || placeholder)
    : (state.keychainName || placeholder);
}

function renderTemplateStage() {
  if (!els.templateStageNote) return;
  const applyTemplateView = (nextView) => {
    viewer.templateView = nextView === "back" ? "back" : "front";
    const name = keychainPreviewName();
    const hasBuiltKeychain = state.currentModel?.templateKey === "bridge_keychain";
    els.templateStageNote.textContent = hasBuiltKeychain
      ? `Keychain view for ${name}. Drag to inspect or flip to the back.`
      : "Build the keychain to inspect the front and back in 3D.";
    els.keychainFrontBtn?.classList.toggle("is-active", viewer.templateView === "front");
    els.keychainBackBtn?.classList.toggle("is-active", viewer.templateView === "back");
    if (!viewer.isTemplateModel || !viewer.mesh || !viewer.templatePivot) return;
    const basePitch = -0.10;
    const baseYaw = 0.18;
    const targetY = viewer.templateView === "back" ? Math.PI + baseYaw : baseYaw;
    viewer.templatePivot.rotation.set(basePitch, targetY, -0.04);
    viewer.controls.target.set(0, 0, 0);
    viewer.controls.update();
  };
  if (els.keychainFrontBtn && !els.keychainFrontBtn.dataset.boundPreview) {
    els.keychainFrontBtn.dataset.boundPreview = "1";
    els.keychainFrontBtn.onclick = () => globalThis.__pmSetKeychainPreviewView?.("front") || applyTemplateView("front");
  }
  if (els.keychainBackBtn && !els.keychainBackBtn.dataset.boundPreview) {
    els.keychainBackBtn.dataset.boundPreview = "1";
    els.keychainBackBtn.onclick = () => globalThis.__pmSetKeychainPreviewView?.("back") || applyTemplateView("back");
  }
  const name = keychainPreviewName();
  const hasBuiltKeychain = state.currentModel?.templateKey === "bridge_keychain";
  const previewReady = hasBuiltKeychain && Boolean(viewer.templatePivot);
  els.templateStageNote.textContent = hasBuiltKeychain
    ? (previewReady
      ? `Keychain view for ${name}. Drag to inspect or flip to the back.`
      : `Preparing keychain preview for ${name}...`)
    : "Build the keychain to inspect the front and back in 3D.";
  els.keychainFrontBtn?.classList.toggle("is-active", viewer.templateView === "front");
  els.keychainBackBtn?.classList.toggle("is-active", viewer.templateView === "back");
  if (els.keychainFrontBtn) els.keychainFrontBtn.disabled = !previewReady;
  if (els.keychainBackBtn) els.keychainBackBtn.disabled = !previewReady;
}

function setKeychainPreviewView(view) {
  viewer.templateView = view === "back" ? "back" : "front";
  const name = keychainPreviewName();
  const hasBuiltKeychain = state.currentModel?.templateKey === "bridge_keychain";
  const previewReady = hasBuiltKeychain && Boolean(viewer.templatePivot);
  if (els.templateStageNote) {
    els.templateStageNote.textContent = hasBuiltKeychain
      ? (previewReady
        ? `Keychain view for ${name}. Drag to inspect or flip to the back.`
        : `Preparing keychain preview for ${name}...`)
      : "Build the keychain to inspect the front and back in 3D.";
  }
  if (els.keychainFrontBtn) {
    els.keychainFrontBtn.classList.toggle("is-active", viewer.templateView === "front");
    els.keychainFrontBtn.disabled = !previewReady;
  }
  if (els.keychainBackBtn) {
    els.keychainBackBtn.classList.toggle("is-active", viewer.templateView === "back");
    els.keychainBackBtn.disabled = !previewReady;
  }
  if (!viewer.isTemplateModel || !viewer.mesh || !viewer.templatePivot) return;
  const basePitch = -0.10;
  const baseYaw = 0.18;
  const targetY = viewer.templateView === "back" ? Math.PI + baseYaw : baseYaw;
  viewer.templatePivot.rotation.set(basePitch, targetY, -0.04);
  viewer.controls.target.set(0, 0, 0);
  viewer.controls.update();
}

globalThis.__pmSetKeychainPreviewView = setKeychainPreviewView;
globalThis.__pmViewer = viewer;

function syncMainViewerSize() {
  if (!viewer.renderer || !viewer.camera || !els.viewer) return;
  const rect = els.viewer.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  viewer.camera.aspect = rect.width / rect.height;
  viewer.camera.updateProjectionMatrix();
  viewer.renderer.setSize(rect.width, rect.height, true);
}

function updateBedCameraFrustum(explicitSpan = null) {
  const camera = bedViewer3D.camera;
  if (!camera || !els.bedCanvasWrap) return;
  const rect = els.bedCanvasWrap.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const span = explicitSpan || bedViewer3D.frameHalfSpan || 140;
  bedViewer3D.frameHalfSpan = span;
  camera.aspect = rect.width / Math.max(rect.height, 1);
  camera.updateProjectionMatrix();
}

function syncBedViewerSize() {
  if (!bedViewer3D.renderer || !bedViewer3D.camera || !els.bedCanvasWrap) return;
  const rect = els.bedCanvasWrap.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  updateBedCameraFrustum();
  bedViewer3D.renderer.setSize(Math.round(rect.width), Math.round(rect.height), false);
  if (bedViewer3D.modelMesh) {
    frameBedCamera(bedViewer3D.modelMesh);
  }
}

function renderBedViewMode() {
  const isFocus = state.bedViewMode !== "full";
  els.bedFocusBtn?.classList.toggle("is-active", isFocus);
  els.bedFullBtn?.classList.toggle("is-active", !isFocus);
  if (els.bedPaneSubtitle) {
    els.bedPaneSubtitle.textContent = isFocus
      ? "Focused 3D bed view · drag to orbit"
      : "Whole-bed 3D view · drag to orbit";
  }
}

function renderPreviewExpansion() {
  document.body.classList.toggle("preview-expanded", state.previewExpanded);
  els.previewStageCard?.classList.toggle("is-expanded", state.previewExpanded);
  if (els.previewOverlayCloseBtn) {
    els.previewOverlayCloseBtn.hidden = !state.previewExpanded;
  }
  if (els.viewerFullscreenBtn) {
    if (!state.currentModel?.stlPath) {
      els.viewerFullscreenBtn.disabled = true;
    } else {
      els.viewerFullscreenBtn.disabled = false;
      els.viewerFullscreenBtn.textContent = state.previewExpanded
        ? "Expanded"
        : (state.previewPane === "plate" ? "Plate Full" : "Expand");
    }
  }
  requestAnimationFrame(() => {
    syncMainViewerSize();
    syncBedViewerSize();
  });
}

function renderPreviewPane() {
  const isPlate = state.previewPane === "plate";
  els.viewerMain?.classList.toggle("is-active", !isPlate);
  els.viewerBedPane?.classList.toggle("is-active", isPlate);
  els.viewer3dBtn?.classList.toggle("is-active", !isPlate);
  els.viewerPlateBtn?.classList.toggle("is-active", isPlate);
  renderBedViewMode();
  renderPreviewExpansion();
}

function setPreviewPane(mode) {
  state.previewPane = mode === "plate" ? "plate" : "3d";
  renderPreviewPane();
}

function setBedViewMode(mode) {
  state.bedViewMode = mode === "full" ? "full" : "focus";
  renderBedViewMode();
  if (bedViewer3D.modelMesh) {
    frameBedCamera(bedViewer3D.modelMesh);
  } else {
    syncBedViewerSize();
  }
}

function toggleViewerFullscreen() {
  if (!state.currentModel?.stlPath) return;
  state.previewExpanded = !state.previewExpanded;
  renderPreviewExpansion();
}

function setSizePreset(sizePreset) {
  state.sizePreset = sizePreset;
  state.targetMaxExtentMm = SIZE_PRESETS[sizePreset];
  renderManufacturingState();
}

function inferSizePreset(targetMm) {
  const mm = Number(targetMm);
  const candidates = Object.entries(SIZE_PRESETS);
  let best = "medium";
  let delta = Infinity;
  candidates.forEach(([key, value]) => {
    const diff = Math.abs(value - mm);
    if (diff < delta) {
      delta = diff;
      best = key;
    }
  });
  return best;
}

function renderManufacturingState() {
  const templateLocked = state.currentModel?.templateKey === "bridge_keychain";
  const slotValue = effectiveAmsSlot();
  if (templateLocked && slotValue && !state.amsSlot) {
    state.amsSlot = slotValue;
  }
  els.intentButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.intent === state.intent);
    button.disabled = false;
  });
  els.supportButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.support === state.supportMode);
    button.disabled = templateLocked;
  });
  els.sizePresetButtons.forEach((button) => {
    button.classList.toggle("is-active", button.dataset.size === state.sizePreset);
    button.disabled = templateLocked;
  });
  els.sizeRange.value = String(state.targetMaxExtentMm);
  const lockedExtent = Math.round(maxModelExtent(state.currentModel?.dimensionsMm) || state.targetMaxExtentMm);
  els.sizeReadout.textContent = templateLocked ? `${lockedExtent} mm` : `${Math.round(state.targetMaxExtentMm)} mm`;
  els.scaleReadout.textContent = templateLocked ? "Locked" : `${computedScalePercent()}%`;
  els.sizeRange.disabled = templateLocked;
  if (els.sizeSettingRow) {
    els.sizeSettingRow.hidden = templateLocked;
  }
  if (els.supportSettingRow) {
    els.supportSettingRow.hidden = templateLocked;
  }
  if (els.templatePrintLockNote) {
    els.templatePrintLockNote.hidden = !templateLocked;
  }
  els.autoStartToggle.checked = state.autoStart;
  els.useAmsToggle.checked = state.useAms;
  els.amsSlotSelect.disabled = !state.useAms;
  if (slotValue) {
    els.amsSlotSelect.value = String(slotValue);
  }
  els.jobNameInput.value = state.jobName;
  els.jobNameInput.placeholder = templateLocked ? `bridge-keychain-${state.currentModel?.name || state.keychainName || "name"}` : "Optional";
  updateReadiness();
  updatePrintActionAvailability();
}

function updateReadiness() {
  if (!state.currentModel?.stlPath) {
    els.microReadiness.textContent = "Awaiting model";
    return;
  }
  if (state.preflight?.can_print === true) {
    els.microReadiness.textContent = "Ready to print";
    return;
  }
  if (state.preflight?.can_print === false) {
    els.microReadiness.textContent = "Preflight blocked";
    return;
  }
  if (state.estimate?.estimated?.available) {
    els.microReadiness.textContent = "Estimated";
    return;
  }
  els.microReadiness.textContent = "Model ready";
}

function renderResultCards() {
  const model = state.currentModel;
  els.resultSeconds.textContent = model ? formatSeconds(model.seconds) : "--";
  els.resultFaces.textContent = model ? Number(model.faces || 0).toLocaleString() : "--";
  els.resultDimensions.textContent = model ? formatDimensions(model.dimensionsMm) : "--";
  els.resultEngine.textContent = model ? formatEngine(model.generationConfig) : "--";
  els.exportMenuBtn.disabled = !model?.stlPath;
  if (!model?.stlPath) {
    els.exportMenu.hidden = true;
  }
  if (els.export3mfBtn) {
    els.export3mfBtn.hidden = !model?.model3mfPath;
  }
  if (model?.templateKey === "bridge_keychain") {
    els.microOutput.textContent = model.name ? `${model.name} keychain` : "Keychain ready";
  } else {
    els.microOutput.textContent = model ? `${Number(model.faces || 0).toLocaleString()} faces` : "No STL yet";
  }
}

function renderPerfCards() {
  const perf = state.lastPerf;
  els.perfTotal.textContent = perf ? `${Number(perf.total_s || 0).toFixed(1)}s` : "--";
  els.perfSampling.textContent = perf ? `${Number(perf.diffusion_sampling_s || 0).toFixed(1)}s` : "--";
  els.perfDecode.textContent = perf ? `${Number(perf.volume_decoding_s || 0).toFixed(1)}s` : "--";
}

function renderProgress(progress) {
  const pg = progress || state.progress;
  if (!pg || !state.isGenerating) {
    els.progressDock.hidden = true;
    return;
  }
  const bars = pg.bars || { prep: 0, diffusion: 0, decode: 0 };
  els.progressDock.hidden = false;
  els.progressStage.textContent = pg.stage_label || "Generating";
  els.progressMessage.textContent = pg.message || "Processing request";
  const prep = Number(bars.prep || 0);
  const diff = Number(bars.diffusion || 0);
  const decode = Number(bars.decode || 0);
  els.progressPrepFill.style.width = `${Math.round(prep * 100)}%`;
  els.progressDiffusionFill.style.width = `${Math.round(diff * 100)}%`;
  els.progressDecodeFill.style.width = `${Math.round(decode * 100)}%`;
  els.progressPrepValue.textContent = formatPercent(prep);
  els.progressDiffusionValue.textContent = formatPercent(diff);
  els.progressDecodeValue.textContent = formatPercent(decode);
}

function renderPrinterSelect() {
  const current = state.selectedPrinter;
  els.printerSelect.innerHTML = "";
  if (!state.printers.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No printers configured";
    els.printerSelect.appendChild(option);
    return;
  }
  state.printers.forEach((printer) => {
    const option = document.createElement("option");
    option.value = printer.name;
    option.textContent = printer.name;
    option.selected = printer.name === current;
    els.printerSelect.appendChild(option);
  });
}

function renderPrinterTimeline() {
  els.printerTimeline.innerHTML = "";
  const timeline = Array.isArray(state.printerStatus?.timeline) ? state.printerStatus.timeline : [];
  if (!timeline.length) {
    const row = document.createElement("div");
    row.className = "timeline-chip";
    row.textContent = "No timeline data.";
    els.printerTimeline.appendChild(row);
    return;
  }

  timeline.forEach((step) => {
    const chip = document.createElement("div");
    const cls = step.state === "active"
      ? "is-active"
      : step.state === "done"
        ? "is-done"
        : step.state === "halted"
          ? "is-halted"
          : "";
    chip.className = `timeline-chip ${cls}`.trim();
    const stateLabel = step.state === "active"
      ? "In progress"
      : step.state === "done"
        ? "Done"
        : step.state === "halted"
          ? "Stopped"
          : "Pending";
    chip.innerHTML = `
      <span class="timeline-marker"></span>
      <div class="timeline-copy">
        <strong>${step.label || step.id || "Step"}</strong>
        <span>${stateLabel}</span>
      </div>
    `;
    els.printerTimeline.appendChild(chip);
  });
}

function renderAmsSlots() {
  const current = String(effectiveAmsSlot() || "");
  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  els.amsSlotSelect.innerHTML = '<option value="">Auto / default</option>';
  trays.forEach((tray) => {
    const option = document.createElement("option");
    option.value = String(tray.slot);
    const type = tray.type ? ` - ${tray.type}` : "";
    option.textContent = `Slot ${tray.slot}${type}`;
    option.selected = option.value === current;
    els.amsSlotSelect.appendChild(option);
  });
}

// When the printer AMS data loads, update keychain colour swatches to reflect actual slot colours.
function updateSwatchesFromAms() {
  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  if (!trays.length) return;

  const hint = document.getElementById("amsSwatchHint");
  const container = document.getElementById("keychainSwatches");
  if (!container) return;

  // Build a colour list from AMS — normalise to #RRGGBBFF (Bambu sends colours without '#')
  const amsColors = trays
    .map((t) => {
      const cssColor = hexToCssColor(t.color);
      if (cssColor === "var(--surface-4)") return null;
      const raw = String(t.color || "").replace("#", "").trim();
      const kcColor = raw.length === 8 ? `#${raw}` : raw.length === 6 ? `#${raw}FF` : cssColor + "FF";
      return { slot: t.slot, color: cssColor, kcColor, label: `Slot ${t.slot}${t.type ? ` · ${t.type}` : ""}` };
    })
    .filter(Boolean);

  // Always keep orange as the first/default swatch
  const swatchColors = [
    { color: "#F5641E", kcColor: "#F5641EFF", label: "Orange (default)" },
    ...amsColors,
  ];

  container.innerHTML = "";
  swatchColors.forEach((item, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "color-swatch" + (idx === 0 ? " is-active" : "");
    btn.dataset.kcColor = item.kcColor;
    btn.style.background = item.color;
    const isLight = /^#[eEfFdDcC]/i.test(item.color);
    if (isLight) btn.style.borderColor = "rgba(0,0,0,0.14)";
    btn.title = item.label;
    btn.addEventListener("click", () => {
      container.querySelectorAll(".color-swatch").forEach((s) => s.classList.remove("is-active"));
      btn.classList.add("is-active");
      state.keychainNameColor = btn.dataset.kcColor;
      renderBedPreview();
    });
    container.appendChild(btn);
  });

  // Keep orange as default; only switch if user hasn't already picked something
  if (state.keychainNameColor === "#F5641EFF" || !state.keychainNameColor) {
    state.keychainNameColor = "#F5641EFF";
  }
  if (hint) hint.textContent = `${amsColors.length} AMS slot${amsColors.length !== 1 ? "s" : ""} synced from printer.`;
}

function renderKeychainSwatches() {
  const container = els.keychainSwatches;
  if (!container) return;

  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  const fallback = [
    { slot: "", kcColor: "#F5641EFF", cssColor: "#F5641E", label: "Orange default" },
    { slot: "", kcColor: "#87909AFF", cssColor: "#87909A", label: "Silver grey" },
    { slot: "", kcColor: "#FFFFFFFF", cssColor: "#FFFFFF", label: "White" },
    { slot: "", kcColor: "#000000FF", cssColor: "#000000", label: "Black" },
  ];

  const choices = trays.length
    ? trays
      .map((tray) => {
        const kcColor = normalizeHex8(tray.color);
        if (!kcColor) return null;
        return {
          slot: String(tray.slot),
          kcColor,
          cssColor: hexToCssColor(kcColor),
          label: `Slot ${tray.slot}${tray.type ? ` · ${tray.type}` : ""}`,
        };
      })
      .filter(Boolean)
      .sort((a, b) => {
        const da = colorDistance(a.kcColor, "#F5641EFF");
        const db = colorDistance(b.kcColor, "#F5641EFF");
        if (da !== db) return da - db;
        return Number(a.slot || 0) - Number(b.slot || 0);
      })
    : fallback;

  state.keychainColorSlots = choices;
  const preferred = choices.find((item) => item.kcColor === state.keychainNameColor)
    || choices.find((item) => item.slot === String(state.amsSlot || ""))
    || choices[0];
  if (preferred) {
    state.keychainNameColor = preferred.kcColor;
    if (preferred.slot) state.amsSlot = preferred.slot;
  }

  container.innerHTML = "";
  choices.forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "color-swatch" + (item.kcColor === state.keychainNameColor ? " is-active" : "");
    btn.dataset.kcColor = item.kcColor;
    btn.dataset.slot = item.slot || "";
    btn.style.background = item.cssColor;
    if (isLightColor(item.kcColor)) {
      btn.style.borderColor = "rgba(0,0,0,0.14)";
    }
    btn.title = item.label;
    btn.addEventListener("click", () => {
      container.querySelectorAll(".color-swatch").forEach((s) => s.classList.remove("is-active"));
      btn.classList.add("is-active");
      state.keychainNameColor = btn.dataset.kcColor;
      state.amsSlot = btn.dataset.slot || "";
      renderManufacturingState();
      renderManufactureSummary();
      renderBedPreview();
    });
    container.appendChild(btn);
  });

  if (els.amsSwatchHint) {
    els.amsSwatchHint.textContent = trays.length
      ? "Colours match live AMS trays. Name defaults to the closest orange slot."
      : "No live AMS tray data. Using default keychain colours.";
  }
}

function renderAmsTrayRail() {
  if (!els.amsTrayRail) return;
  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  const active = Number(state.printerStatus?.ams?.active_slot || 0);
  const selected = state.useAms && state.amsSlot ? Number(state.amsSlot) : 0;
  const keychainPlan = keychainAmsPlan();
  els.amsTrayRail.innerHTML = "";
  if (!trays.length) {
    const empty = document.createElement("div");
    empty.className = "ams-chip ams-chip--empty";
    empty.textContent = "No AMS tray data";
    els.amsTrayRail.appendChild(empty);
    renderKeychainSwatches();
    return;
  }
  trays.forEach((tray) => {
    const chip = document.createElement("div");
    const slot = Number(tray.slot || 0);
    const assignments = keychainPlan.filter((item) => Number(item.slot || 0) === slot);
    const flags = [
      "ams-chip",
      slot === active ? "is-active" : "",
      slot === selected ? "is-selected" : "",
    ].filter(Boolean);
    chip.className = flags.join(" ");
    const spool = document.createElement("div");
    spool.className = "ams-spool";
    spool.style.setProperty("--spool-color", hexToCssColor(tray.color));
    const spoolCore = document.createElement("span");
    spoolCore.className = "ams-spool-core";
    spool.appendChild(spoolCore);
    const copy = document.createElement("div");
    copy.className = "ams-copy";
    const title = document.createElement("strong");
    title.textContent = `Slot ${tray.slot}`;
    const meta = document.createElement("span");
    const metaParts = [];
    if (slot === selected) metaParts.push("Selected");
    if (slot === active) metaParts.push("Active");
    metaParts.push(compactFilamentLabel(tray.color, tray.type) || materialTypeShortLabel(tray.type) || "Filament");
    meta.textContent = metaParts.join(" · ");
    copy.appendChild(title);
    copy.appendChild(meta);
    if (assignments.length) {
      const tags = document.createElement("div");
      tags.className = "ams-tags";
      assignments.forEach((item) => {
        const tag = document.createElement("span");
        tag.className = "ams-tag";
        tag.textContent = `${item.role} · ${displayColorName(item.color)}`;
        tags.appendChild(tag);
      });
      copy.appendChild(tags);
    }
    chip.appendChild(spool);
    chip.appendChild(copy);
    els.amsTrayRail.appendChild(chip);
  });
  renderKeychainSwatches();
}

function renderQueue() {
  els.queueList.innerHTML = "";
  const items = Array.isArray(state.queue?.items) ? state.queue.items : [];
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "queue-empty";
    empty.textContent = "Queue is empty.";
    els.queueList.appendChild(empty);
    return;
  }

  items.slice(0, 6).forEach((item) => {
    const row = document.createElement("div");
    row.className = "queue-item";
    const req = item.request || {};
    row.innerHTML = `
      <div class="queue-head">
        <span>${String(item.status || "queued").toUpperCase()}</span>
        <span>${req.printer_name || "printer?"}</span>
      </div>
      <div>${req.job_name || "untitled job"}</div>
      <div class="queue-meta">${req.mode || "decorative"} | ${req.ams_slot ? `slot ${req.ams_slot}` : "auto slot"}</div>
    `;
    els.queueList.appendChild(row);
  });
}

function renderControlCenter() {
  const health = state.health;
  const healthText = els.healthPill.querySelector("span:last-child");
  const healthDot = els.healthPill.querySelector(".pill-dot");

  if (health) {
    if (health.loaded === false) {
      if (healthText) healthText.textContent = "Model service standby";
      if (healthDot) healthDot.style.background = "var(--text-3)";
    } else {
      const device = String(health.device || "unknown");
      const vram = Number(health.gpu_vram_gb || 0).toFixed(1);
      const strict = health.strict_gpu_mode ? "strict" : "adaptive";
      if (healthText) healthText.textContent = `${device} · ${vram} GB · ${strict}`;
      if (healthDot) healthDot.style.background = "var(--good)";
    }
  } else {
    if (healthText) healthText.textContent = "Checking engine";
    if (healthDot) healthDot.style.background = "var(--warn)";
  }

  const queueCount = Array.isArray(state.queue?.items) ? state.queue.items.length : 0;
  const queueText = els.queuePill.querySelector("span:last-child");
  const queueDot = els.queuePill.querySelector(".pill-dot");
  if (queueText) queueText.textContent = queueCount ? `Queue: ${queueCount}` : "Queue idle";
  if (queueDot) queueDot.style.background = queueCount ? "var(--orange)" : "var(--text-3)";

  renderPrinterSelect();
  renderAmsSlots();
  renderAmsTrayRail();

  if (!state.selectedPrinter) {
    els.printerStage.textContent = "Unknown";
    if (els.printerJob) els.printerJob.textContent = "--";
    els.printerProgress.textContent = "0%";
    els.printerTemps.textContent = "-- / --";
    els.printerRemaining.textContent = "--";
    els.printerHint.textContent = state.printerStatusError || "No printer selected.";
    renderPrinterTimeline();
    renderQueue();
    updatePrintActionAvailability();
    return;
  }

  if (!state.printerStatus) {
    els.printerStage.textContent = "Unavailable";
    if (els.printerJob) els.printerJob.textContent = "--";
    els.printerProgress.textContent = "0%";
    els.printerTemps.textContent = "-- / --";
    els.printerRemaining.textContent = "--";
    els.printerHint.textContent = state.printerStatusError || "Waiting for printer telemetry.";
    renderPrinterTimeline();
    renderQueue();
    updatePrintActionAvailability();
    return;
  }

  const st = state.printerStatus;
  const printerState = String(st.gcode_state || "").toUpperCase();
  const hasLiveJob = isPrinterStateLive(printerState);
  const hasInterruptedJob = printerState === "FAILED" || printerState === "PAUSE";
  els.printerStage.textContent = st.stage_label || st.gcode_state || "Unknown";
  if (els.printerJob) {
    els.printerJob.textContent = hasLiveJob || hasInterruptedJob
      ? (st.job_name || st.subtask_name || "--")
      : "--";
  }
  els.printerProgress.textContent = `${Number(st.percent || 0)}%`;
  const nozzleTemp = Number(st.nozzle_temper ?? 0);
  const bedTemp = Number(st.bed_temper ?? 0);
  const nozzleText = Number.isFinite(nozzleTemp) && nozzleTemp > 0 ? `${Math.round(nozzleTemp)}C` : "--";
  const bedText = Number.isFinite(bedTemp) && bedTemp > 0 ? `${Math.round(bedTemp)}C` : "--";
  els.printerTemps.textContent = `${nozzleText} / ${bedText}`;
  els.printerRemaining.textContent = formatMinutes(st.remaining_minutes);
  if (hasLiveJob && st.stage_id === "calibration") {
    els.printerHint.textContent = "Startup calibration is still running before first layer. This can take a few minutes on the X1C.";
  } else if (hasLiveJob && st.job_name) {
    els.printerHint.textContent = `${st.stage_label || "Printing"} · ${st.job_name}`;
  } else if (printerState === "FAILED") {
    els.printerHint.textContent = st.job_name
      ? `Last job stopped: ${st.job_name}`
      : "Last job stopped or was interrupted.";
  } else if (printerState === "PAUSE") {
    els.printerHint.textContent = st.job_name
      ? `Paused: ${st.job_name}`
      : "Printer is paused.";
  } else if (st.error_hint) {
    els.printerHint.textContent = st.error_hint;
  } else {
    els.printerHint.textContent = "Printer online.";
  }
  renderPrinterTimeline();
  renderQueue();
  updatePrintActionAvailability();
}

function renderManufactureSummary() {
  const override = state.manufactureSummaryOverride;
  if (override?.text) {
    els.manufactureSummary.dataset.tone = override.tone || "neutral";
    els.manufactureSummary.textContent = override.text;
    return;
  }

  els.manufactureSummary.dataset.tone = "neutral";
  if (!state.currentModel?.stlPath) {
    els.manufactureSummary.textContent = "No estimate yet. Generate a model first.";
    return;
  }

  if (state.preflight) {
    if (state.preflight.can_print) {
      els.manufactureSummary.textContent = "Preflight passed.\nMachine and model are ready to print.";
      return;
    }
    const issues = Array.isArray(state.preflight.issues) ? state.preflight.issues : [];
    const lines = issues.length
      ? issues.map((issue) => `${issue.severity || "issue"}: ${issue.message || "Unknown issue"}`)
      : ["Preflight blocked the print."];
    els.manufactureSummary.textContent = lines.join("\n");
    return;
  }

  const estimated = state.estimate?.estimated;
  if (state.currentModel?.templateKey === "bridge_keychain" && !estimated?.available) {
    const plan = keychainAmsPlan();
    const planText = plan.length
      ? `Filaments: ${plan.map((item) => `${item.role} -> ${item.slot ? `Slot ${item.slot}` : displayColorName(item.color)}`).join(", ")}`
      : `Name slot: ${selectedTrayLabel()}`;
    els.manufactureSummary.textContent =
      "Bridge keychain template loaded.\n" +
      "The 3-color geometry is fixed by the template.\n" +
      `Custom name: ${state.currentModel.name || "--"}\n` +
      `Colors: Black body · Orange accent + name · White logo\n` +
      planText;
    return;
  }
  if (estimated?.available) {
    const total = estimated.time_text_total || formatMinutes(estimated.minutes_total);
    const weight = estimated.filament_weight_g != null ? `${Number(estimated.filament_weight_g).toFixed(2)} g` : "n/a";
    const infill = estimated.infill_percent != null ? `${estimated.infill_percent}%` : "n/a";
    const scaleText = state.currentModel?.templateKey === "bridge_keychain" ? "Locked by template" : `${computedScalePercent()}%`;
    const plan = keychainAmsPlan();
    els.manufactureSummary.textContent =
      `Estimated: ${total}\n` +
      `Filament: ${weight}\n` +
      `Infill: ${infill}\n` +
      `Scale: ${scaleText}\n` +
      (state.currentModel?.templateKey === "bridge_keychain" && plan.length
        ? `Filaments: ${plan.map((item) => `${item.role} -> Slot ${item.slot || "?"}`).join(", ")}`
        : `AMS: ${selectedTrayLabel()}`);
    return;
  }

  els.manufactureSummary.textContent = "Model ready. Run estimate, preflight, queue, or print.";
}

function updatePrintActionAvailability() {
  const readyForOps = Boolean(state.currentModel?.stlPath && state.selectedPrinter);
  const busy = Boolean(state.manufactureBusy);
  els.estimateBtn.disabled = !readyForOps || busy;
  els.preflightBtn.disabled = !readyForOps || busy;
  els.queueBtn.disabled = !readyForOps || busy;
  els.printBtn.disabled = !readyForOps || busy;
  els.estimateBtn.textContent = state.manufactureBusy === "estimate" ? "Estimating..." : "Estimate";
  els.preflightBtn.textContent = state.manufactureBusy === "preflight" ? "Checking..." : "Preflight";
  els.queueBtn.textContent = state.manufactureBusy === "queue" ? "Queueing..." : "Queue";
  const idlePrintLabel = idlePrintActionLabel();
  els.printBtn.textContent = state.manufactureBusy === "print"
    ? (state.autoStart ? "Starting..." : "Preparing...")
    : idlePrintLabel;
}

// ── KEY FIX: manage viewer-empty visibility during generation ──────────
function setViewerEmptyVisible(visible) {
  if (visible) {
    els.viewerEmpty.style.display = "";
  } else {
    els.viewerEmpty.style.display = "none";
  }
}

function renderStagePresentation() {
  const showTemplateControls = Boolean(
    !state.isGenerating &&
    (state.mode === "keychain" || state.currentModel?.templateKey === "bridge_keychain")
  );

  if (els.templateStage) {
    els.templateStage.hidden = !showTemplateControls;
  }
  if (els.viewer) {
    els.viewer.hidden = false;
  }

  if (showTemplateControls) {
    renderTemplateStage();
  }

  if (state.isGenerating) {
    setViewerEmptyVisible(false);
    return;
  }

  setViewerEmptyVisible(!state.currentModel?.stlPath);
}

function setGeneratingUi(isGenerating) {
  state.isGenerating = isGenerating;
  els.generateBtn.disabled = isGenerating;
  els.cancelBtn.disabled = !isGenerating;
  if (!isGenerating) {
    renderProgress(null);
  }
  renderStagePresentation();
}

function buildPrintPayload() {
  if (!state.currentModel?.stlPath) {
    throw new Error("Generate a model first.");
  }
  if (!state.selectedPrinter) {
    throw new Error("Select a printer first.");
  }
  const templateLocked = state.currentModel?.templateKey === "bridge_keychain";
  const intent = INTENT_PRESETS[state.intent] || INTENT_PRESETS.balanced;
  const amsSlot = effectiveAmsSlot();
  return {
    stl_path: state.currentModel.stlPath,
    model_3mf_path: state.currentModel.model3mfPath || null,
    printer_name: state.selectedPrinter,
    auto_route: false,
    mode: intent.mode,
    auto_start: Boolean(state.autoStart),
    skip_preflight: false,
    job_name: templateLocked
      ? (`bridge-keychain-${state.currentModel?.name || state.keychainName || "name"}`.slice(0, 48))
      : (state.jobName.trim() || defaultJobName()),
    use_ams: Boolean(state.useAms),
    ams_slot: state.useAms && amsSlot ? Number(amsSlot) : null,
    bed_leveling: true,
    flow_cali: !templateLocked,
    vibration_cali: !templateLocked,
    layer_inspect: false,
    timelapse: false,
    bed_type: "Textured PEI Plate",
    nozzle_mm: 0.4,
    nozzle_type: "hardened_steel",
    infill_percent: intent.infillPercent,
    scale_percent: templateLocked ? null : computedScalePercent(),
    target_max_extent_mm: templateLocked ? null : Number(state.targetMaxExtentMm),
    size_preset: templateLocked ? null : state.sizePreset,
    orientation_mode: "upright_auto",
    support_mode: state.supportMode,
    support_enabled: state.supportMode === "auto" ? null : state.supportMode === "on",
    support_type: "tree(auto)",
    support_on_build_plate_only: false,
  };
}

function findTrayBySlot(slot) {
  const slotText = String(slot || "");
  if (!slotText) return null;
  const trays = Array.isArray(state.printerStatus?.ams?.trays) ? state.printerStatus.ams.trays : [];
  return trays.find((item) => String(item.slot) === slotText) || null;
}

function buildReviewItem(label, value) {
  const item = document.createElement("div");
  item.className = "review-item";
  const itemLabel = document.createElement("span");
  itemLabel.className = "review-item-label";
  itemLabel.textContent = label;
  const itemValue = document.createElement("span");
  itemValue.className = "review-item-value";
  itemValue.textContent = value;
  item.appendChild(itemLabel);
  item.appendChild(itemValue);
  return item;
}

function captureCanvasSnapshot(sourceCanvas) {
  if (!sourceCanvas || !sourceCanvas.width || !sourceCanvas.height) return "";
  const targetWidth = Math.min(sourceCanvas.width, 1200);
  const scale = targetWidth / sourceCanvas.width;
  const out = document.createElement("canvas");
  out.width = Math.max(1, Math.round(sourceCanvas.width * scale));
  out.height = Math.max(1, Math.round(sourceCanvas.height * scale));
  const ctx = out.getContext("2d");
  if (!ctx) return "";
  ctx.drawImage(sourceCanvas, 0, 0, out.width, out.height);
  return out.toDataURL("image/jpeg", 0.92);
}

function currentReviewSnapshotSize() {
  const bedRect = els.bedCanvasWrap?.getBoundingClientRect();
  const viewerRect = els.viewerFrame?.getBoundingClientRect();
  const rect = (bedRect?.width && bedRect?.height) ? bedRect : viewerRect;
  const width = Math.max(720, Math.round(rect?.width || 720));
  const height = Math.max(480, Math.round(rect?.height || 540));
  return { width, height };
}

function buildBedReviewCamera(width, height) {
  const sourceCamera = bedViewer3D.camera;
  if (!sourceCamera) return null;
  const snapshotCamera = sourceCamera.clone();
  snapshotCamera.aspect = width / Math.max(height, 1);
  if (bedViewer3D.modelMesh) {
    bedViewer3D.modelMesh.updateWorldMatrix(true, true);
    const box = new THREE.Box3().setFromObject(bedViewer3D.modelMesh);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const heightMm = Math.max(size.y, 6);
    const span = BED_MM * 0.95;
    const fov = THREE.MathUtils.degToRad(snapshotCamera.fov || 34);
    const distance = Math.max(90, (span * 0.78) / Math.tan(fov / 2));
    const viewDir = new THREE.Vector3(1.0, 0.92, 1.06).normalize();
    const target = new THREE.Vector3(center.x, Math.max(0, box.min.y) + (heightMm * 0.1), center.z);
    snapshotCamera.position.copy(target.clone().addScaledVector(viewDir, distance));
    snapshotCamera.near = 2;
    snapshotCamera.far = Math.max(1800, distance * 8);
    snapshotCamera.lookAt(target);
  }
  snapshotCamera.updateProjectionMatrix();
  snapshotCamera.updateMatrixWorld(true);
  return snapshotCamera;
}

function renderSceneSnapshot(scene, sourceCamera, sourceRenderer, width, height) {
  if (!scene || !sourceCamera || width < 2 || height < 2) return "";
  let snapshotRenderer = null;
  try {
    snapshotRenderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      preserveDrawingBuffer: true,
      premultipliedAlpha: false,
    });
    snapshotRenderer.setPixelRatio(1);
    snapshotRenderer.setSize(width, height, false);
    snapshotRenderer.outputColorSpace = sourceRenderer?.outputColorSpace || THREE.SRGBColorSpace;
    snapshotRenderer.toneMapping = sourceRenderer?.toneMapping || THREE.NoToneMapping;
    snapshotRenderer.toneMappingExposure = sourceRenderer?.toneMappingExposure ?? 1;
    snapshotRenderer.shadowMap.enabled = Boolean(sourceRenderer?.shadowMap?.enabled);
    snapshotRenderer.shadowMap.type = sourceRenderer?.shadowMap?.type || THREE.PCFSoftShadowMap;
    const snapshotCamera = sourceCamera.clone();
    snapshotCamera.aspect = width / Math.max(height, 1);
    snapshotCamera.updateProjectionMatrix();
    scene.updateMatrixWorld(true);
    snapshotCamera.updateMatrixWorld(true);
    snapshotRenderer.render(scene, snapshotCamera);
    return snapshotRenderer.domElement.toDataURL("image/png");
  } catch (_) {
    return "";
  } finally {
    if (snapshotRenderer) {
      snapshotRenderer.dispose();
      snapshotRenderer.forceContextLoss?.();
      snapshotRenderer.domElement.width = 0;
      snapshotRenderer.domElement.height = 0;
    }
  }
}

function getPrintReviewSnapshot() {
  const { width, height } = currentReviewSnapshotSize();
  if (els.printReviewPreviewFrame) {
    els.printReviewPreviewFrame.style.aspectRatio = `${width} / ${height}`;
  }

  const renderedBed = renderSceneSnapshot(
    bedViewer3D.scene,
    buildBedReviewCamera(width, height),
    bedViewer3D.renderer,
    width,
    height,
  );
  if (renderedBed) return renderedBed;

  const renderedViewer = renderSceneSnapshot(
    viewer.scene,
    viewer.camera,
    viewer.renderer,
    width,
    height,
  );
  if (renderedViewer) return renderedViewer;

  const canvases = [els.bedPreviewCanvas, bedViewer3D.renderer?.domElement || null, viewer.renderer?.domElement || null].filter(Boolean);
  for (const canvas of canvases) {
    const snapshot = captureCanvasSnapshot(canvas);
    if (snapshot) {
      return snapshot;
    }
  }
  return "";
}

function printReviewFilaments(payload) {
  const isKeychain = state.currentModel?.templateKey === "bridge_keychain";
  if (isKeychain) {
    const livePlan = inferredKeychainAmsPlan();
    const plan = livePlan.length ? livePlan : keychainAmsPlan();
    if (plan.length) {
      return plan.map((item) => {
        const tray = findTrayBySlot(item.slot);
        const color = normalizeHex8(item.tray_color) || normalizeHex8(tray?.color) || normalizeHex8(item.color) || "#F5641EFF";
        const type = item.tray_type || tray?.type || "";
        const slotLabel = item.slot ? `Slot ${item.slot}` : (payload.use_ams ? "Auto AMS" : "Manual spool");
        return {
          role: item.role || "Part",
          color,
          detail: [compactFilamentLabel(color, type) || displayColorName(color), slotLabel].filter(Boolean).join(" - "),
        };
      });
    }

    const colors = [...new Set(
      (Array.isArray(state.currentModel?.previewParts) ? state.currentModel.previewParts : [])
        .map((part) => normalizeHex8(part.color))
        .filter(Boolean),
    )];
    return colors.map((color) => ({
      role: keychainColorRole(color),
      color,
      detail: `${displayColorName(color)} - ${payload.use_ams ? "AMS auto match" : "Manual spool"}`,
    }));
  }

  const tray = findTrayBySlot(payload.ams_slot);
  const color = normalizeHex8(tray?.color) || "#F5641EFF";
  const detailParts = [];
  const label = compactFilamentLabel(color, tray?.type);
  if (label) detailParts.push(label);
  detailParts.push(payload.use_ams ? (payload.ams_slot ? `Slot ${payload.ams_slot}` : "Auto AMS") : "Manual spool");
  return [{
    role: "Material",
    color,
    detail: detailParts.join(" - "),
  }];
}

function setPrintReviewSending(isSending) {
  state.printReviewSending = Boolean(isSending);
  if (els.printReviewConfirmBtn) {
    els.printReviewConfirmBtn.disabled = state.printReviewSending;
    els.printReviewConfirmBtn.textContent = state.printReviewSending
      ? (state.autoStart ? "Starting..." : "Preparing...")
      : idlePrintActionLabel();
  }
  if (els.printReviewBackBtn) {
    els.printReviewBackBtn.disabled = state.printReviewSending;
  }
  if (els.printReviewCloseBtn) {
    els.printReviewCloseBtn.disabled = state.printReviewSending;
  }
}

function setPrintReviewOpen(open) {
  state.printReviewOpen = Boolean(open);
  if (els.printReviewOverlay) {
    els.printReviewOverlay.hidden = !state.printReviewOpen;
  }
  document.body.style.overflow = state.printReviewOpen ? "hidden" : "";
  if (!state.printReviewOpen) {
    setPrintReviewSending(false);
  }
}

function renderPrintReview() {
  const payload = buildPrintPayload();
  const isKeychain = state.currentModel?.templateKey === "bridge_keychain";
  const modelName = isKeychain
    ? `Bridge keychain - ${state.currentModel?.name || state.keychainName || "Name"}`
    : (state.currentModel?.name || "Generated model");
  const preflightLabel = state.preflight
    ? (state.preflight.can_print ? "Passed" : "Blocked")
    : "Not run yet";
  const gridItems = [
    ["Printer", payload.printer_name],
    ["Job", payload.job_name],
    ["Model", modelName],
    ["Dispatch", payload.auto_start ? "Start after upload" : "Prepare only"],
    ["AMS", payload.use_ams ? "Enabled" : "Disabled"],
    ["Preflight", preflightLabel],
    ["Bed / nozzle", `${payload.bed_type} - ${payload.nozzle_mm} mm`],
  ];

  if (isKeychain) {
    gridItems.splice(3, 0, ["Name", state.currentModel?.name || state.keychainName || "--"]);
    gridItems.push(["Colors", "Black · Orange · White"]);
  } else {
    gridItems.splice(3, 0, ["Scale", `${computedScalePercent()}%`]);
    gridItems.push(["Support", state.supportMode === "auto" ? "Auto tree" : state.supportMode === "on" ? "On" : "Off"]);
    gridItems.push(["Size", `${Math.round(state.targetMaxExtentMm)} mm max`]);
  }

  els.printReviewTitle.textContent = isKeychain ? "Review bridge keychain print." : "Review print job.";
  els.printReviewLead.textContent = isKeychain
    ? `Final check for ${state.currentModel?.name || "your keychain"} before ${payload.auto_start ? "starting the printer" : "preparing the 3-color job"}.`
    : `Final check before ${payload.auto_start ? "starting the printer" : "preparing the job"}.`;
  els.printReviewGrid.innerHTML = "";
  gridItems.forEach(([label, value]) => {
    els.printReviewGrid.appendChild(buildReviewItem(label, value));
  });

  const snapshot = getPrintReviewSnapshot();
  if (snapshot) {
    els.printReviewPreviewImage.src = snapshot;
    els.printReviewPreviewImage.hidden = false;
    els.printReviewPreviewFallback.hidden = true;
  } else {
    els.printReviewPreviewImage.removeAttribute("src");
    els.printReviewPreviewImage.hidden = true;
    els.printReviewPreviewFallback.hidden = false;
  }
  els.printReviewPreviewCaption.textContent = isKeychain ? "Prepared 3D plate view" : "Prepared bed view";

  const filaments = printReviewFilaments(payload);
  els.printReviewFilaments.innerHTML = "";
  filaments.forEach((item) => {
    const row = document.createElement("div");
    row.className = "review-filament";
    const swatch = document.createElement("span");
    swatch.className = "review-filament-swatch";
    swatch.style.background = hexToCssColor(item.color);
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.role;
    const detail = document.createElement("span");
    detail.textContent = item.detail;
    copy.appendChild(title);
    copy.appendChild(detail);
    row.appendChild(swatch);
    row.appendChild(copy);
    els.printReviewFilaments.appendChild(row);
  });
  els.printReviewFilamentNote.textContent = isKeychain
    ? "Read-only mapping for body, logo, and name"
    : "Current filament route";

  const noteLines = [
    payload.auto_start
      ? "This will validate, slice, upload, and then start the printer if the job passes."
      : "This will validate, slice, and upload only. The printer will stay idle until you start the job.",
  ];
  if (isKeychain) {
    noteLines.push("Name color stays controlled from the first keychain panel. This review step is view-only.");
  }
  if (state.preflight && state.preflight.can_print === false) {
    noteLines.unshift("Last preflight reported a blocker. Review that before sending this job.");
  }
  els.printReviewNote.textContent = noteLines.join("\n");
  setPrintReviewSending(false);
}

function closePrintReview(force = false) {
  if (state.printReviewSending && !force) return;
  setPrintReviewOpen(false);
}

function openPrintReview() {
  try {
    renderPrintReview();
    setPrintReviewOpen(true);
  } catch (error) {
    showToast(error.message, 3600);
  }
}

function toggleExportMenu(forceOpen = null) {
  if (!state.currentModel?.stlPath) return;
  const shouldOpen = forceOpen == null ? els.exportMenu.hidden : Boolean(forceOpen);
  els.exportMenu.hidden = !shouldOpen;
}

function downloadModel(format) {
  if (!state.currentModel?.stlPath) return;
  const modelPath = format === "3mf" ? state.currentModel.model3mfPath : state.currentModel.stlPath;
  if (!modelPath) return;
  const href = `/api/model?path=${encodeURIComponent(modelPath)}&format=${encodeURIComponent(format)}`;
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.target = "_blank";
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  toggleExportMenu(false);
}

function startProgressPolling(requestId) {
  stopProgressPolling();
  state.requestId = requestId;
  state.progress = {
    stage_label: "Queued",
    message: "Job accepted",
    bars: { prep: 0, diffusion: 0, decode: 0 },
  };
  renderProgress(state.progress);
  state.progressTimer = setInterval(async () => {
    try {
      const progress = await fetchJson(`/api/generation_status?request_id=${encodeURIComponent(requestId)}`);
      state.progress = progress;
      renderProgress(progress);
      if (progress.status === "error") {
        stopProgressPolling();
        setGeneratingUi(false);
        setStatus(progress.error || "Generation failed.");
      } else if (progress.status === "cancelled") {
        stopProgressPolling();
        setGeneratingUi(false);
        setStatus("Generation cancelled.");
      }
    } catch (_) {
      // Keep polling quiet while the generate request is active.
    }
  }, PROGRESS_INTERVAL_MS);
}

function stopProgressPolling() {
  clearInterval(state.progressTimer);
  state.progressTimer = null;
}

async function generateFromText(prompt, requestId) {
  return fetchJson("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      quality_preset: state.preset,
      request_id: requestId,
    }),
    signal: state.abortCtrl.signal,
  });
}

async function generateKeychain(name) {
  return fetchJson("/api/templates/keychain/build", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, name_color: state.keychainNameColor || "#F5641EFF" }),
  });
}

async function generateFromImageSource(source, requestId) {
  if (source.kind === "file") {
    return fetchJson(
      `/api/generate_image_upload?quality_preset=${encodeURIComponent(state.preset)}&request_id=${encodeURIComponent(requestId)}`,
      {
        method: "POST",
        headers: { "Content-Type": source.file.type || "application/octet-stream" },
        body: source.file,
        signal: state.abortCtrl.signal,
      },
    );
  }

  if (source.kind === "local-url") {
    const res = await fetch(source.url, { signal: state.abortCtrl.signal });
    if (!res.ok) {
      throw new Error(`Failed to load local image (${res.status})`);
    }
    const blob = await res.blob();
    return fetchJson(
      `/api/generate_image_upload?quality_preset=${encodeURIComponent(state.preset)}&request_id=${encodeURIComponent(requestId)}`,
      {
        method: "POST",
        headers: { "Content-Type": blob.type || "application/octet-stream" },
        body: blob,
        signal: state.abortCtrl.signal,
      },
    );
  }

  return fetchJson("/api/generate_image_url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      image_url: source.url,
      quality_preset: state.preset,
      request_id: requestId,
    }),
    signal: state.abortCtrl.signal,
  });
}

function applyGenerationResult(data) {
  closePrintReview(true);
  state.currentModel = {
    stlUrl: data.stl_url,
    stlPath: data.stl_path,
    model3mfUrl: data.model_3mf_url || null,
    model3mfPath: data.model_3mf_path || null,
    previewParts: Array.isArray(data.preview_parts) ? data.preview_parts : [],
    seconds: Number(data.seconds || 0),
    faces: Number(data.faces || 0),
    dimensionsMm: normalizeDimensions(data.dimensions_mm),
    generationConfig: data.generation_config || null,
    templateKey: data.template_key || null,
    name: data.name || null,
  };
  state.estimate = null;
  state.preflight = null;
  state.manufactureBusy = "";
  state.manufactureSummaryOverride = null;
  state.lastPerf = data.perf || null;
  if (state.currentModel.templateKey === "bridge_keychain") {
    state.jobName = state.currentModel.name || "";
    state.bedViewMode = "focus";
    viewer.templateView = "front";
    if (!state.amsSlot) {
      state.amsSlot = effectiveAmsSlot();
    }
  }
  renderResultCards();
  renderPerfCards();
  renderManufacturingState();
  renderManufactureSummary();
  renderBedPreview();
  setPreviewPane("3d");
  if (Array.isArray(data.preview_parts) && data.preview_parts.length) {
    loadPreviewPartsIntoViewer(data.preview_parts, { templateKey: data.template_key || null });
    loadPreviewPartsIntoBedViewer(data.preview_parts);
  } else {
    loadStlIntoViewer(data.stl_url, { templateKey: data.template_key || null });
    loadStlIntoBedViewer(data.stl_url);
  }
  if (data.template_key === "bridge_keychain") {
    els.viewerTitle.textContent = data.name ? `Bridge keychain: ${data.name}` : "Bridge keychain";
    setStatus(`Keychain ready for ${data.name || "name"}.`);
    showToast("Keychain ready");
  } else {
    els.viewerTitle.textContent = data.source_type
      ? `Model from ${data.source_type}`
      : "Model from text brief";
    setStatus(`Model ready in ${Number(data.seconds || 0).toFixed(1)}s.`);
    showToast("Generation complete");
  }
  renderStagePresentation();
}

async function generateCurrentMode() {
  if (state.isGenerating) return;
  try {
    state.abortCtrl = new AbortController();
    setGeneratingUi(true);
    let response;
    if (state.mode === "text") {
      const requestId = makeRequestId();
      startProgressPolling(requestId);
      setStatus(`Generating with ${state.preset} preset...`);
      const prompt = els.promptInput.value.trim();
      if (!prompt) {
        throw new Error("Enter a prompt first.");
      }
      response = await generateFromText(prompt, requestId);
    } else if (state.mode === "keychain") {
      stopProgressPolling();
      updateKeychainCount();
      if (!state.keychainName) {
        throw new Error("Enter a name first.");
      }
      setStatus("Building keychain from the production template...");
      response = await generateKeychain(state.keychainName);
    } else {
      const requestId = makeRequestId();
      startProgressPolling(requestId);
      setStatus(`Generating with ${state.preset} preset...`);
      if (!state.source) {
        throw new Error("Select or capture an image first.");
      }
      response = await generateFromImageSource(state.source, requestId);
    }

    stopProgressPolling();
    state.progress = null;
    state.requestId = null;
    setGeneratingUi(false);
    applyGenerationResult(response);
  } catch (error) {
    stopProgressPolling();
    state.requestId = null;
    setGeneratingUi(false);
    if (error?.name === "AbortError") {
      setStatus("Generation cancelled.");
      return;
    }
    setStatus(`Error: ${error.message}`);
    showToast(error.message, 3600);
  }
}

async function cancelGeneration() {
  if (!state.isGenerating || !state.requestId) return;
  try {
    await fetchJson("/api/generation_cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: state.requestId }),
    });
  } catch (_) {
    // Ignore cancel races.
  }
  state.abortCtrl?.abort();
  stopProgressPolling();
  state.requestId = null;
  setGeneratingUi(false);
  setStatus("Generation cancelled.");
}

async function refreshControlCenter() {
  const query = state.selectedPrinter ? `?printer_name=${encodeURIComponent(state.selectedPrinter)}` : "";
  const data = await fetchJson(`/api/control_center${query}`);
  state.health = data.health || null;
  state.printers = Array.isArray(data.printers) ? data.printers : [];

  const printerNames = new Set(state.printers.map((printer) => printer.name));
  if (!state.selectedPrinter || !printerNames.has(state.selectedPrinter)) {
    state.selectedPrinter = data.selected_printer || state.printers[0]?.name || "";
  }

  state.printerStatus = data.printer_status || null;
  state.printerStatusError = data.printer_status_error || null;
  state.queue = data.queue || null;
  renderControlCenter();
}

async function refreshControlCenterSafe() {
  try {
    await refreshControlCenter();
  } catch (error) {
    const healthText = els.healthPill.querySelector("span:last-child");
    if (healthText) healthText.textContent = "Model service offline";
    els.printerHint.textContent = error.message;
  }
}

async function postPrinterCommand(url) {
  if (!state.selectedPrinter) {
    throw new Error("Select a printer first.");
  }
  return fetchJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ printer_name: state.selectedPrinter }),
  });
}

async function runEstimate() {
  state.manufactureBusy = "estimate";
  setManufactureFeedback(
    `Estimating print on ${state.selectedPrinter}...\n` +
    "The slicer is checking time, material use, and printer fit.",
    "busy",
  );
  renderManufacturingState();
  try {
    const payload = buildPrintPayload();
    state.preflight = null;
    const result = await fetchJson("/api/slice_estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.estimate = result;
    state.manufactureBusy = "";
    state.manufactureSummaryOverride = null;
    renderManufactureSummary();
    renderManufacturingState();
    showToast("Estimate ready");
  } catch (error) {
    state.manufactureBusy = "";
    setManufactureFeedback(error.message, "error");
    renderManufacturingState();
    showToast(error.message, 3600);
  }
}

async function runPreflight() {
  state.manufactureBusy = "preflight";
  setManufactureFeedback(
    `Running preflight for ${state.selectedPrinter}...\n` +
    "Checking printer state, nozzle match, build fit, and AMS readiness.",
    "busy",
  );
  renderManufacturingState();
  try {
    const payload = buildPrintPayload();
    const result = await fetchJson("/api/preflight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.preflight = result;
    state.manufactureBusy = "";
    state.manufactureSummaryOverride = null;
    renderManufactureSummary();
    renderManufacturingState();
    showToast(result.can_print ? "Preflight passed" : "Preflight blocked");
  } catch (error) {
    state.manufactureBusy = "";
    setManufactureFeedback(error.message, "error");
    renderManufacturingState();
    showToast(error.message, 3600);
  }
}

async function queuePrint() {
  state.manufactureBusy = "queue";
  setManufactureFeedback(
    `Queueing job for ${state.selectedPrinter}...\n` +
    "The request is being validated before it enters the printer queue.",
    "busy",
  );
  renderManufacturingState();
  try {
    const payload = buildPrintPayload();
    payload.auto_start = true;
    const result = await fetchJson("/api/queue/enqueue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.manufactureBusy = "";
    setManufactureFeedback(
      `Queued on ${state.selectedPrinter}.\n` +
      `Position: ${result.position}`,
      "success",
    );
    renderManufacturingState();
    showToast(`Queued at position ${result.position}`);
    await refreshControlCenterSafe();
  } catch (error) {
    state.manufactureBusy = "";
    setManufactureFeedback(error.message, "error");
    renderManufacturingState();
    showToast(error.message, 3600);
  }
}

async function executePrintSend() {
  const preparingMessage = state.currentModel?.templateKey === "bridge_keychain"
    ? "Validating the printer, rebuilding the 3-color AMS assembly, slicing it, and uploading the job."
    : "Validating the printer, slicing the model, and uploading the job.";
  state.manufactureBusy = "print";
  setPrintReviewSending(true);
  setManufactureFeedback(
    `${state.autoStart ? `Starting print on ${state.selectedPrinter}...` : `Preparing print on ${state.selectedPrinter}...`}\n` +
    `${preparingMessage}\n` +
    (state.autoStart
      ? "The printer will begin immediately if the upload passes."
      : "Auto start is off, so this stages the job without starting the printer."),
    "busy",
  );
  renderManufacturingState();
  try {
    const payload = buildPrintPayload();
    payload.auto_start = Boolean(state.autoStart);
    const result = await fetchJson("/api/slice_send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.estimate = result;
    state.preflight = result.preflight || state.preflight;
    const effectivePrinter = result.effective_printer_name || state.selectedPrinter || "printer";
    const lines = [
      result.started ? `Print started on ${effectivePrinter}.` : `Job prepared on ${effectivePrinter}.`,
    ];
    if (result.upload?.upload_name) {
      lines.push(`File: ${result.upload.upload_name}`);
    }
    const keychainMapping = formatKeychainAmsMapping(result.keychain_multicolor || result.slice?.keychain_multicolor);
    if (keychainMapping) {
      lines.push(keychainMapping);
    }
    if (!result.started) {
      lines.push("Uploaded to printer storage. Auto start is off, so the printer has not started yet.");
    }
    closePrintReview(true);
    setManufactureFeedback(lines.join("\n"), "success");
    renderManufacturingState();
    showToast(result.started ? "Print started" : "Job prepared");
    await refreshControlCenterSafe();
  } catch (error) {
    setManufactureFeedback(error.message, "error");
    renderManufacturingState();
    setPrintReviewSending(false);
    showToast(error.message, 3600);
  } finally {
    state.manufactureBusy = "";
    renderManufacturingState();
  }
}

function sendPrint() {
  openPrintReview();
}

function initViewer() {
  const scene = new THREE.Scene();
  scene.background = null;

  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 1000);
  camera.position.set(0, 1.2, 5.2);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.domElement.style.touchAction = "none";
  renderer.domElement.style.cssText = "touch-action:none;width:100%;height:100%;display:block;";
  els.viewer.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.enablePan = false;
  controls.screenSpacePanning = false;
  controls.touches.ONE = THREE.TOUCH.ROTATE;
  controls.touches.TWO = THREE.TOUCH.DOLLY_ROTATE;
  controls.minDistance = 1.5;
  controls.maxDistance = 10;

  // Lighting — warm industrial feel
  const hemi = new THREE.HemisphereLight(0xfff4e8, 0x2a3142, 2.2);
  scene.add(hemi);

  const key = new THREE.DirectionalLight(0xfff8f2, 3.4);
  key.position.set(2.8, 4.8, 6.2);
  scene.add(key);

  const fill = new THREE.DirectionalLight(0xc0d0f0, 1.3);
  fill.position.set(-5, 3, 4);
  scene.add(fill);

  const rim = new THREE.DirectionalLight(0xe8551a, 0.55);
  rim.position.set(-3, 2, -4);
  scene.add(rim);

  // Stage platform
  const stage = new THREE.Mesh(
    new THREE.CylinderGeometry(2.6, 2.8, 0.14, 56),
    new THREE.MeshStandardMaterial({
      color: 0x1a1d26,
      metalness: 0.3,
      roughness: 0.7,
      transparent: true,
      opacity: 0.95,
    }),
  );
  stage.position.y = -1.1;
  scene.add(stage);

  // Orange accent ring
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(2.82, 3.1, 64),
    new THREE.MeshBasicMaterial({
      color: 0xe8551a,
      transparent: true,
      opacity: 0.18,
      side: THREE.DoubleSide,
    }),
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = -1.02;
  scene.add(ring);

  viewer.scene = scene;
  viewer.camera = camera;
  viewer.renderer = renderer;
  viewer.controls = controls;
  viewer.stage = stage;
  viewer.ring = ring;

  const resize = () => {
    const rect = els.viewer.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    camera.aspect = rect.width / rect.height;
    camera.updateProjectionMatrix();
    renderer.setSize(rect.width, rect.height, true);
  };

  viewer.resizeObserver = new ResizeObserver(resize);
  viewer.resizeObserver.observe(els.viewer);
  resize();

  const animate = () => {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  };
  animate();
}

function clearViewerMesh() {
  viewer.loadToken += 1;
  if (!viewer.mesh) return;
  viewer.scene.remove(viewer.mesh);
  viewer.mesh.traverse((node) => {
    if (!node.isMesh) return;
    node.geometry?.dispose?.();
    if (Array.isArray(node.material)) {
      node.material.forEach((material) => material?.dispose?.());
    } else {
      node.material?.dispose?.();
    }
  });
  viewer.mesh = null;
  viewer.renderMesh = null;
  viewer.isTemplateModel = false;
  viewer.templatePivot = null;
}

function positionStageForMesh(size) {
  if (!viewer.stage || !viewer.ring) return;
  if (viewer.isTemplateModel) {
    viewer.stage.visible = false;
    viewer.ring.visible = false;
    return;
  }
  viewer.stage.visible = true;
  viewer.ring.visible = true;
  const footprint = Math.max(size.x, size.z, 10);
  const scale = Math.max(footprint / 5.2, 1.2);
  const y = -(size.y * 0.5) - 0.14;
  viewer.stage.scale.set(scale, 1, scale);
  viewer.stage.position.y = y;
  viewer.ring.scale.set(scale, scale, scale);
  viewer.ring.position.y = y + 0.08;
}

function frameMesh(mesh) {
  mesh.updateWorldMatrix(true, true);
  const box = new THREE.Box3().setFromObject(mesh);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z, 1);
  const fov = THREE.MathUtils.degToRad(viewer.camera.fov);
  const aspect = Math.max(viewer.camera.aspect || 1, 0.1);
  const fitHeight = (size.y * 0.5) / Math.tan(fov / 2);
  const fitWidth = (size.x * 0.5) / (Math.tan(fov / 2) * aspect);
  const fitDepth = size.z * (viewer.isTemplateModel ? 1.6 : 1.2);
  const distance = Math.max(fitHeight, fitWidth, fitDepth, maxDim * 0.55)
    * (viewer.isTemplateModel ? 1.18 : 1.15);

  positionStageForMesh(size);
  if (viewer.isTemplateModel) {
    // Template model is always aligned to world origin by buildTemplatePreviewRoot.
    // Always aim at world origin to avoid drift from rotated bounding box shifts.
    viewer.camera.position.set(0, 0, distance);
    viewer.controls.target.set(0, 0, 0);
    viewer.camera.near = Math.max(0.1, maxDim / 200);
    viewer.camera.far = Math.max(1000, distance * 8);
    viewer.camera.updateProjectionMatrix();
    viewer.controls.minDistance = Math.max(maxDim * 0.3, 1.5);
    viewer.controls.maxDistance = Math.max(distance * 4, 10);
    viewer.controls.update();
    return;
  } else {
    viewer.camera.position.set(
      center.x + (maxDim * 0.28),
      center.y + (maxDim * 0.18),
      center.z + distance,
    );
  }
  viewer.camera.near = Math.max(0.1, maxDim / 200);
  viewer.camera.far = Math.max(1000, distance * 8);
  viewer.camera.updateProjectionMatrix();
  viewer.controls.minDistance = Math.max(maxDim * 0.35, 1.5);
  viewer.controls.maxDistance = Math.max(distance * 3.5, 10);
  viewer.controls.target.copy(center);
  viewer.controls.update();
}

function alignGroupToOrigin(group) {
  group.updateWorldMatrix(true, true);
  const box = new THREE.Box3().setFromObject(group);
  const center = box.getCenter(new THREE.Vector3());
  group.position.sub(center);
}

function buildTemplatePreviewRoot(content) {
  const normalized = new THREE.Group();
  normalized.add(content);
  alignGroupToOrigin(normalized);

  const spin = new THREE.Group();
  spin.add(normalized);
  spin.updateWorldMatrix(true, true);
  const frameBox = new THREE.Box3().setFromObject(spin);

  const root = new THREE.Group();
  root.add(spin);
  root.userData.templatePivot = spin;
  root.userData.templateFrameSize = frameBox.getSize(new THREE.Vector3());
  return root;
}

function loadStlGeometry(url, token) {
  return new Promise((resolve, reject) => {
    viewer.loader.load(
      url,
      (geometry) => {
        if (token !== viewer.loadToken) {
          geometry.dispose?.();
          resolve(null);
          return;
        }
        geometry.computeVertexNormals();
        resolve(geometry);
      },
      undefined,
      reject,
    );
  });
}

async function loadPreviewPartsIntoViewer(parts, options = {}) {
  clearViewerMesh();
  viewer.isTemplateModel = options.templateKey === "bridge_keychain";
  // Ensure canvas is correctly sized before loading (fixes corner-render bug on iPad)
  if (viewer.resizeObserver && els.viewer) {
    const rect = els.viewer.getBoundingClientRect();
    if (rect.width && rect.height) {
      viewer.camera.aspect = rect.width / rect.height;
      viewer.camera.updateProjectionMatrix();
      viewer.renderer.setSize(rect.width, rect.height, true);
    }
  }
  const token = viewer.loadToken;
  try {
    const loaded = await Promise.all(
      parts.map(async (part) => {
        const geometry = await loadStlGeometry(part.stlUrl || part.stl_url, token);
        if (!geometry) return null;
        const norm = normalizeHex8(part.color);
        const displayColor = (() => {
          if (!viewer.isTemplateModel) return hexToCssColor(part.color);
          const plan = inferredKeychainAmsPlan();
          const slot = plan.find((item) => item.color === norm);
          return slot?.tray_color ? hexToCssColor(slot.tray_color) : hexToCssColor(part.color);
        })();
        // Non-body parts (accent/name, logo) may be coplanar with the body surface.
        // Use polygonOffset so they always render on top without Z-fighting.
        const isBody = viewer.isTemplateModel && keychainColorRole(norm) === "Body";
        return { geometry, color: displayColor, isBody };
      }),
    );
    if (token !== viewer.loadToken) return;

    const assembled = new THREE.Group();
    loaded.filter(Boolean).forEach((part) => {
      const material = new THREE.MeshStandardMaterial({
        color: part.color,
        metalness: 0.12,
        roughness: 0.58,
        side: THREE.DoubleSide,
        polygonOffset: !part.isBody,
        polygonOffsetFactor: part.isBody ? 0 : -2,
        polygonOffsetUnits: part.isBody ? 0 : -2,
      });
      const mesh = new THREE.Mesh(part.geometry, material);
      if (!part.isBody) mesh.renderOrder = 1;
      assembled.add(mesh);
    });
    if (!assembled.children.length) {
      setViewerEmptyVisible(true);
      setStatus("Could not load the keychain preview.");
      return;
    }

    const root = viewer.isTemplateModel ? buildTemplatePreviewRoot(assembled) : assembled;
    viewer.scene.add(root);
    viewer.mesh = root;
    viewer.renderMesh = root;
    viewer.templatePivot = root.userData?.templatePivot || null;
    frameMesh(root);
    setKeychainPreviewView(viewer.templateView || "front");
    renderTemplateStage();
    setViewerEmptyVisible(false);
  } catch (_) {
    if (token !== viewer.loadToken) return;
    setViewerEmptyVisible(true);
    setStatus("Could not load the colored keychain preview.");
  }
}

function loadStlIntoViewer(url, options = {}) {
  clearViewerMesh();
  viewer.isTemplateModel = options.templateKey === "bridge_keychain";
  const token = viewer.loadToken;
  viewer.loader.load(
    url,
    (geometry) => {
      if (token !== viewer.loadToken) {
        geometry.dispose?.();
        return;
      }
      geometry.computeVertexNormals();
      geometry.center();
      geometry.computeBoundingBox();
      geometry.computeBoundingSphere();

      const material = new THREE.MeshStandardMaterial({
        color: 0xede8e2,
        metalness: 0.08,
        roughness: 0.62,
        side: viewer.isTemplateModel ? THREE.DoubleSide : THREE.FrontSide,
      });
      const surface = new THREE.Mesh(geometry, material);
      let root = new THREE.Group();
      if (viewer.isTemplateModel) {
        const assembled = new THREE.Group();
        assembled.add(surface);
        root = buildTemplatePreviewRoot(assembled);
      } else {
        root.add(surface);
      }
      viewer.scene.add(root);
      viewer.mesh = root;
      viewer.renderMesh = surface;
      viewer.templatePivot = root.userData?.templatePivot || null;
      frameMesh(root);
      if (viewer.isTemplateModel) {
        setKeychainPreviewView(viewer.templateView || "front");
      }

      // Hide empty state — model is loaded
      setViewerEmptyVisible(false);
    },
    undefined,
    () => {
      // On error, show empty state again
      setViewerEmptyVisible(true);
      setStatus("Could not load the STL preview.");
    },
  );
}

function bindDropzone() {
  const zone = els.imageDropzone;
  zone.addEventListener("click", () => els.imageUploadInput.click());
  ["dragenter", "dragover"].forEach((name) => {
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.add("is-dragging");
    });
  });
  ["dragleave", "dragend", "drop"].forEach((name) => {
    zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.remove("is-dragging");
    });
  });
  zone.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    applySourceFile(file, "Dropped reference");
  });
}

function applySourceFile(file, label) {
  const previewUrl = URL.createObjectURL(file);
  setSource({
    kind: "file",
    file,
    previewUrl,
    revokeUrl: true,
    label: label || file.name || "Reference image",
    meta: `${file.type || "image"} · ${(file.size / (1024 * 1024)).toFixed(1)} MB`,
  });
}

function initBedViewer3D() {
  const canvas = document.getElementById("bedPreviewCanvas");
  const wrap   = document.getElementById("bedCanvasWrap");
  if (!canvas || !wrap) return;

  const scene = new THREE.Scene();
  const _isDark = document.documentElement.getAttribute("data-theme") === "dark";
  scene.background = new THREE.Color(_isDark ? 0x1a1d26 : 0xE8E2D8);
  bedViewer3D.scene = scene;

  const camera = new THREE.PerspectiveCamera(34, 1, 2, 1800);
  camera.position.set(175, 190, 175);
  bedViewer3D.camera = camera;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setSize(512, 512, false);   // sets canvas px dims; CSS fills wrapper
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  bedViewer3D.renderer = renderer;

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.enableRotate = true;
  controls.enablePan = true;
  controls.screenSpacePanning = false;
  controls.zoomSpeed = 0.92;
  controls.panSpeed = 0.85;
  controls.minDistance = 70;
  controls.maxDistance = 580;
  controls.minPolarAngle = 0.35;
  controls.maxPolarAngle = 1.42;
  controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  controls.mouseButtons.RIGHT = THREE.MOUSE.PAN;
  controls.touches.ONE = THREE.TOUCH.ROTATE;
  controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;
  controls.target.set(0, 0, 0);
  bedViewer3D.controls = controls;

  // ── Bambu X1C Textured PEI plate (256 × 256 mm) ─────────────────────────
  const plate = new THREE.Mesh(
    new THREE.BoxGeometry(BED_MM, 3, BED_MM),
    new THREE.MeshStandardMaterial({ color: 0x202733, metalness: 0.06, roughness: 0.9 }),
  );
  plate.position.y = -1.5;   // top face at y = 0
  plate.receiveShadow = true;
  scene.add(plate);

  // Grid overlay — major 16×16 + minor 32×32
  const gMaj = new THREE.GridHelper(BED_MM, 16, 0x4a5060, 0x3a4050);
  gMaj.position.y = 0.05;
  scene.add(gMaj);
  const gMin = new THREE.GridHelper(BED_MM, 32, 0x333b48, 0x2a3240);
  gMin.position.y = 0.02;
  scene.add(gMin);

  const axes = buildBedAxesMarker();
  scene.add(axes);
  bedViewer3D.axes = axes;

  // Lighting — same balance as main viewer for visual consistency
  scene.add(new THREE.AmbientLight(0xffffff, 0.86));
  const kl = new THREE.DirectionalLight(0xffffff, 1.45);
  kl.position.set(180, 260, 160);
  kl.castShadow = true;
  kl.shadow.mapSize.set(512, 512);
  scene.add(kl);
  const fl = new THREE.DirectionalLight(0xffd9bf, 0.42);
  fl.position.set(-160, 220, -80);
  scene.add(fl);

  // STL loader for actual model geometry
  bedViewer3D.loader = new STLLoader();

  // ResizeObserver — resizes renderer whenever the wrapper resizes
  bedViewer3D.ro = new ResizeObserver((entries) => {
    for (const e of entries) {
      const { width, height } = e.contentRect;
      if (width < 10 || height < 10) continue;
      updateBedCameraFrustum();
      renderer.setSize(Math.round(width), Math.round(height), false);
    }
  });
  bedViewer3D.ro.observe(wrap);
  updateBedCameraFrustum();

  // Render loop
  (function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  })();
}

// ── Remove whatever model is currently shown on the bed ───────────────────
function clearBedModel() {
  const scene = bedViewer3D.scene;
  if (!scene || !bedViewer3D.modelMesh) return;
  scene.remove(bedViewer3D.modelMesh);
  bedViewer3D.modelMesh.traverse((n) => {
    if (!n.isMesh) return;
    n.geometry?.dispose();
    if (Array.isArray(n.material)) n.material.forEach((m) => m?.dispose());
    else n.material?.dispose();
  });
  bedViewer3D.modelMesh = null;
}

// ── Frame the bed camera to show the model sitting on the plate ──────────
function frameBedCamera(group) {
  const cam  = bedViewer3D.camera;
  const ctrl = bedViewer3D.controls;
  if (!cam || !ctrl) return;

  group.updateWorldMatrix(true, true);
  const box  = new THREE.Box3().setFromObject(group);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const footprint = Math.max(size.x, size.z, 30);
  const height = Math.max(size.y, 6);
  const fullSpan = BED_MM * 0.95;
  const focusSpan = Math.min(fullSpan, Math.max(52, (footprint * 1.05) + 20));
  const span = state.bedViewMode === "full" ? fullSpan : focusSpan;
  bedViewer3D.frameHalfSpan = span;
  const fov = THREE.MathUtils.degToRad(cam.fov || 34);
  const distance = Math.max(90, (span * 0.78) / Math.tan(fov / 2));
  const viewDir = new THREE.Vector3(1.0, 0.92, 1.06).normalize();
  const target = new THREE.Vector3(center.x, Math.max(0, box.min.y) + (height * 0.1), center.z);
  const cameraPos = target.clone().addScaledVector(viewDir, distance);
  cam.position.copy(cameraPos);
  cam.near = 2;
  cam.far = Math.max(1800, distance * 8);
  cam.updateProjectionMatrix();
  ctrl.minDistance = Math.max(60, distance * 0.45);
  ctrl.maxDistance = Math.max(560, distance * 2.8);
  ctrl.target.copy(target);
  ctrl.update();
}

// ── Shared: place a group flat on the plate, centred at origin ───────────
function _placeBedGroup(group, isKeychain) {
  // Keychains from backend are in XY plane (face-on); rotate -90° around X
  // to lay them flat on the build plate (XZ plane, Y = up).
  if (isKeychain) group.rotation.x = -Math.PI / 2;

  group.updateMatrixWorld(true);
  const box    = new THREE.Box3().setFromObject(group);
  const center = box.getCenter(new THREE.Vector3());
  // Translate so bottom sits at y=0 and model is centred in X/Z
  group.position.set(-center.x, -box.min.y, -center.z);
  group.updateMatrixWorld(true);
}

// ── Load colored preview parts into the bed scene ─────────────────────────
async function loadPreviewPartsIntoBedViewer(parts) {
  const scene = bedViewer3D.scene;
  if (!scene || !bedViewer3D.loader) return;

  clearBedModel();

  const isKeychain = state.currentModel?.templateKey === "bridge_keychain";
  const loader = bedViewer3D.loader;
  try {
    // For keychain, remap each part's design colour to the AMS tray colour it will print with
    // so the bed preview shows black body (etc.) rather than the template's gray design colour.
    const amsPlan = isKeychain ? inferredKeychainAmsPlan() : [];
    const trayColorFor = (designHex) => {
      const norm = normalizeHex8(designHex);
      const slot = amsPlan.find((item) => item.color === norm);
      return slot?.tray_color ? hexToCssColor(slot.tray_color) : hexToCssColor(designHex);
    };

    const loaded = await Promise.all(
      parts.map((part) =>
        new Promise((resolve) => {
          const url = part.stlUrl || part.stl_url;
          if (!url) { resolve(null); return; }
          const displayColor = isKeychain ? trayColorFor(part.color) : hexToCssColor(part.color);
          loader.load(
            url,
            (geo) => { geo.computeVertexNormals(); resolve({ geo, color: displayColor }); },
            null,
            () => resolve(null),
          );
        }),
      ),
    );

    const group = new THREE.Group();
    loaded.filter(Boolean).forEach(({ geo, color }) => {
      const mesh = new THREE.Mesh(
        geo,
        new THREE.MeshStandardMaterial({ color, metalness: 0.12, roughness: 0.58, side: THREE.DoubleSide }),
      );
      mesh.castShadow = true;
      group.add(mesh);
    });

    if (!group.children.length) return;

    _placeBedGroup(group, isKeychain);
    scene.add(group);
    bedViewer3D.modelMesh = group;
    frameBedCamera(group);
  } catch (e) {
    console.warn("bed viewer: load failed", e);
  }
}

// ── Load a single STL into the bed scene ─────────────────────────────────
function loadStlIntoBedViewer(url) {
  const scene = bedViewer3D.scene;
  if (!scene || !bedViewer3D.loader) return;

  clearBedModel();

  const isKeychain = state.currentModel?.templateKey === "bridge_keychain";
  bedViewer3D.loader.load(url, (geo) => {
    geo.computeVertexNormals();
    const mesh = new THREE.Mesh(
      geo,
      new THREE.MeshStandardMaterial({ color: 0x69707a, metalness: 0.15, roughness: 0.65 }),
    );
    mesh.castShadow = true;

    const group = new THREE.Group();
    group.add(mesh);
    _placeBedGroup(group, isKeychain);
    scene.add(group);
    bedViewer3D.modelMesh = group;
    frameBedCamera(group);
  });
}

// ── Toggle bed pane expanded / collapsed ────────────────────────────────
function toggleBedPane(expand) {
  const bedPane  = document.getElementById("viewerBedPane");
  const mainPane = document.getElementById("viewerMain");
  if (!bedPane || !mainPane) return;

  const shouldExpand = expand !== undefined ? expand : !bedPane.classList.contains("is-expanded");
  bedPane.classList.toggle("is-expanded", shouldExpand);
  mainPane.classList.toggle("is-collapsed", shouldExpand);

  if (shouldExpand) {
    // Force renderer to fill the newly opened pane after the 420ms CSS transition
    setTimeout(() => {
      const wrap = document.getElementById("bedCanvasWrap");
      if (!wrap || !bedViewer3D.renderer || !bedViewer3D.camera) return;
      const { width, height } = wrap.getBoundingClientRect();
      if (width < 10 || height < 10) return;
      bedViewer3D.camera.aspect = width / height;
      bedViewer3D.camera.updateProjectionMatrix();
      bedViewer3D.renderer.setSize(Math.round(width), Math.round(height), false);
    }, 440);
  }
}

// ── Update bed info text only (model loading is done separately) ─────────
function renderBedPreview() {
  const model = state.currentModel;
  if (els.bedPaneInfo) {
    if (model?.templateKey === "bridge_keychain" && model.dimensionsMm) {
      const d = model.dimensionsMm;
      const coverage = ((Number(d.x || 0) * Number(d.y || 0)) / (BED_MM * BED_MM)) * 100;
      els.bedPaneInfo.textContent =
        `${model.name || "--"} · ${d.x.toFixed(0)} × ${d.y.toFixed(0)} × ${d.z.toFixed(1)} mm\n`
        + `${state.bedViewMode === "full" ? "Whole bed" : "Focused"} · ${coverage.toFixed(1)}% coverage · ${selectedTrayLabel()}`;
    } else if (model?.dimensionsMm) {
      const d = model.dimensionsMm;
      const coverage = ((Number(d.x || 0) * Number(d.y || 0)) / (BED_MM * BED_MM)) * 100;
      els.bedPaneInfo.textContent =
        `${d.x.toFixed(0)} × ${d.y.toFixed(0)} mm · target ${Number(state.targetMaxExtentMm || 70)} mm\n`
        + `${state.bedViewMode === "full" ? "Whole bed" : "Focused"} · ${coverage.toFixed(1)}% coverage`;
    } else {
      els.bedPaneInfo.textContent = "Bambu X1C · 256 × 256 mm";
    }
    renderBedViewMode();
    return;
  }
  if (els.bedPaneInfo) {
    if (model?.templateKey === "bridge_keychain" && model.dimensionsMm) {
      const d = model.dimensionsMm;
      els.bedPaneInfo.textContent =
        `${model.name || "--"}  ·  ${d.x.toFixed(0)} × ${d.y.toFixed(0)} × ${d.z.toFixed(1)} mm`;
    } else if (model?.dimensionsMm) {
      const d = model.dimensionsMm;
      els.bedPaneInfo.textContent =
        `${d.x.toFixed(0)} × ${d.y.toFixed(0)} mm  ·  target ${Number(state.targetMaxExtentMm || 70)} mm`;
    } else {
      els.bedPaneInfo.textContent = "Bambu X1C  ·  256 × 256 mm";
    }
  }
}

function startClock() {
  const tick = () => {
    const formatter = new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
    els.clockPill.textContent = formatter.format(new Date());
  };
  tick();
  setInterval(tick, 30000);
}

async function loadLibrary() {
  try {
    state.library = await fetchJson("/static/assets/inspiration/library.json");
  } catch (_) {
    state.library = [];
  }
  renderGalleryFilters();
  renderGallery();
}

async function loadTemplates() {
  try {
    const payload = await fetchJson("/api/templates");
    state.templates = Array.isArray(payload.items) ? payload.items : [];
  } catch (_) {
    state.templates = [];
  }
  renderTemplateFacts();
}

function bindEvents() {
  els.promptInput.addEventListener("input", updatePromptCount);
  els.keychainNameInput?.addEventListener("input", updateKeychainCount);

  // Bed pane toggle — click narrow strip to expand; click collapsed 3D strip to collapse
  els.viewer3dBtn?.addEventListener("click", () => setPreviewPane("3d"));
  els.viewerPlateBtn?.addEventListener("click", () => setPreviewPane("plate"));
  els.viewerFullscreenBtn?.addEventListener("click", toggleViewerFullscreen);
  els.previewOverlayCloseBtn?.addEventListener("click", () => {
    state.previewExpanded = false;
    renderPreviewExpansion();
  });
  els.bedFocusBtn?.addEventListener("click", () => setBedViewMode("focus"));
  els.bedFullBtn?.addEventListener("click", () => setBedViewMode("full"));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.previewExpanded) {
      state.previewExpanded = false;
      renderPreviewExpansion();
    }
  });

  renderKeychainSwatches();

  els.presetButtons.forEach((button) => {
    button.addEventListener("click", () => setPreset(button.dataset.preset));
  });

  els.modeButtons.forEach((button) => {
    button.addEventListener("click", () => setMode(button.dataset.mode));
  });

  els.imageUploadInput.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setMode("image");
    applySourceFile(file, "Uploaded reference");
  });

  els.cameraInput.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setMode("image");
    applySourceFile(file, "Camera capture");
  });

  els.cameraCaptureBtn.addEventListener("click", () => els.cameraInput.click());
  els.clearSourceBtn.addEventListener("click", clearSource);
  els.generateBtn.addEventListener("click", generateCurrentMode);
  els.cancelBtn.addEventListener("click", cancelGeneration);

  els.exportMenuBtn.addEventListener("click", () => toggleExportMenu());
  els.exportStlBtn.addEventListener("click", () => downloadModel("stl"));
  els.exportObjBtn.addEventListener("click", () => downloadModel("obj"));
  els.export3mfBtn?.addEventListener("click", () => downloadModel("3mf"));
  els.keychainFrontBtn?.addEventListener("click", () => setKeychainPreviewView("front"));
  els.keychainBackBtn?.addEventListener("click", () => setKeychainPreviewView("back"));
  document.addEventListener("click", (event) => {
    if (!els.exportMenu || els.exportMenu.hidden) return;
    const target = event.target;
    if (els.exportMenu.contains(target) || els.exportMenuBtn.contains(target)) return;
    toggleExportMenu(false);
  });

  els.refreshSnapshotBtn.addEventListener("click", refreshControlCenterSafe);
  els.printerSelect.addEventListener("change", async () => {
    state.selectedPrinter = els.printerSelect.value;
    clearManufactureFeedback();
    await refreshControlCenterSafe();
  });

  els.resumeBtn.addEventListener("click", async () => {
    try {
      await postPrinterCommand("/api/printer_resume");
      showToast("Resume command sent");
      await refreshControlCenterSafe();
    } catch (error) {
      showToast(error.message, 3600);
    }
  });

  els.stopBtn.addEventListener("click", async () => {
    try {
      await postPrinterCommand("/api/printer_stop");
      showToast("Stop command sent");
      await refreshControlCenterSafe();
    } catch (error) {
      showToast(error.message, 3600);
    }
  });

  els.intentButtons.forEach((button) => {
    button.addEventListener("click", () => {
      clearManufactureFeedback();
      state.intent = button.dataset.intent;
      renderManufacturingState();
      renderManufactureSummary();
    });
  });

  els.supportButtons.forEach((button) => {
    button.addEventListener("click", () => {
      clearManufactureFeedback();
      state.supportMode = button.dataset.support;
      renderManufacturingState();
      renderManufactureSummary();
    });
  });

  els.sizePresetButtons.forEach((button) => {
    button.addEventListener("click", () => {
      clearManufactureFeedback();
      setSizePreset(button.dataset.size);
      renderManufactureSummary();
    });
  });

  els.sizeRange.addEventListener("input", () => {
    clearManufactureFeedback();
    state.targetMaxExtentMm = Number(els.sizeRange.value);
    state.sizePreset = inferSizePreset(state.targetMaxExtentMm);
    renderManufacturingState();
    renderManufactureSummary();
    renderBedPreview();
  });

  els.autoStartToggle.addEventListener("change", () => {
    clearManufactureFeedback();
    state.autoStart = els.autoStartToggle.checked;
    renderManufacturingState();
  });

  els.useAmsToggle.addEventListener("change", () => {
    clearManufactureFeedback();
    state.useAms = els.useAmsToggle.checked;
    renderManufacturingState();
    renderManufactureSummary();
    renderBedPreview();
  });

  els.amsSlotSelect.addEventListener("change", () => {
    clearManufactureFeedback();
    state.amsSlot = els.amsSlotSelect.value;
    renderKeychainSwatches();
    renderManufacturingState();
    renderManufactureSummary();
    renderBedPreview();
  });

  els.jobNameInput.addEventListener("input", () => {
    state.jobName = els.jobNameInput.value;
  });

  els.estimateBtn.addEventListener("click", runEstimate);
  els.preflightBtn.addEventListener("click", runPreflight);
  els.queueBtn.addEventListener("click", queuePrint);
  els.printBtn.addEventListener("click", sendPrint);
  els.printReviewCloseBtn?.addEventListener("click", () => closePrintReview());
  els.printReviewBackBtn?.addEventListener("click", () => closePrintReview());
  els.printReviewConfirmBtn?.addEventListener("click", executePrintSend);
  els.printReviewOverlay?.addEventListener("click", (event) => {
    if (event.target === els.printReviewOverlay) {
      closePrintReview();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.printReviewOpen) {
      closePrintReview();
    }
  });
}

async function bootstrap() {
  initTheme();
  initViewer();
  bindDropzone();
  bindEvents();
  startClock();
  renderRecipes();
  setMode("text");
  setPreset("balanced");
  updatePromptCount();
  updateKeychainCount();
  renderResultCards();
  renderPerfCards();
  renderManufacturingState();
  renderManufactureSummary();
  initBedViewer3D();
  renderBedPreview();
  renderKeychainSwatches();
  renderPreviewPane();
  updateGenerateButtonLabel();
  renderTemplateStage();
  renderStagePresentation();
  loadLibrary();
  await loadTemplates();
  await refreshControlCenterSafe();
  state.snapshotTimer = setInterval(refreshControlCenterSafe, SNAPSHOT_INTERVAL_MS);
}

bootstrap();

// ── Theme toggle (appended) ─────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem("printmind-theme");
  if (saved === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
  const btn = document.getElementById("themeToggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    if (isDark) {
      document.documentElement.removeAttribute("data-theme");
      localStorage.setItem("printmind-theme", "light");
    } else {
      document.documentElement.setAttribute("data-theme", "dark");
      localStorage.setItem("printmind-theme", "dark");
    }
    // Sync bed viewer background to new theme
    if (bedViewer3D.scene) {
      const nowDark = document.documentElement.getAttribute("data-theme") === "dark";
      bedViewer3D.scene.background.set(nowDark ? 0x1a1d26 : 0xE8E2D8);
    }
  });
}
