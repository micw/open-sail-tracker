# Enclosure CAD

Parametric FreeCAD geometry for the Open Sail Tracker enclosure and the tray
for the LILYGO T-SIM7670G-S3 Standard (H802).

## Setup

Initialize the pinned FreeCAD Toolkit submodule:

```bash
git submodule update --init enclosure/freecad-toolkit
```

The repository contains a compressed, reduced H802 reference model. It is
unpacked automatically when the geometry is loaded. The basic setup therefore
only requires the submodule checkout shown above.

To regenerate the reduced model, extract the official LILYGO model outside this
repository and write its path to the ignored local configuration file:

```bash
cd enclosure
printf '%s\n' /path/to/T-A7670X-S3-Standard.step > h802_reference_path.txt
make prepare-reference
make test
```

The environment variable `H802_REFERENCE_STEP` overrides the path file when
needed. Both forms accept paths beginning with `~`.

`make prepare-reference` regenerates the ignored local BREP model and its
tracked `.xz` archive. It removes both
1x16 pin headers and small passive components. The PCB and battery geometry are
retained, while modules, switches and connectors are reduced to their bounding
boxes. The resulting model preserves the tray-relevant envelope and loads
substantially faster than the complete manufacturer STEP assembly.

The geometry centers the reduced H802 assembly and marks it as non-exportable.
Tray geometry can therefore be developed around it without including the
electronics in STL or 3MF exports.

Set `H802_FULL_REFERENCE=1` to bypass the reduced BREP and force the complete
manufacturer model in headless mode. This is considerably slower and can emit
many Open CASCADE projection warnings.

## Files

- `geometry_h802_tray.py`: tray geometry entry point
- `prepare_h802_reference.py`: reduction of the manufacturer STEP assembly
- `h802_reference_path.txt`: ignored local path to the extracted STEP model
- `h802_reference_reduced.brep`: ignored generated model used by FreeCAD
- `h802_reference_reduced.brep.xz`: tracked compressed reference model
- `freecad-toolkit/`: FreeCAD Toolkit v0.3.0 pinned as a Git submodule

The complete manufacturer archive and the extracted STEP model are deliberately
not stored in this repository.

## Reference model

The model comes from the official LILYGO Modem Series repository:

`dimensions/Standard/T-A7670X-S3-Standard.7z`

It is the 3D resource linked by LILYGO's documentation for the
T-SIM7670G-S3 Standard platform. The delivered board revision must still be
measured before the tray design is finalized.
