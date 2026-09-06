# QDN Cable-Spool Holder — Build Plan & FreeCAD Instructions

Project: wall-mounted holder for small cable spools (Ø ~50 mm, 1 mm² wire),
for the Q-System / QDN perforated panel grid.

Folder: `~/Projekte/qdn-spool-holder/`

---

## 1. Goal & scope

- **Primary goal:** **two printed brackets**, one at each end of the rod. Each
  latches into the wall panel and carries one end of a horizontal **M6
  threaded rod (axis parallel to the wall)** on which 3–4 cable spools hang
  and spin freely for unspooling. Locking: M6 nyloc nut per bracket outside
  face.
- **Supporting reference:** a parameterized model of the wall panel so the
  bracket fit can be verified in an assembly before printing.

### Why not off-the-shelf?
The RasterPlan® Spulenhalter and QDN 0° hooks all give an axle
**perpendicular** to the wall. No standard part for this grid offers an
**axis parallel to the wall**, so a small custom bracket is justified.

---

## 2. The wall system (verified)

| Parameter | Value | Source |
|---|---|---|
| Hole shape | square, 10 × 10 mm | manufacturer drawing, DIN 24041 |
| Hole pitch (c–c) | 38 mm both directions | manufacturer drawing |
| Panel flat area | 1268 × 190 mm (MTR 02A, 3 segments) | product page |
| Sheet thickness | ~1.2 mm (oversized for easy fixture fit) | user note |

The user's earlier "~27 mm" reading matches **38 mm pitch − 10 mm hole =
28 mm edge-to-edge**, i.e. the gap between adjacent holes, not center pitch.

---

## 3. Design parameters

Spool holder bracket (all in one spreadsheet):

| Parameter | Value | Notes |
|---|---|---|
| `lug_size` | 8.8 mm | 10 mm hole − ~1.2 mm print clearance |
| `lug_pitch_y` | 38 mm | vertical c–c of the two latch lugs |
| `plate_h` | 52 mm | backplate height |
| `plate_w` | 40 mm | backplate width |
| `plate_t` | 4 mm | backplate thickness |
| `toggle_depth` | 6 mm | lug insertion behind sheet |
| `toggle_lip` | 2.5 mm | catch lip that hooks behind the sheet |
| `axle_dia` | 6.5 mm | bore for M6 rod (clearance) |
| `sleeve_od` | 14 mm | (unused in pylon style; bore geometry wins) |
| `seat_depth` | 14 mm | rod seat length along the rod, per end bracket; nut presses on outer face |
| `standoff` | 44 mm | rod center distance from the wall (`44 − 25 = 19` mm back-spool clearance for Ø50) |
| `n_spools` | 3 | default |
| `spool_w` | (measure) | flange-to-flange width |
| `spool_gap` | 4 mm | spacing between spools |
| `rod_len` | derived | `= n_spools*(spool_w+spool_gap) + 2*seat_depth + 24 mm` (2 ends × nut ≈ 12 mm) |

---

## 4. Environment

```
nix-shell        # of a shell in this folder
freecad          # launch GUI
```

`shell.nix` is included in this folder; it provides FreeCAD 1.1.3.

---

## 5. File layout (to be created in FreeCAD)

```
Wall_QDN.FCStd            # reference wall (Part Design, parameterized)
SpoolHolder.FCStd         # printable bracket (Part Design, parameterized)
Assembly_QDN.FCStd        # wall + bracket fit check (Assembly workbench)
#   → saved as Assembly.FCStd by user (23:00-ish); verifier now accepts it
verify_fixture.py         # verification (headless) - run after modeling
README.md                 # final parameter table + print notes
shell.nix                 # nix-shell environment
```

---

## 6. Step-by-step instructions

### Step A — Wall reference model (`Wall_QDN.FCStd`)

1. New document → save as `Wall_QDN.FCStd`.
2. **Spreadsheet workbench** → `Create spreadsheet` → rename to `Params`.
   Fill column B and set aliases (select cell → right-click →
   *Properties* → `Alias`):
   - `hole_size` = 10 mm
   - `pitch` = 38 mm
   - `wall_w` = 1268 mm
   - `wall_h` = 190 mm
   - `sheet_t` = 1.2 mm
   - `cols` = 32            (holes horizontally)
   - `rows` = 5             (holes vertically; manufacturer drawing shows 5)
3. **Part Design** → `Create body` → rename `Wall`.
4. Sketch on XY plane → rectangle 1268 × 190, constrained to
   `<<Params>>.wall_w` / `<<Params>>.wall_h` via expressions (click the
   dimension → set formula with `=` → `<<Params>>.wall_w`).
5. `Pad` → length `<<Params>>.sheet_t`.
6. Sketch a single **10 × 10 mm square** somewhere on the face (does not
   matter where; constrain with `<<Params>>.hole_size`).
7. `Pocket` → **Through all** (or `sheet_t`) → this is `Hole`.
8. Select `Hole` → `LinearPattern` → **X direction** → Spacing
   `<<Params>>.pitch`, Occurrences `<<Params>>.cols` → rename `HoleGridX`.
9. Select `HoleGridX` → `LinearPattern` → **Y direction** → Spacing
   `<<Params>>.pitch`, Occurrences `<<Params>>.rows`.
10. Save. Verify visually: 32 × 6 square hole grid, 38 mm pitch.

> Note: the grid is centered; exact edge margins of the real MTR 02A do not
> affect bracket verification, only the pitch and hole grid do.
> If a red/broken feature appears in the tree (e.g. while experimenting with
> pattern tools), delete it — `verify_fixture.py` fails on invalid features.

### Step B — Spool holder bracket (`SpoolHolder.FCStd`)

Idea: backplate with **two latch lugs** (vertical c–c 38 mm) that insert
through the wall holes and hook behind the sheet; on the plate, a horizontal
**axle sleeve** whose bore accepts the M6 rod parallel to the wall.

1. New document → save as `SpoolHolder.FCStd`.
2. **Spreadsheet** `Params` with aliases from §3 (lug_size, lug_pitch_y,
   plate_h/w/t, toggle_depth, toggle_lip, axle_dia, sleeve_od, seat_depth,
   n_spools, spool_w, spool_gap, rod_len).
3. **Part Design** → `Create body` → `Plate`.
4. On XY plane, sketch backplate outline: width `plate_w`, height `plate_h`
   (expressions). `Pad` → `plate_t`.
5. Front face (towards you = back of plate against wall). Sketch the **two
   lugs**: two squares of `lug_size` withdrawn 5 mm from plate top and bottom
   edges, centers separated by `lug_pitch_y` vertically, centered on the
   plate's vertical axis. `Pad` the lugs outward (‑Z or +Z depending on view)
   by `toggle_depth`+`plate_t` so they protrude beyond the plate back.
6. **Toggle lip:** on the *outer end* of each lug, add a small square boss
   `toggle_lip` × `lug_size` × 2 mm so it hooks behind the sheet. (May need a
   pocket first to create the hook seat — iterate to taste; keep the lip
   on the side that faces the adjacent hole, QDN-style.)
7. Axle holder (pylon style, connects itself — no manual fusion needed):
   Parts in one Body are welded automatically when they touch or overlap.
   - On the plate's **front face**, sketch a rectangle (suggest `seat_depth`
     14 mm wide along X × 26 mm tall) centered on the plate's vertical axis.
     `Pad` outward by `standoff + sleeve_od/2 - plate_t` → a block sticking
     out of the plate to just past the rod line. This pads *from the face*
     like the lugs, so it welds to the plate.
   - Sketch a circle `axle_dia` on the **YZ plane** (side view, normal = X,
     the rod axis) at the rod position (Y = plate mid-height, Z = `standoff`
     from the wall), `Pocket` **Through all** along X → the bore for the M6
     rod. The outer nut presses against the bracket's outer face.
     *A bore drawn as construction (internal) geometry does NOT cut — it must
     be a real Pocket, or the profile of a ring-shaped pad.*
   Repeat for the second bracket (same file or a copy).
8. Save. Adjust lug/lip geometry by eyeballing against Wall (Step C).
9. **Print friendliness:** keep the lugs short and the lip small so no
   supports are needed; plate faces the build plate with lugs up.

### Step C — Assembly fit check (`Assembly.FCStd`)

1. New document → **Assembly workbench** (`Assembly`); saved as `Assembly.FCStd`.
2. Insert `Wall_QDN` (imported Part) → Insert `SpoolHolder` (bracket 1) → ground wall.
3. Use **Planar/coincident** + offsets to seat the two lugs in two wall holes
   that are **38 mm apart vertically**; align the axle sleeve axis parallel to
   the wall plane (it already is).
4. Check with *Move* / *View*: lugs pass through cleanly, lip hooks behind
   the sheet, sleeve runs parallel to wall, no interferences.
5. Note any fit issues → adjust `lug_size`, `toggle_depth/lip` in the
   SpoolHolder spreadsheet.
6. For the full system check link bracket 2 at the rod's other end plus a
   simple rod ∅6.5 cylinder + spool cylinders (∅70, 100 wide) on the bore axis;
   confirm overall clearance.

### Step D — Verification (headless, single command)

After modeling, run:

```
nix-shell --run "freecadcmd --console verify_fixture.py"
```

`verify_fixture.py` (see §7) loads the two `.FCStd` files and reports PASS/FAIL
with exit code 0/1:
- Wall: hole size 10 mm, pitch 38 mm, grid 32×6, bbox 1268×190×~1.2 mm,
  computed volume matches solid-minus-holes within tolerance.
- Bracket: lug centers 38 mm, lug size ~8.8 mm, sleeve bore ≥ M6, axis
  horizontal.
- Assembly presence: `Assembly_QDN.FCStd` exists (manual fit already done).

---

## 7. BOM & print notes

| # | Item | Detail |
|---|---|---|
| 1 | **SpoolHolder.FCStd** → printed | PLA/PETG, 0.2 mm, ~2–3 walls, ~25 % infill |
| 2 | M6 threaded rod | cut to `rod_len`; clean the threads on the spool section |
| 3 | M6 nyloc nut | retainer at rod tip (no printed cap needed) |
| 4 | (optional) bushings | Ø17/18/19/20 → 6 mm ID, printed, to take up bore slop |

Torque note (for 3–4 spools ≈ 1 kg ≈ 9.8 N static):
- Tilt/pry moment from unspooling pull ≈ 0.08 N·m → only ≈ 2 N per lug.
- Two lugs at 38 mm exist for **rigidity/stability** (no rocking/pivot),
  not because single-lug would fail.

---

## 8. Open items

- Measure actual `spool_w` (flange-to-flange) → set in spreadsheet.
- Confirm rod length for your 3–4 spools vs splitting to two rods.
- After first print: fine-tune `lug_size`/`toggle_lip`.