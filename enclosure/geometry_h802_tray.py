"""Parametric tray geometry for the LILYGO T-SIM7670G-S3 Standard (H802)."""

import lzma
import os
import shutil
from pathlib import Path

import FreeCAD as App
import Part

from freecad_toolkit import PreviewAssembly


MODEL_DIR = Path(__file__).resolve().parent
REFERENCE_PATH_FILE = MODEL_DIR / "h802_reference_path.txt"
REDUCED_REFERENCE = MODEL_DIR / "h802_reference_reduced.brep"
PACKED_REFERENCE = MODEL_DIR / "h802_reference_reduced.brep.xz"


def get_reference_step_value():
    """Get the local STEP path from the environment or the ignored path file."""
    environment_value = os.environ.get("H802_REFERENCE_STEP")
    if environment_value:
        return environment_value
    if REFERENCE_PATH_FILE.is_file():
        return REFERENCE_PATH_FILE.read_text(encoding="utf-8").strip()
    return None


REFERENCE_STEP_VALUE = get_reference_step_value()
REFERENCE_STEP = (
    Path(REFERENCE_STEP_VALUE).expanduser().resolve()
    if REFERENCE_STEP_VALUE
    else None
)
WATCH_FILES = [str(REFERENCE_PATH_FILE)]
if REFERENCE_STEP:
    WATCH_FILES.append(str(REFERENCE_STEP))
WATCH_FILES.extend((str(REDUCED_REFERENCE), str(PACKED_REFERENCE)))
FULL_REFERENCE_IN_HEADLESS = os.environ.get("H802_FULL_REFERENCE", "0") == "1"


def ensure_reduced_reference():
    """Unpack the tracked lightweight reference model when necessary."""
    if REDUCED_REFERENCE.is_file() and (
        not PACKED_REFERENCE.is_file()
        or REDUCED_REFERENCE.stat().st_mtime >= PACKED_REFERENCE.stat().st_mtime
    ):
        return
    if not PACKED_REFERENCE.is_file():
        return

    temporary_path = REDUCED_REFERENCE.with_suffix(".brep.tmp")
    try:
        with lzma.open(PACKED_REFERENCE, "rb") as source, temporary_path.open("wb") as target:
            shutil.copyfileobj(source, target)
        temporary_path.replace(REDUCED_REFERENCE)
    finally:
        temporary_path.unlink(missing_ok=True)


def load_centered_h802_reference():
    """Load the official STEP model and center its footprint at the origin."""
    ensure_reduced_reference()
    if not FULL_REFERENCE_IN_HEADLESS and REDUCED_REFERENCE.is_file():
        shape = Part.read(str(REDUCED_REFERENCE))
        if shape.isNull():
            raise RuntimeError(
                f"FreeCAD could not read the reduced H802 model: {REDUCED_REFERENCE}"
            )
        if not App.GuiUp:
            bounds = shape.BoundBox
            return Part.makeBox(
                bounds.XLength,
                bounds.YLength,
                bounds.ZLength,
                App.Vector(-bounds.XLength / 2.0, -bounds.YLength / 2.0, 0),
            )
        return shape

    if REFERENCE_STEP is None:
        raise RuntimeError(
            "No H802 reference model is configured. Set H802_REFERENCE_STEP or "
            "write the STEP path to enclosure/h802_reference_path.txt."
        )
    if not REFERENCE_STEP.is_file():
        raise FileNotFoundError(f"Missing H802 reference model: {REFERENCE_STEP}")

    shape = Part.read(str(REFERENCE_STEP))
    if shape.isNull():
        raise RuntimeError(f"FreeCAD could not read the H802 STEP model: {REFERENCE_STEP}")

    bounds = shape.BoundBox
    if not App.GuiUp and not FULL_REFERENCE_IN_HEADLESS:
        return Part.makeBox(
            bounds.XLength,
            bounds.YLength,
            bounds.ZLength,
            App.Vector(-bounds.XLength / 2.0, -bounds.YLength / 2.0, 0),
        )

    shape.translate(
        App.Vector(
            -(bounds.XMin + bounds.XMax) / 2.0,
            -(bounds.YMin + bounds.YMax) / 2.0,
            -bounds.ZMin,
        )
    )
    return shape


def create_geometry(doc):
    """Create the initial H802 reference assembly for tray development."""
    assembly = PreviewAssembly()
    assembly.group(
        "H802Reference",
        label="LILYGO T-SIM7670G-S3 Standard (H802 reference)",
        color=(0.30, 0.45, 0.30),
        transparency=65,
        export=False,
    ).add(load_centered_h802_reference())
    return assembly.build(doc)
