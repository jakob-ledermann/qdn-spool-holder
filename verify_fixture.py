#!/usr/bin/env python3
"""Verification for the QDN cable-spool holder (headless, run via freecadcmd).

Usage:
    nix-shell --run "freecadcmd --console verify_fixture.py"

Exits 0 (PASS) or 1 (FAIL). Each check prints a line. The wall grid and the
bracket must have been created by following PLAN.md.

The assembly checks are invariant-based: everything (hole rows/columns,
lug/hook geometry, bore axis, plate extent) is measured from the loaded
shapes; nothing is hard-coded except the physical criteria below.

Notes:
- freecadcmd does not flush stdout on script exit, so all output is flushed.
- freecadcmd with `--console script.py` runs the script once; app args after
  the script name are treated as docs to open, so keep it argument-free.
- Objects are matched by Label ("Wall", "Bracket1", ...), not Name.
"""
import os
import sys
import functools
import math

print = functools.partial(print, flush=True)

try:
    import FreeCAD as App
    import Part
except ImportError:
    print("FreeCAD not importable — run inside: nix-shell")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() \
    else os.getcwd()
WALL = os.path.join(HERE, "Wall_QDN.FCStd")
BRACKET = os.path.join(HERE, "SpoolHolder.FCStd")
ASSEMBLY = os.path.join(HERE, "Assembly.FCStd")

# Physical criteria ---------------------------------------------------------
# V1  minimum running clearance between a lug and its hole wall while the lug
#     passes through the sheet (manufacturing tolerance budget: nominal
#     per-side slack is (hole_size - lug_size)/2 = 0.6 mm, +/-0.2 mm error
#     still leaves a usable fit).
MIN_INSERT_CLEARANCE = 0.4
# V2  how far the hook (lug material behind the sheet) reaches below the
#     hole's bottom edge. Positive = the hook wraps under the sheet strip.
#     The diagonal lead-in must never be asked to bear the load.
MIN_BEARING_OVERLAP = 1.5
# V3  hook depth behind the sheet back face before the lip turns around.
MIN_HOOK_BEHIND = 2.0
# V3  self-locking: the load-bearing catch face normal must not lean forward
#     beyond this angle from the "-Y" (downward) axis, else an outward/upward
#     pull cams it out of the wall.
MAX_CAM_OUT_ANGLE = 15.0
# rest position may not overlap the wall (V0)
INTERFERENCE_MAX = 0.5
# both lugs of a bracket must be seated equally into their holes
SEAT_SYMMETRY = 0.75

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


def num_from(p, k):
    if not p or k not in p:
        return None
    try:
        return float(p[k])
    except ValueError:
        try:
            return float(p[k].split()[0])
        except Exception:
            return None


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


def grid_rows_cols(wall_body, pitch):
    """Hole row/column centre coordinates measured from the wall solid."""
    xs, ys = [], []
    for f in wall_body.Shape.Faces:
        if "Plane" not in f.Surface.TypeId:
            continue
        bb = f.BoundBox
        if not (bb.XLength < 12 and bb.YLength < 12 and bb.ZLength < 3):
            continue
        n = f.normalAt(0.5, 0.5)
        # A hole's side walls span its height (y), faces along Y span its width
        # (x); the transverse bbox centre is the true row/column centre.
        if abs(n.x) > 0.99:
            ys.append(bb.Center.y)
        elif abs(n.y) > 0.99:
            xs.append(bb.Center.x)
    if not xs or not ys:
        return None

    def rungs(v):
        v = sorted(set(round(x, 3) for x in v))
        out = [v[0]]
        for a, b in zip(v, v[1:]):
            if b - a > pitch / 2:
                out.append(b)
        return out

    return rungs(xs), rungs(ys)


def feature_world(link, feature):
    """Feature shape (in body coords) transformed into assembly coords."""
    sh = feature.Shape.copy(False)
    lp = link.LinkPlacement if hasattr(link, "LinkPlacement") \
        else link.Placement
    sh.Placement = lp.multiply(sh.Placement)
    return sh


def slab_box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, App.Vector(x0, y0, z0))


print(f"Verifying fixtures in: {HERE}\n")

# ---------------------------------------------------------------- Wall
print("== Wall_QDN.FCStd ==")
wp = {}
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
        wp = get_alias_map(sheet)
        for k in ("hole_size", "pitch", "wall_w", "wall_h", "sheet_t",
                  "cols", "rows"):
            if k in wp:
                check(f"wall param {k} set", True, wp[k])
            else:
                check(f"wall param {k} set", False)
        for k, want in [("hole_size", 10.0), ("pitch", 38.0),
                        ("wall_w", 1268.0), ("wall_h", 190.0),
                        ("sheet_t", 1.2)]:
            v = num_from(wp, k)
            if v is None:
                continue
            check(f"wall param {k} == {want:g}", abs(v - want) < 1e-6,
                  f"{v:g}")
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
            check("wall bbox ~1268x190",
                  abs(bb.XLength - 1268) / 1268 < TOL
                  and abs(bb.YLength - 190) / 190 < TOL,
                  f"{bb.XLength:.1f}x{bb.YLength:.1f}")
            check("wall bbox thickness ~1.2",
                  abs(bb.ZLength - 1.2) / 1.2 < TOL, f"{bb.ZLength:.2f}")
            if num_from(wp, "cols") is not None and num_from(wp, "rows") \
                    is not None and num_from(wp, "hole_size") is not None \
                    and num_from(wp, "wall_w") is not None \
                    and num_from(wp, "wall_h") is not None \
                    and num_from(wp, "sheet_t") is not None:
                cc, rr = int(num_from(wp, "cols")), int(num_from(wp, "rows"))
                hs0 = num_from(wp, "hole_size")
                exp = (num_from(wp, "wall_w") * num_from(wp, "wall_h")
                       * num_from(wp, "sheet_t")
                       - cc * rr * hs0 * hs0 * num_from(wp, "sheet_t"))
                check("wall volume == solid minus holes grid",
                      abs(act - exp) / exp < TOL,
                      f"expected {exp:.0f}, got {act:.0f}")
    cleanup()

# ---------------------------------------------------------------- Bracket
print("\n== SpoolHolder.FCStd ==")
bp = {}
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
        bp = get_alias_map(sheet)
        for k in ("lug_size", "lug_pitch_y", "plate_h", "plate_w", "plate_t",
                  "toggle_depth", "toggle_lip", "toggle_clearing",
                  "axle_dia", "seat_depth", "n_spools", "spool_w",
                  "spool_gap", "rod_len"):
            if k in bp:
                check(f"bracket param {k} set", True, bp[k])
            else:
                check(f"bracket param {k} set", False)
        if num_from(bp, "lug_size") is not None:
            check("lug_size fits 10 mm hole (<=9.9)",
                  num_from(bp, "lug_size") < 9.9, f"{num_from(bp, 'lug_size'):g}")
        if num_from(bp, "lug_pitch_y") is not None:
            check("lug_pitch_y == 38 mm grid",
                  abs(num_from(bp, "lug_pitch_y") - 38) < 1e-6,
                  f"{num_from(bp, 'lug_pitch_y'):g}")
        if num_from(bp, "axle_dia") is not None:
            check("axle_dia >= M6 (6.0)", num_from(bp, "axle_dia") >= 6.0,
                  f"{num_from(bp, 'axle_dia'):g}")
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
    check("B5: toggle lugs present", len(lugs) >= 1,
          f"{len(lugs)} pad(s) labeled *Toggle*")
    check("B6: toggle lips present", len(lips) >= 1,
          f"{len(lips)} pad(s) labeled *Lip*")
    check("B7: rod seat pad", len(sleeve) >= 1,
          f"{len(sleeve)} pad(s) labeled *Sleeve*/*Pylon*/*Seat*")

    bore_ok = bool(pockets)
    detail = f"{len(pockets)} pocket(s)"
    if not bore_ok and num_from(bp, "axle_dia") is not None:
        want_r = num_from(bp, "axle_dia") / 2.0
        try:
            for f in body.Shape.Faces:
                s = f.Surface
                if s is not None and s.TypeId and \
                        s.TypeId.endswith("Cylinder") \
                        and abs(s.Radius - want_r) < 0.2 \
                        and abs(s.Axis.dot(App.Vector(1, 0, 0))) > 0.99 \
                        and f.BoundBox.XLength > 8.0:
                    bore_ok = True
                    detail = ("cylindrical bore Ø%g through the seat"
                              % (2 * want_r))
                    break
        except Exception:
            pass
    check("B7: axle bore present", bore_ok, detail)

    if num_from(bp, "plate_w") is not None and num_from(bp, "plate_t") \
            is not None and num_from(bp, "plate_h") is not None and not sleeve:
        exp = (num_from(bp, "plate_w") * num_from(bp, "plate_h")
               * num_from(bp, "plate_t")
               + 2 * num_from(bp, "lug_size") ** 2
               * num_from(bp, "toggle_depth")
               + 2 * num_from(bp, "lug_size") * num_from(bp, "toggle_lip")
               * 2.0)
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
        cleanup()
        sys.exit(1)
    check("assembly object present", True, asm.Label)
    links = {}
    for o in asm.OutList:
        t = type(o).__name__
        if "Link" in t or "DocumentObject" in t:
            links[o.Label] = o
    wall_link = links.get("Wall_Linked")
    b1 = links.get("Bracket1")
    b2 = links.get("Bracket2")
    check("assembly: wall link present", wall_link is not None)
    check("assembly: bracket 1 present", b1 is not None)
    check("assembly: bracket 2 present", b2 is not None)

    wdoc = App.openDocument(WALL, True)
    wbody = find_body(wdoc, "Wall")
    wbb = wbody.Shape.BoundBox if wbody else None
    wsheet = get_sheet(wdoc)
    wali = get_alias_map(wsheet) if wsheet else {}
    pitch = num_from(wali, "pitch")
    hs = num_from(wali, "hole_size")
    sheet_t = num_from(wali, "sheet_t")
    if pitch is None or hs is None or sheet_t is None or wbody is None:
        check("wall grid params readable", False)
        cleanup()
        sys.exit(1)
    cols, rows = grid_rows_cols(wbody, pitch)
    if not cols or not rows:
        check("wall grid measured", False)
        cleanup()
        sys.exit(1)
    check("wall grid measured", True, f"{len(cols)} col(s), {len(rows)} row(s)")

    wall_front = wbb.ZMax
    wall_back = wbb.ZMax - sheet_t
    print("  wall (assembly): z front/back %.2f/%.2f, holes Ø%g@%g pitch"
          % (wall_front, wall_back, hs, pitch))

    def link_body(link):
        if link is None:
            return None, []
        try:
            body = link.getLinkedObject(True)
            return body, find_pads(body, "toggle")
        except Exception:
            return None, []

    def engaged_row(pext_y, col_x):
        """Row(s) under the pad: hole centres inside the pad Y-band."""
        lo, hi = pext_y
        return [r for r in rows if lo - 1 <= r <= hi + 1]

    def bracket_bore_center(link):
        body, _ = link_body(link)
        if body is None:
            return None
        want_r = num_from(bp, "axle_dia") / 2.0
        bc = feature_world(link, body)
        for f in bc.Faces:
            s = f.Surface
            if s is not None and s.TypeId and s.TypeId.endswith("Cylinder") \
                    and abs(s.Axis.dot(App.Vector(1, 0, 0))) > 0.99 \
                    and want_r is not None and abs(s.Radius - want_r) < 0.2 \
                    and f.BoundBox.XLength > 4.0:
                return s.Center
        return None

    def bracket_bbox(link):
        body, _ = link_body(link)
        return feature_world(link, body).BoundBox if body else None

    def bracket_invariants(name, link):
        body, padlist = link_body(link)
        if body is None or not padlist:
            check(f"A: {name} toggle pad readable", False)
            return
        check(f"A: {name} toggle pad readable", True, f"{len(padlist)} pad(s)")
        pw = feature_world(link, padlist[0])
        pbb = pw.BoundBox
        col = min(cols, key=lambda c: abs(c - pbb.Center.x))
        hx = col
        hits = engaged_row((pbb.YMin, pbb.YMax), hx)
        if len(hits) != 2:
            check(f"A: {name} engages two hole rows", False,
                  f"found {len(hits)}: {hits}")
            return
        check(f"A: {name} engages two hole rows", True,
              f"rows {hits[0]:g}/{hits[1]:g}, col {hx:g}")

        vol = 0.0
        try:
            vol = pw.common(ws).Volume
        except Exception:
            pass
        check(f"V0: {name} rests without overlap",
              vol < INTERFERENCE_MAX, f"{vol:.3f} mm^3")

        min_clear = 999.0
        seats = []
        for r in hits:
            hy = r
            hole = (hx - hs / 2, hx + hs / 2, hy - hs / 2, hy + hs / 2)
            band = pw.common(slab_box(
                hx - hs / 2 - 1, hx + hs / 2 + 1,
                hy - hs / 2 - 8, hy + hs / 2 + 1,
                wall_back - 8, wall_front + 8))
            if band.Volume < 1e-9:
                continue
            bbb = band.BoundBox
            # lug slice inside the sheet thickness only (the pass-through
            # cross-section at the hole) — exclude the plate sliver at the
            # front and the hook/lip material behind the sheet.
            win = band.common(slab_box(
                hx - 6, hx + 6, hy - 6, hy + 6,
                wall_back + 0.005, wall_front - 0.005))
            wbbx = win.BoundBox if win.Volume > 1e-9 else bbb
            gaps = {
                "L": wbbx.XMin - hole[0],
                "R": hole[1] - wbbx.XMax,
                "B": wbbx.YMin - hole[2],
                "T": hole[3] - wbbx.YMax,
            }
            min_clear = min(min_clear, *gaps.values())
            hook = band.common(slab_box(
                hx - 6, hx + 6, hy - 10, hy + 6,
                wall_back - 8, wall_back - 0.05))
            ho = hook.BoundBox if hook.Volume > 1e-9 else None
            check(f"V1: {name} lug@{hy:g} clears hole walls",
                  min(gaps.values()) >= MIN_INSERT_CLEARANCE,
                  " ".join(f"{k}{v:+.2f}" for k, v in gaps.items())
                  + f"  min {min(gaps.values()):.2f}")
            if ho is None:
                check(f"V2: {name} hook@{hy:g} behind sheet", False,
                      "no material behind the wall back face")
            else:
                hook_depth = wall_back - ho.ZMin
                wrap = (hy - hs / 2) - ho.YMin
                check(f"V2: {name} hook@{hy:g} tucks behind sheet",
                      hook_depth >= MIN_HOOK_BEHIND,
                      f"{hook_depth:.2f} mm behind back face")
                check(f"V3: {name} hook@{hy:g} wraps the sheet strip",
                      wrap >= MIN_BEARING_OVERLAP,
                      f"reaches {wrap:+.2f} mm past the hole bottom edge "
                      f"(need >= {MIN_BEARING_OVERLAP:g})")
                if wrap < 0:
                    seats.append(0.0)
                else:
                    seats.append(wrap)
                bear = None
                for f in hook.Faces:
                    try:
                        s = f.Surface
                        if "Plane" not in s.TypeId:
                            continue
                        n = f.normalAt(0.5, 0.5)
                        # the load-bearing catch face is the lowest plane with a
                        # downward (-Y) outward normal (it meets the strip edge
                        # below the hole); skip top faces (nz ~ 0.97).
                        if n.y < -0.9 and f.BoundBox.YMin <= ho.YMin + 0.5:
                            bear = n
                            break
                    except Exception:
                        continue
                if bear is None:
                    check(f"V3: {name} hook@{hy:g} bearing face", False,
                          "no downward bearing face found")
                else:
                    ang = math.degrees(math.acos(
                        min(1.0, max(-1.0, -bear.y))))
                    ok = ang <= MAX_CAM_OUT_ANGLE and bear.z <= 0.05
                    check(f"V3: {name} hook@{hy:g} self-locking", ok,
                          f"catch face tilt {ang:.1f} deg, nz {bear.z:+.2f} "
                          f"(limit {MAX_CAM_OUT_ANGLE:g} deg)")

        check(f"V1: {name} min in-hole clearance",
              min_clear >= MIN_INSERT_CLEARANCE,
              f"{min_clear:.2f} mm running clearance")
        if len(seats) == 2:
            check(f"A: {name} lugs seated symmetrically",
                  abs(seats[0] - seats[1]) <= SEAT_SYMMETRY,
                  f"seat {seats[0]:.2f} vs {seats[1]:.2f} mm")

        pt = num_from(bp, "plate_t")
        if pt is None:
            check(f"V4: {name} plate covers both holes", False,
                  "plate_t missing")
        else:
            plate = pw.common(slab_box(
                hx - 6, hx + 6, wbb.YMin - 1, wbb.YMax + 1,
                wall_front - 0.01, wall_front + pt + 0.01))
            pbb = plate.BoundBox if plate.Volume > 1e-9 else None
            if pbb is None:
                check(f"V4: {name} plate covers both holes", False,
                      "no plate material at wall front")
            else:
                ys = sorted(hits)
                lo_h = ys[0] - hs / 2
                hi_h = ys[1] + hs / 2
                xo_h = hx - hs / 2
                xi_h = hx + hs / 2
                covers = pbb.YMin <= lo_h and pbb.YMax >= hi_h \
                    and pbb.XMin <= xo_h and pbb.XMax >= xi_h
                mid = (ys[0] + ys[1]) / 2.0
                check(f"V4: {name} plate covers both holes fully", covers,
                      f"plate y[{pbb.YMin:.2f},{pbb.YMax:.2f}] vs "
                      f"holes [{lo_h:.2f},{hi_h:.2f}]")
                check(f"V4: {name} plate centre on the hole pair",
                      abs(pbb.Center.y - mid) <= (ys[1] - ys[0]) / 2.0 + 5.0,
                      f"centre y {pbb.Center.y:.2f} vs midpoint {mid:.2f}")

        c = bracket_bore_center(link)
        if c is None:
            check(f"V5: {name} axle bore present", False)
        else:
            check(f"V5: {name} axle bore present", True,
                  f"axis at y={c.y:.2f} z={c.z:.2f}")

    wall_body, _ = link_body(wall_link)
    ws = feature_world(wall_link, wall_body) if wall_body else None
    if ws is None:
        check("assembly: wall shape readable", False)
        cleanup()
        sys.exit(1)
    bracket_invariants("Bracket1", b1)
    bracket_invariants("Bracket2", b2)

    rod = next((o for o in adoc.Objects if o.Label == "Rod_M6"), None)
    if rod is None:
        check("assembly: rod present", False)
    else:
        bb = rod.Shape.BoundBox
        check("assembly: rod present", True,
              f"Ø{bb.ZLength:g} (axis along X)")
        ax = rod.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        check("assembly: rod parallel to wall (along X)",
              ax.x > 0.99 and abs(ax.y) < 0.01 and abs(ax.z) < 0.01,
              f"axis=({ax.x:.2f},{ax.y:.2f},{ax.z:.2f})")
        rb = rod.Placement.Base
        for name, link in (("Bracket1", b1), ("Bracket2", b2)):
            c = bracket_bore_center(link)
            if c is None:
                check(f"V5: rod through {name} bore", False, "no bore found")
            else:
                check(f"V5: rod through {name} bore",
                      abs(rb.y - c.y) < 0.02 and abs(rb.z - c.z) < 0.02,
                      f"rod y={rb.y:.2f} z={rb.z:.2f} vs "
                      f"bore y={c.y:.2f} z={c.z:.2f}")
        bb1 = bracket_bbox(b1)
        bb2 = bracket_bbox(b2)
        if bb1 is not None and bb2 is not None:
            xmin = min(bb1.XMin, bb2.XMin)
            xmax = max(bb1.XMax, bb2.XMax)
            check("assembly: rod spans both brackets",
                  bb.XMin <= xmin + 0.1 and bb.XMax >= xmax - 0.1,
                  f"rod X {bb.XMin:g}..{bb.XMax:g} vs plates "
                  f"{xmin:g}..{xmax:g}")

    spools = [o for o in adoc.Objects
              if o.TypeId == "Part::Feature"
              and o.Label.lower().startswith("spool")]
    check("assembly: 3 spools present", len(spools) == 3, f"{len(spools)} found")
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