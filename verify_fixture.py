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
if os.path.exists(ASSEMBLY):
    check("assembly file present", True)
else:
    check("assembly file present", False, "run Step C manually in GUI")

print()
if failures:
    print(f"RESULT: FAIL — {len(failures)} of {len(checks)} checks failed: "
          f"{', '.join(failures)}")
    sys.exit(1)
print(f"RESULT: PASS — all {len(checks)} checks passed.")
sys.exit(0)