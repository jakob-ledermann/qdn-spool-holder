#!/usr/bin/env python3
"""Headless export of the QDN spool-holder prints and web preview.

Usage:
    nix-shell --run "freecadcmd --console export_qdn.py"

Writes into exports/:
    SpoolHolder.stl    printable bracket (print twice)
    SpoolHolder.3mf    printable bracket (print twice)
    Assembly.glb       full-system preview (GLB 2.0)
    Assembly.html      full-system preview (stock FreeCAD WebGL viewer)

FreeCAD's own glTF/GLB exporter serialises nothing in headless mode, and
importers.importWebGL pulls in Qt/PySide6 which segfaults freecadcmd at
interpreter exit. So the GLB is written by a small built-in writer and the
HTML reuses the stock BIM WebGL template directly (non-compressed encoding,
documented in importers/importWebGL.py).
"""
import functools
import json
import math
import os
import struct
import sys

print = functools.partial(print, flush=True)

try:
    import FreeCAD as App
except ImportError:
    print("FreeCAD not importable - run inside: nix-shell")
    sys.exit(1)
import Mesh

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() \
    else os.getcwd()
BRACKET = os.path.join(HERE, "SpoolHolder.FCStd")
ASSEMBLY = os.path.join(HERE, "Assembly.FCStd")
OUT = os.path.join(HERE, "exports")

DEFL_BRACKET = 0.1   # mm linear deflection for the printable mesh
DEFL_ASM = 0.2       # mm for the preview meshes

THREEJS_VERSION = "0.172.0"  # matches the stock template / FreeCAD 1.1.3


def find_body(doc):
    for o in doc.Objects:
        if o.TypeId == "PartDesign::Body":
            return o
    return None


def global_shape(obj):
    """Shape in world/assembly coordinates (links resolved)."""
    if obj.isDerivedFrom("App::Link"):
        sh = obj.getLinkedObject(True).Shape.copy(False)
        lp = obj.LinkPlacement if hasattr(obj, "LinkPlacement") else obj.Placement
        sh.Placement = lp.multiply(sh.Placement)
        return sh
    return obj.Shape


def assembly_objects(doc):
    out = []
    for o in doc.Objects:
        if o.TypeId == "Assembly::AssemblyObject":
            continue
        if o.isDerivedFrom("App::Link"):
            out.append(o)
        elif o.TypeId == "Part::Feature" and o.Shape is not None \
                and o.Shape.Volume > 1e-6:
            out.append(o)
    return out


def mesh_of(shape, dev):
    m = Mesh.Mesh(shape.tessellate(dev))
    return None if m.CountPoints == 0 else m


# ------------------------------------------------------------------ GLB

def write_glb(mesh, path):
    """Write a minimal but valid glTF 2.0 binary (GLB) for a triangle mesh."""
    pos = [(p.Vector.x, p.Vector.y, p.Vector.z) for p in mesh.Points]
    n = len(pos)
    acc = [[0.0, 0.0, 0.0] for _ in range(n)]
    for f in mesh.Facets:
        i0, i1, i2 = f.PointIndices
        a, b, c = pos[i0], pos[i1], pos[i2]
        ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        nx, ny, nz = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
        L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        nx, ny, nz = nx / L, ny / L, nz / L
        for i in (i0, i1, i2):
            acc[i][0] += nx
            acc[i][1] += ny
            acc[i][2] += nz
    normals = []
    for (nx, ny, nz) in acc:
        L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
        normals.append((nx / L, ny / L, nz / L))
    indices = [v for f in mesh.Facets for v in f.PointIndices]

    pos_bytes = b"".join(struct.pack("<fff", *p) for p in pos)
    norm_bytes = b"".join(struct.pack("<fff", *p) for p in normals)
    idx_bytes = struct.pack("<%dI" % len(indices), *indices)
    bin_data = pos_bytes + norm_bytes + idx_bytes
    bin_data += b"\x00" * ((-len(bin_data)) % 4)

    minp = [min(p[i] for p in pos) for i in range(3)]
    maxp = [max(p[i] for p in pos) for i in range(3)]

    pos_off = 0
    norm_off = len(pos_bytes)
    idx_off = len(pos_bytes) + len(norm_bytes)

    def accessor(component, count, ctype, view, offset, mnmx=None):
        a = {"bufferView": view,
             "byteOffset": offset,
             "componentType": component,
             "count": count,
             "type": ctype}
        if mnmx:
            a["min"] = mnmx[0]
            a["max"] = mnmx[1]
        return a

    views = [
        {"buffer": 0, "byteOffset": pos_off, "byteLength": len(pos_bytes)},
        {"buffer": 0, "byteOffset": norm_off, "byteLength": len(norm_bytes)},
        {"buffer": 0, "byteOffset": idx_off, "byteLength": len(idx_bytes)},
    ]
    accs = [
        accessor(5126, n, "VEC3", 0, pos_off, (minp, maxp)),
        accessor(5126, n, "VEC3", 1, norm_off),
        accessor(5125, len(indices), "SCALAR", 2, idx_off),
    ]
    doc = {
        "asset": {"version": "2.0", "generator": "export_qdn.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0, "NORMAL": 1},
            "indices": 2,
            "material": 0,
        }]}],
        "materials": [{
            "name": "Part",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.8, 0.8, 0.8, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.9,
            },
            "doubleSided": True,
        }],
        "buffers": [{"byteLength": len(bin_data)}],
        "bufferViews": views,
        "accessors": accs,
    }
    payload = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((-len(payload)) % 4)
    bin_chunk = struct.pack("<I", len(bin_data)) + b"BIN\x00"[:4] + bin_data
    json_chunk = struct.pack("<I", len(payload)) + b"JSON" + payload
    total = 12 + len(json_chunk) + len(bin_chunk)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(json_chunk)
        fh.write(bin_chunk)


# ------------------------------------------------------------------ HTML

def write_html(objects, path):
    """Replicate importWebGL's non-compressed export against the stock
    template ($pagetitle, $version, $data, $threejs_version)."""
    template_path = os.path.join(
        App.getResourceDir(), "Mod", "BIM", "Resources", "templates",
        "webgl_export_template.html")
    with open(template_path, "r", encoding="utf-8") as fh:
        html = fh.read()

    objs = []
    for o in objects:
        sh = global_shape(o)
        m = mesh_of(sh, DEFL_ASM)
        if m is None:
            continue
        vindex = {}
        verts = []
        for p in m.Points:
            vindex[p.Index] = p.Index
            verts.extend("%.5f" % v for v in (p.Vector.x, p.Vector.y,
                                              p.Vector.z))
        facets = [vindex[i] for f in m.Facets for i in f.PointIndices]
        objs.append({
            "name": o.Label,
            "color": "#cccccc",
            "opacity": 1.0,
            "verts": verts,
            "facets": facets,
            "wires": [],
            "faceColors": [],
            "facesToFacets": [],
            "floats": [],
        })

    bounds = [min(float(v) for o in objs for v in o["verts"][i::3])
              for i in range(3)]
    bounds_m = [max(float(v) for o in objs for v in o["verts"][i::3])
                for i in range(3)]
    center = [0.5 * (bounds_m[i] + bounds[i]) for i in range(3)]
    bigrange = max(bounds_m[i] - bounds[i] for i in range(3))
    dirx, diry, dirz = -0.45, -0.55, 0.85
    L = math.sqrt(dirx * dirx + diry * diry + dirz * dirz)
    pos = [center[i] + [dirx, diry, dirz][i] / L * 1.6 * bigrange
           for i in range(3)]

    data = {
        "camera": {
            "type": "Perspective",
            "position_x": pos[0],
            "position_y": pos[1],
            "position_z": pos[2],
            "focalDistance": bigrange,
        },
        "file": {},
        "objects": objs,
        "compressed": False,
        "base": ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                 "1234567890!#$%&()*+-:;/=>?@[]^_,.{|}~`"),
        "baseFloat": ",.-0123456789",
    }
    version = App.Version()
    html = html.replace("$pagetitle", "QDN Spool Holder Assembly")
    html = html.replace("$version",
                        ".".join(str(v) for v in version[:3]))
    html = html.replace("$threejs_version", THREEJS_VERSION)
    html = html.replace("$data", json.dumps(data, separators=(",", ":")))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)


# ------------------------------------------------------------------ main

def main():
    os.makedirs(OUT, exist_ok=True)
    results = []

    print("== export_qdn.py ==")
    print("opening SpoolHolder.FCStd")
    brk = App.openDocument(BRACKET, True)
    brk.recompute()
    body = find_body(brk)
    if body is None:
        print("ERROR: no PartDesign body in SpoolHolder.FCStd")
        return 1
    bracket_mesh = mesh_of(body.Shape, DEFL_BRACKET)
    if bracket_mesh is None:
        print("ERROR: bracket produced no mesh")
        return 1

    for ext in ("stl", "3mf"):
        target = os.path.join(OUT, "SpoolHolder.%s" % ext)
        bracket_mesh.write(target)
        results.append(target)
        print("  wrote %-28s %8d bytes" % (os.path.basename(target),
                                            os.path.getsize(target)))
    App.closeDocument(brk.Name)

    print("opening Assembly.FCStd")
    asm = App.openDocument(ASSEMBLY, True)
    asm.recompute()
    objs = assembly_objects(asm)
    if not objs:
        print("ERROR: no exportable objects in Assembly.FCStd")
        return 1
    print("  assembly objects: %s" % ", ".join(o.Label for o in objs))

    glb_target = os.path.join(OUT, "Assembly.glb")
    merged = Mesh.Mesh()
    for o in objs:
        m = mesh_of(global_shape(o), DEFL_ASM)
        if m is not None:
            merged.addMesh(m)
    if merged.CountPoints == 0:
        print("ERROR: assembly produced no mesh")
        return 1
    write_glb(merged, glb_target)
    results.append(glb_target)
    print("  wrote %-28s %8d bytes" % (os.path.basename(glb_target),
                                        os.path.getsize(glb_target)))

    html_target = os.path.join(OUT, "Assembly.html")
    write_html(objs, html_target)
    results.append(html_target)
    print("  wrote %-28s %8d bytes" % (os.path.basename(html_target),
                                        os.path.getsize(html_target)))
    App.closeDocument(asm.Name)

    ok = True
    for p in results:
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            ok = False
    if os.path.exists(glb_target) and \
            open(glb_target, "rb").read(4) != b"glTF":
        ok = False
        print("ERROR: Assembly.glb is not a valid GLB")
    print("EXPORT RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())