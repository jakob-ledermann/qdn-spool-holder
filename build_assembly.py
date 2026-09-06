#!/usr/bin/env python3
"""Rebuild the full-system mock Assembly.FCStd (headless).

Seats two SpoolHolder brackets into Wall_QDN holes, runs an M6 rod (Ø6) through
both bores and threads three Ø70 spools on it. Fixed link placements (no solver
joints); verified by `verify_fixture.py`.

Usage:
    nix-shell --run "freecadcmd -c \"exec(open('build_assembly.py').read())\""
"""
import os

import FreeCAD as App
import Part

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() \
    else os.getcwd()
WALL = os.path.join(HERE, "Wall_QDN.FCStd")
BRACKET = os.path.join(HERE, "SpoolHolder.FCStd")
OUT = os.path.join(HERE, "Assembly.FCStd")

def wall_grid_offset(body):
    """Measure the first hole-column/row center from the wall solid.

    The hole walls are planar ~10x10 faces with normal along X (side walls)
    or Y (top/bottom walls); the extreme walls give the grid origin, which is
    NOT derivable from the bbox margin (model uses a 33.05 mm x-margin).
    Return (col0_x, row0_y) hole-center coordinates.
    """
    x_min_wall = y_min_wall = None
    for f in body.Shape.Faces:
        if "Plane" not in f.Surface.TypeId:
            continue
        bb = f.BoundBox
        if not (bb.XLength < 12 and bb.YLength < 12 and bb.ZLength < 3):
            continue
        n = f.normalAt(0.5, 0.5)
        if abs(n.x) > 0.99:
            cx = bb.Center.x
            x_min_wall = cx if x_min_wall is None else min(x_min_wall, cx)
        elif abs(n.y) > 0.99:
            cy = bb.Center.y
            y_min_wall = cy if y_min_wall is None else min(y_min_wall, cy)
    if x_min_wall is None or y_min_wall is None:
        print("WARN: could not measure hole grid, assuming centered margin")
        return ((1268.0 - 31.0 * 38.0) / 2.0,
                -190.0 + (190.0 - 4.0 * 38.0) / 2.0)
    return (x_min_wall + 5.0, y_min_wall + 5.0)


pitch = 38.0
WALL_FRONT_Z = 1.2
# bracket landmarks (verified by B5..B7 / bore scan)
LUG_X, LUG_LO_Y, LUG_HI_Y = 10.0, -43.75, -5.75
PYLON_X0, PYLON_X1 = 3.0, 17.0                 # seat pad along X
BORE_Y, BORE_Z = -26.0, 44.0
SEAT_Y_NUDGE = -1.0    # latched lip hook: bracket hangs ~1 mm below grid center

C1, C2 = 11, 20        # wall columns the two brackets latch into
ROW = 1                # lower lug in this wall row (upper 38 mm above)

wallDoc = App.openDocument(WALL, True)
brkDoc = App.openDocument(BRACKET, True)
wallDoc.recompute()
brkDoc.recompute()
wallBody = [o for o in wallDoc.Objects if "Body" in type(o).__name__][0]
brkBody = [o for o in brkDoc.Objects if "Body" in type(o).__name__][0]

COL0, ROW0 = wall_grid_offset(wallBody)
col_x = lambda c: COL0 + (c - 1) * pitch        # col 1..32 center X
row_y = lambda k: ROW0 + k * pitch              # k=0..4 (0 = lowest row)
print("measured grid origin: col0=%.2f row0=%.2f" % (COL0, ROW0))
bX1, bX2 = col_x(C1), col_x(C2)
bY = row_y(ROW) - LUG_LO_Y + SEAT_Y_NUDGE
bZ = WALL_FRONT_Z

doc = App.newDocument("Assembly")
doc.FileName = OUT
doc.save()

asm = doc.addObject("Assembly::AssemblyObject", "Assembly")


def add_link(name, bodyobj, placement):
    lnk = doc.addObject("App::Link", name)
    lnk.LinkedObject = bodyobj
    lnk.Placement = placement
    asm.addObject(lnk) if hasattr(asm, "addObject") else None
    try:
        asm.Group = list(asm.Group) + [lnk]
    except Exception:
        pass
    return lnk


add_link("Wall_Linked", wallBody, App.Placement())
b1 = add_link("Bracket1", brkBody,
              App.Placement(App.Vector(bX1 - LUG_X, bY, bZ), App.Rotation()))
b2 = add_link("Bracket2", brkBody,
              App.Placement(App.Vector(bX2 - LUG_X, bY, bZ), App.Rotation()))

rot_zx = App.Rotation(App.Vector(0, 0, 1), App.Vector(1, 0, 0))
rod_y = BORE_Y + bY
rod_z = BORE_Z + bZ

ROD_LEN = 364.0
rod_cx = (bX1 + bX2) / 2.0   # midpoint between the two bracket bores
rod = doc.addObject("Part::Feature", "Rod_M6")
rod.Shape = Part.makeCylinder(3.0, ROD_LEN)         # base at origin along Z
rod.Placement = App.Placement(
    App.Vector(rod_cx - ROD_LEN / 2.0, rod_y, rod_z), rot_zx)

SPOOL_R, SPOOL_W, SPACING = 35.0, 100.0, 104.0
for i in range(3):
    sp = doc.addObject("Part::Feature", "Spool%d" % (i + 1))
    sp.Shape = Part.makeCylinder(SPOOL_R, SPOOL_W)
    cx = rod_cx + (i - 1) * SPACING
    sp.Placement = App.Placement(
        App.Vector(cx - SPOOL_W / 2.0, rod_y, rod_z), rot_zx)

doc.recompute()
doc.save()
print("saved", OUT)
App.closeDocument(wallDoc.Name)
App.closeDocument(brkDoc.Name)
App.closeDocument(doc.Name)