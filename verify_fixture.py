#!/usr/bin/env python3
"""Verification for the QDN cable-spool holder (headless, run via freecadcmd).

Usage:
    nix-shell --run "freecadcmd --console verify_fixture.py"

Exits 0 (PASS) or 1 (FAIL). Each check prints a line. The wall grid and the
bracket must have been created by following PLAN.md.

Notes:
- freecadcmd does not flush stdout on script exit, so all output is flushed.
- freecadcmd with `--console script.py` runs the script once; app args after
  the script name are treated as docs to open, so keep it argument-free.
- Objects are matched by Label ("Wall", "Params", "Plate"), not Name.
"""
import os
import sys
import functools

print = functools.partial(print, flush=True)

try:
    import FreeCAD as App
except ImportError:
    print("FreeCAD not importable — run inside: nix-shell")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
WALL = os.path.join(HERE, "Wall_QDN.FCStd")
BRACKET = os.path.join(HERE, "SpoolHolder.FCStd")
ASSEMBLY = os.path.join(HERE, "Assembly.FCStd")

# Latched lip hook: the bracket hangs ~1 mm below exact grid center so the lip
# overhang seats on the sheet edge below each hole (matches manual seating).
SEAT_Y_NUDGE = -1.0

TOL = 5e-3  # relative tolerance for volume checks

checks = []
failures = []


def check(name, ok, detail=""):
    checks.append(name)
    if ok:
        print(f"  PASS  {name}{': ' + detail if detail else ''}")
    else:
        failures.append(name)
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")


def get_sheet(doc):
    return next((o for o in doc.Objects
                 if o.TypeId.startswith("Spreadsheet")), None)


def get_alias_map(sheet):
    m = {}
    for r in "ABCDEFGHIJ":
        for c in range(1, 31):
            cell = f"{r}{c}"
            try:
                v = str(sheet.get(cell))
                al = sheet.getAlias(cell)
            except Exception:
                continue
            if al and v and v != "None":
                m[al] = v
    return m


def find_body(doc, label=None):
    for o in doc.Objects:
        if o.TypeId == "PartDesign::Body" and (label is None or o.Label == label
                                               or o.Name == label):
            return o
    return None


def find_pads(body, sub):
    out = []
    for o in body.OutListRecursive:
        if o.TypeId == "PartDesign::Pad" and sub.lower() in o.Label.lower():
            out.append(o)
    return out


def wall_grid_origin(body):
    """Measure the first hole-column/row center from the wall solid.

    The model's x-margin (33.05 mm) is not the centered bbox margin, so the
    grid origin must be read from the hole walls directly. Returns
    (col0_x, row0_y), hole centers at (col0 + c*pitch, row0 + r*pitch).
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
        return None
    return (x_min_wall + 5.0, y_min_wall + 5.0)


def invalid_features(doc):
    bad = []
    for o in doc.Objects:
        if o.TypeId.startswith("PartDesign::"):
            # Features nested inside a MultiTransform (e.g. a LinearPattern
            # as the Y-direction step) don't expose a standalone shape, even
            # though they compute fine within the parent. Skip them.
            if o.InList and any(i.TypeId == "PartDesign::MultiTransform"
                                for i in o.InList):
                continue
            try:
                if hasattr(o, "Shape"):
                    o.Shape.Volume
            except Exception:
                bad.append(o.Label)
    return bad


def cleanup():
    try:
        for doc in list(App.listDocuments().values()):
            App.closeDocument(doc.Name)
    except Exception:
        pass


print(f"Verifying fixtures in: {HERE}\n")

# ---------------------------------------------------------------- Wall
print("== Wall_QDN.FCStd ==")
if not os.path.exists(WALL):
    check("wall file present", False, "follow PLAN.md Step A")
else:
    check("wall file present", True, os.path.basename(WALL))
    try:
        doc = App.openDocument(WALL)
    except Exception as e:
        check("wall loads without errors", False, str(e))
        cleanup()
        sys.exit(1)

    sheet = get_sheet(doc)
    if sheet is None:
        check("wall spreadsheet present", False)
    else:
        check("wall spreadsheet present", True, sheet.Label)
        p = get_alias_map(sheet)

        def num(k):
            if k not in p:
                return None
            try:
                return float(p[k])
            except ValueError:
                try:
                    return float(p[k].split()[0])
                except Exception:
                    return None

        for k in ("hole_size", "pitch", "wall_w", "wall_h", "sheet_t",
                  "cols", "rows"):
            if k in p:
                check(f"wall param {k} set", True, p[k])
            else:
                check(f"wall param {k} set", False)

        for k, want in [("hole_size", 10.0), ("pitch", 38.0),
                        ("wall_w", 1268.0), ("wall_h", 190.0),
                        ("sheet_t", 1.2)]:
            v = num(k)
            if v is None:
                continue
            check(f"wall param {k} == {want:g}", abs(v - want) < 1e-6,
                  f"{v:g}")
        if num("cols") is not None:
            check("wall cols == 32", int(num("cols")) == 32,
                  f"{num('cols'):.0f}")
        if num("rows") is not None:
            check("wall rows == 5 (drawing)", int(num("rows")) == 5,
                  f"{num('rows'):.0f}")

    bad = invalid_features(doc)
    check("wall: no broken features", len(bad) == 0,
          f"{len(bad)}: {', '.join(bad)}" if bad else "ok")

    body = find_body(doc, "Wall")
    if body is None:
        check("wall body present", False, "no body labeled 'Wall'")
    else:
        try:
            bb = body.Shape.BoundBox
            act = body.Shape.Volume
        except Exception as e:
            check("wall body shape valid", False, str(e))
        else:
            check("wall bbox ~1268x190", abs(bb.XLength - 1268) / 1268 < TOL
                  and abs(bb.YLength - 190) / 190 < TOL,
                  f"{bb.XLength:.1f}x{bb.YLength:.1f}")
            check("wall bbox thickness ~1.2", abs(bb.ZLength - 1.2) / 1.2 < TOL,
                  f"{bb.ZLength:.2f}")
            if num("cols") is not None and num("rows") is not None \
                    and num("hole_size") is not None:
                cc, rr = int(num("cols")), int(num("rows"))
                hs = num("hole_size")
                exp = (num("wall_w") * num("wall_h") * num("sheet_t")
                       - cc * rr * hs * hs * num("sheet_t"))
                check("wall volume == solid minus holes grid",
                      abs(act - exp) / exp < TOL,
                      f"expected {exp:.0f}, got {act:.0f}")
    cleanup()

# ---------------------------------------------------------------- Bracket
print("\n== SpoolHolder.FCStd ==")
if not os.path.exists(BRACKET):
    check("bracket file present", False, "follow PLAN.md Step B")
else:
    check("bracket file present", True, os.path.basename(BRACKET))
    try:
        doc = App.openDocument(BRACKET)
    except Exception as e:
        check("bracket loads without errors", False, str(e))
        cleanup()
        sys.exit(1)

    sheet = get_sheet(doc)
    if sheet is None:
        check("bracket spreadsheet present", False)
    else:
        check("bracket spreadsheet present", True, sheet.Label)
        p = get_alias_map(sheet)

        def num(k):
            if k not in p:
                return None
            try:
                return float(p[k])
            except ValueError:
                try:
                    return float(p[k].split()[0])
                except Exception:
                    return None

        for k in ("lug_size", "lug_pitch_y", "plate_h", "plate_w", "plate_t",
                  "toggle_depth", "toggle_lip", "axle_dia", "seat_depth",
                  "n_spools", "spool_w", "spool_gap", "rod_len"):
            if k in p:
                check(f"bracket param {k} set", True, p[k])
            else:
                check(f"bracket param {k} set", False)

        if num("lug_size") is not None:
            check("lug_size fits 10 mm hole (<=9.9)",
                  num("lug_size") < 9.9, f"{num('lug_size'):g}")
        if num("lug_pitch_y") is not None:
            check("lug_pitch_y == 38 mm grid", abs(num("lug_pitch_y") - 38) < 1e-6,
                  f"{num('lug_pitch_y'):g}")
        if num("axle_dia") is not None:
            check("axle_dia >= M6 (6.0)", num("axle_dia") >= 6.0,
                  f"{num('axle_dia'):g}")
        if num("spool_w") is not None and num("spool_w") < 30:
            check("spool_w real value measured (>30 mm)", False,
                  f"{num('spool_w'):g} mm looks like a placeholder")
        if num("rod_len") is not None and num("n_spools") is not None \
                and num("spool_w") is not None:
            need = (num("n_spools") * (num("spool_w") + 4.0)
                    + 2 * 14.0 + 24.0)
            check("rod_len covers two-end spool load", num("rod_len") >= need,
                  f"rod {num('rod_len'):g} >= {need:g}")

    bad = invalid_features(doc)
    check("bracket: no broken features", len(bad) == 0,
          f"{len(bad)}: {', '.join(bad)}" if bad else "ok")

    body = find_body(doc)
    if body is None:
        check("bracket body present", False, "no PartDesign body found")
        cleanup()
        sys.exit(1)
    check("bracket body present", True, body.Label)
    try:
        act = body.Shape.Volume
    except Exception as e:
        check("bracket body shape valid", False, str(e))
        cleanup()
        sys.exit(1)

    lugs = find_pads(body, "toggle")
    lips = find_pads(body, "lip")
    sleeve = (find_pads(body, "sleeve") + find_pads(body, "pylon")
              + find_pads(body, "seat"))
    pockets = [o for o in body.OutListRecursive
               if o.TypeId == "PartDesign::Pocket"]

    check("B5: two lug lugs", len(lugs) >= 1,
          f"{len(lugs)} pad(s) labeled *Toggle*")
    check("B6: toggle lips present", len(lips) >= 1,
          f"{len(lips)} pad(s) labeled *Lip*")
    check("B7: rod seat pad", len(sleeve) >= 1,
          f"{len(sleeve)} pad(s) labeled *Sleeve*/*Pylon*/*Seat* — do B7 if missing")

    # Bore detection: either a dedicated Pocket, or the solid itself carries
    # a cylindrical hole of ~axle_dia aligned with X (e.g. from a ring pad).
    bore_ok = bool(pockets)
    detail = f"{len(pockets)} pocket(s)"
    if not bore_ok and num("axle_dia") is not None:
        want_r = num("axle_dia") / 2.0
        try:
            for f in body.Shape.Faces:
                s = f.Surface
                if s is not None and s.TypeId and s.TypeId.endswith("Cylinder") \
                        and abs(s.Radius - want_r) < 0.2 \
                        and abs(s.Axis.dot(App.Vector(1, 0, 0))) > 0.99 \
                        and f.BoundBox.XLength > 8.0:
                    bore_ok = True
                    detail = "cylindrical bore Ø%g through the seat" % (2 * want_r)
                    break
        except Exception:
            pass
    check("B7: axle bore present", bore_ok, detail)

    if num("plate_w") is not None and num("plate_t") is not None \
            and num("plate_h") is not None and not sleeve:
        exp = (num("plate_w") * num("plate_h") * num("plate_t")
               + 2 * num("lug_size") ** 2 * num("toggle_depth")
               + 2 * num("lug_size") * num("toggle_lip") * 2.0)
        check("bracket volume == plate + lugs + lips (B6 complete)",
              abs(act - exp) / exp < TOL,
              f"expected {exp:.0f}, got {act:.0f}")
    cleanup()

# ---------------------------------------------------------------- Assembly
print("\n== Assembly.FCStd ==")
if not os.path.exists(ASSEMBLY):
    check("assembly file present", False, "run Step C manually in GUI")
else:
    check("assembly file present", True, os.path.basename(ASSEMBLY))
    try:
        adoc = App.openDocument(ASSEMBLY, True)
        adoc.recompute()
    except Exception as e:
        check("assembly loads without errors", False, str(e))
        cleanup()
        sys.exit(1)

    asm = next((o for o in adoc.Objects
                if o.TypeId == "Assembly::AssemblyObject"), None)
    if asm is None:
        check("assembly object present", False)
    else:
        check("assembly object present", True, asm.Label)
        links = {}
        for o in asm.OutList:
            t = type(o).__name__
            if "Link" in t or "DocumentObject" in t:
                links[o.Label] = o
        wall = links.get("Wall_Linked")
        b1 = links.get("Bracket1")
        b2 = links.get("Bracket2")
        check("assembly: wall link present", wall is not None)
        check("assembly: bracket 1 present", b1 is not None)
        check("assembly: bracket 2 present", b2 is not None)

        # Expected wall hole grid (from Wall_QDN params + measured bbox)
        wdoc = App.openDocument(WALL, True)
        wsheet = get_sheet(wdoc)
        wp = get_alias_map(wsheet) if wsheet else {}
        try:
            pitch = float(wp["pitch"].split()[0])
            cols = int(wp["cols"])
            rows = int(wp["rows"])
        except Exception:
            pitch, cols, rows = None, None, None
        wbody = find_body(wdoc)
        wbb = wbody.Shape.BoundBox if wbody else None

        # bracket geometry (verified local landmarks, see PLAN.md §7)
        lug_x, lug_lo_y, lug_hi_y = 10.0, -43.75, -5.75
        bore_y, bore_z = -26.0, 44.0

        def on_grid(x, y, tol=0.5):
            if not (pitch and cols and rows and wbody):
                return False
            origin = wall_grid_origin(wbody)
            if not origin:
                return False
            ox, oy = origin
            near_x = any(abs(x - (ox + c * pitch)) < tol for c in range(cols))
            near_y = any(abs(y - (oy + r * pitch + SEAT_Y_NUDGE)) < tol
                         for r in range(rows))
            return near_x and near_y

        for name, b in [("Bracket1", b1), ("Bracket2", b2)]:
            if b is None:
                continue
            pl = b.Placement
            lo = (pl.Base.x + lug_x, pl.Base.y + lug_lo_y)
            hi = (pl.Base.x + lug_x, pl.Base.y + lug_hi_y)
            check(f"assembly: {name} lugs on wall grid",
                  on_grid(*lo) and on_grid(*hi),
                  f"lugs at X={pl.Base.x + lug_x:g} "
                  f"Y={lo[1]:g}/{hi[1]:g}")
        if wbb:
            wall_front = wbb.ZMax
        else:
            wall_front = None

        rod = None
        for o in adoc.Objects:
            if o.Label == "Rod_M6" or (o.TypeId == "Part::Feature"
                                       and "Rod" in o.Label):
                rod = o
        if rod is None or rod.Shape is None:
            check("assembly: rod present", False)
        else:
            check("assembly: rod present", True,
                  f"Ø{2 * rod.Shape.BoundBox.ZLength / 2:g} (axis along X)")
            ax = rod.Placement.Rotation.multVec(App.Vector(0, 0, 1))
            check("assembly: rod parallel to wall (along X)",
                  ax.x > 0.99 and abs(ax.y) < 0.01 and abs(ax.z) < 0.01,
                  f"axis=({ax.x:.2f},{ax.y:.2f},{ax.z:.2f})")
            if b1 is not None and b2 is not None:
                xmin = min(b1.Placement.Base.x, b2.Placement.Base.x)
                xmax = max(b1.Placement.Base.x, b2.Placement.Base.x) + 20.0
                rbb = rod.Shape.BoundBox
                check("assembly: rod spans both brackets",
                      rbb.XMin <= xmin + 0.1 and rbb.XMax >= xmax - 0.1,
                      f"rod X {rbb.XMin:g}..{rbb.XMax:g} vs plates "
                      f"{xmin:g}..{xmax:g}")
            if b1 is not None and wall_front is not None:
                by = b1.Placement.Base.y + bore_y
                bz = b1.Placement.Base.z + bore_z
                check("assembly: rod passes through bracket bores",
                      abs(rod.Placement.Base.y - by) < 0.02
                      and abs(rod.Placement.Base.z - bz) < 0.02,
                      f"rod axis Y={rod.Placement.Base.y:g} Z={rod.Placement.Base.z:g} "
                      f"vs bore Y={by:g} Z={bz:g}")

        spools = [o for o in adoc.Objects
                  if o.TypeId == "Part::Feature"
                  and o.Label.lower().startswith("spool")]
        check("assembly: 3 spools present", len(spools) == 3,
              f"{len(spools)} found")
        if spools and wall_front is not None:
            minz = min(o.Shape.BoundBox.ZMin for o in spools)
            check("assembly: spool clearance to wall", minz - wall_front >= 5,
                  f"bottom at {minz:g}, wall front {wall_front:g} "
                  f"-> gap {minz - wall_front:.1f} mm")

    cleanup()

print()
if failures:
    print(f"RESULT: FAIL — {len(failures)} of {len(checks)} checks failed: "
          f"{', '.join(failures)}")
    sys.exit(1)
print(f"RESULT: PASS — all {len(checks)} checks passed.")
sys.exit(0)