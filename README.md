# Tymeline

FreeCAD workbench for the Tymeline agent. It runs inside FreeCAD and lets Tymeline read and edit the document you have open.

Derived from [freecad-mcp](https://github.com/neka-nat/freecad-mcp) (MIT).

## Install with the Addon Manager

1. In FreeCAD, open **Edit → Preferences → Addon Manager**. On macOS that is **FreeCAD → Preferences → Addon Manager**.
2. Add this custom repository, branch `main`:

   `https://github.com/sayeed-hoda/Tymeline-FreeCAD-Addon`

3. Open **Tools → Addon Manager**, install **Tymeline**, and restart FreeCAD.

The addon is installed as `Mod/Tymeline/`. **Tymeline** then appears in the workbench list.

## Install by copying the folder

Clone this repository and copy it into FreeCAD's Mod folder as `Tymeline`. `InitGui.py` and `package.xml` must sit directly inside that folder. Restart FreeCAD.

To print the Mod folder the running FreeCAD uses, open **View → Panels → Python console** and run:

```python
import os
print(os.path.join(FreeCAD.getUserAppDataDir(), "Mod"))
```

## License

MIT. Copyright (c) 2025 Shirokuma (k tanaka). See `LICENSE`.

The `websockets` library in `tymeline_rpc/_vendor/` is BSD-3-Clause. See `tymeline_rpc/_vendor/websockets.LICENSE`.
