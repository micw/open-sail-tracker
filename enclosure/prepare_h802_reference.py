#!/usr/bin/FreeCADCmd
"""Create a lightweight H802 reference model without the pin headers."""

import os
from pathlib import Path

import FreeCAD as App
import Import
import Part


MODEL_DIR = Path(__file__).resolve().parent
PATH_FILE = MODEL_DIR / "h802_reference_path.txt"
OUTPUT_FILE = MODEL_DIR / "h802_reference_reduced.brep"
MINIMUM_COMPONENT_SPAN_MM = 4.0
MINIMUM_COMPONENT_HEIGHT_MM = 2.0
ALWAYS_KEEP_PREFIXES = (
    "bat-",
    "case-",
    "conn-",
    "esp32-",
    "fpc-",
    "kicad_",
    "lga-",
    "sim-",
    "sma",
    "sw-",
    "tf-",
    "usb-",
)


def get_source_path():
    value = os.environ.get("H802_REFERENCE_STEP")
    if not value and PATH_FILE.is_file():
        value = PATH_FILE.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(
            "Set H802_REFERENCE_STEP or write the STEP path to "
            "enclosure/h802_reference_path.txt."
        )
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"H802 STEP model not found: {path}")
    return path


def collect_component_shapes(component):
    """Return globally placed leaf shapes below one imported component."""
    result = []
    pending = [component]
    while pending:
        obj = pending.pop()
        if obj.TypeId == "Part::Feature" and hasattr(obj, "Shape") and not obj.Shape.isNull():
            shape = obj.Shape.copy()
            shape.Placement = obj.getGlobalPlacement()
            result.append(shape)
        pending.extend(getattr(obj, "OutList", []))
    return result


def should_keep_component(label, bounds):
    """Keep mechanically relevant components while dropping tiny passives."""
    normalized = label.lower()
    if "pinheader" in normalized:
        return False
    if normalized.startswith(ALWAYS_KEEP_PREFIXES):
        return True
    return (
        max(bounds.XLength, bounds.YLength) >= MINIMUM_COMPONENT_SPAN_MM
        or bounds.ZLength >= MINIMUM_COMPONENT_HEIGHT_MM
    )


def main():
    source = get_source_path()
    doc = App.newDocument("H802ReferencePreparation")
    try:
        App.Console.PrintMessage(f"Importing H802 reference model: {source}\n")
        Import.insert(str(source), doc.Name)
        doc.recompute()

        roots = [obj for obj in doc.Objects if obj.Label == "T-A7670X-S3-Standard"]
        if len(roots) != 1:
            raise RuntimeError(f"Expected one H802 assembly root, found {len(roots)}")

        kept_shapes = []
        kept_components = []
        omitted_components = []
        for component in roots[0].OutList:
            shapes = collect_component_shapes(component)
            if not shapes:
                continue
            compound = Part.makeCompound(shapes)
            if should_keep_component(component.Label, compound.BoundBox):
                normalized_label = component.Label.lower()
                if normalized_label.startswith(("bat-", "kicad_")):
                    kept_shapes.extend(shapes)
                else:
                    bounds = compound.BoundBox
                    kept_shapes.append(
                        Part.makeBox(
                            bounds.XLength,
                            bounds.YLength,
                            bounds.ZLength,
                            App.Vector(bounds.XMin, bounds.YMin, bounds.ZMin),
                        )
                    )
                kept_components.append(component.Label)
            else:
                omitted_components.append(component.Label)

        if not kept_shapes:
            raise RuntimeError("No shapes remained after reference-model filtering")
        omitted_pin_headers = [
            label for label in omitted_components if "pinheader" in label.lower()
        ]
        if len(omitted_pin_headers) != 2:
            raise RuntimeError(
                f"Expected to remove two pin headers, removed {len(omitted_pin_headers)}"
            )

        result = Part.makeCompound(kept_shapes)
        bounds = result.BoundBox
        result.translate(
            App.Vector(
                -(bounds.XMin + bounds.XMax) / 2.0,
                -(bounds.YMin + bounds.YMax) / 2.0,
                -bounds.ZMin,
            )
        )
        result.exportBrep(str(OUTPUT_FILE))

        App.Console.PrintMessage(
            f"Wrote {OUTPUT_FILE} with {len(kept_components)} components; "
            f"omitted {len(omitted_components)} components.\n"
        )
        App.Console.PrintMessage(
            "Bounds without pin headers: "
            f"{result.BoundBox.XLength:.2f} x {result.BoundBox.YLength:.2f} x "
            f"{result.BoundBox.ZLength:.2f} mm\n"
        )
    finally:
        App.closeDocument(doc.Name)


try:
    main()
except Exception as error:
    App.Console.PrintError(f"Failed to prepare H802 reference: {error}\n")
    raise
