"""Lee un STEP de ensamble (Onshape) y saca la silueta vista desde arriba.

Salida (JSON): por instancia de pieza, la envolvente convexa XY en pulgadas, mas su nombre y su altura Z.
Uso: python3 -I step_topview.py archivo.step salida.json
"""
import json
import math
import re
import sys

M_TO_IN = 39.37007874

ref_re = re.compile(r"#(\d+)")


def load(path):
    ents = {}
    buf = []
    in_data = False
    with open(path, "r", errors="replace") as f:
        for line in f:
            if not in_data:
                if line.startswith("DATA;"):
                    in_data = True
                continue
            if line.startswith("ENDSEC"):
                break
            buf.append(line.rstrip("\n"))
            if line.rstrip().endswith(";"):
                stmt = "".join(buf).strip()
                buf = []
                m = re.match(r"#(\d+)\s*=\s*(.*);$", stmt, re.S)
                if not m:
                    continue
                eid = int(m.group(1))
                body = m.group(2).strip()
                tm = re.match(r"([A-Z_0-9]+)\s*\((.*)\)$", body, re.S)
                if tm:
                    ents[eid] = (tm.group(1), tm.group(2))
                else:
                    ents[eid] = ("", body)
    return ents


def split_args(s):
    """Separa argumentos de nivel superior respetando parentesis y strings."""
    out, depth, cur, in_str = [], 0, [], False
    i = 0
    while i < len(s):
        c = s[i]
        if in_str:
            cur.append(c)
            if c == "'":
                if i + 1 < len(s) and s[i + 1] == "'":
                    cur.append("'")
                    i += 1
                else:
                    in_str = False
        elif c == "'":
            in_str = True
            cur.append(c)
        elif c == "(":
            depth += 1
            cur.append(c)
        elif c == ")":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    if cur:
        out.append("".join(cur).strip())
    return out


def refs(s):
    return [int(x) for x in ref_re.findall(s)]


def nums(s):
    return [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)]


def main(path, outp):
    ents = load(path)
    print("entidades", len(ents), file=sys.stderr)

    def point(eid):
        t, a = ents[eid]
        args = split_args(a)
        return nums(args[1])[:3]

    def direction(eid):
        t, a = ents[eid]
        args = split_args(a)
        v = nums(args[1])[:3]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def placement(eid):
        """AXIS2_PLACEMENT_3D -> (origen, eje z, eje x)."""
        t, a = ents[eid]
        args = split_args(a)
        o = point(refs(args[1])[0])
        z = direction(refs(args[2])[0]) if args[2] != "$" else [0, 0, 1]
        x = direction(refs(args[3])[0]) if args[3] != "$" else [1, 0, 0]
        # ortonormalizar x respecto a z
        d = sum(x[i] * z[i] for i in range(3))
        x = [x[i] - d * z[i] for i in range(3)]
        n = math.sqrt(sum(v * v for v in x)) or 1.0
        x = [v / n for v in x]
        y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
        return o, x, y, z

    def mat_from_place(p):
        o, x, y, z = p
        # columnas = ejes; T(v) = o + R v
        return [[x[0], y[0], z[0], o[0]], [x[1], y[1], z[1], o[1]], [x[2], y[2], z[2], o[2]]]

    def mat_inv(m):
        r = [[m[j][i] for j in range(3)] for i in range(3)]
        t = [-(r[i][0] * m[0][3] + r[i][1] * m[1][3] + r[i][2] * m[2][3]) for i in range(3)]
        return [r[0] + [t[0]], r[1] + [t[1]], r[2] + [t[2]]]

    def mat_mul(a, b):
        out = []
        for i in range(3):
            row = []
            for j in range(4):
                v = sum(a[i][k] * b[k][j] for k in range(3))
                if j == 3:
                    v += a[i][3]
                row.append(v)
            out.append(row)
        return out

    def apply(m, p):
        return [m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3)]

    ident = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0]]

    # ---- puntos de cada BREP ----
    SKIP = {"PLANE", "CYLINDRICAL_SURFACE", "CONICAL_SURFACE", "SPHERICAL_SURFACE", "TOROIDAL_SURFACE",
            "DEGENERATE_TOROIDAL_SURFACE", "B_SPLINE_SURFACE_WITH_KNOTS", "SURFACE_OF_REVOLUTION",
            "SURFACE_OF_LINEAR_EXTRUSION", "LINE", "AXIS2_PLACEMENT_3D", "DIRECTION", "VECTOR",
            "PRESENTATION_STYLE_ASSIGNMENT", "STYLED_ITEM", "OVER_RIDING_STYLED_ITEM", ""}

    def brep_points(bid):
        pts = []
        seen = set()
        stack = [bid]
        while stack:
            e = stack.pop()
            if e in seen or e not in ents:
                continue
            seen.add(e)
            t, a = ents[e]
            if t == "VERTEX_POINT":
                pts.append(point(refs(a)[0]))
                continue
            if t == "CARTESIAN_POINT":
                pts.append(point(e))
                continue
            if t in ("CIRCLE", "ELLIPSE"):
                args = split_args(a)
                p = placement(refs(args[1])[0])
                r1 = nums(args[2])[0]
                r2 = nums(args[3])[0] if t == "ELLIPSE" else r1
                o, x, y, z = p
                if max(r1, r2) > 0.0254:  # arcos de mas de 1 in: solo sus vertices (no el circulo completo)
                    stack.extend(refs(a))
                    continue
                for k in range(16):
                    th = 2 * math.pi * k / 16
                    c, s = math.cos(th) * r1, math.sin(th) * r2
                    pts.append([o[i] + c * x[i] + s * y[i] for i in range(3)])
                continue
            if t in SKIP:
                continue
            if t == "B_SPLINE_CURVE_WITH_KNOTS":
                for r in refs(a):
                    if ents.get(r, ("",))[0] == "CARTESIAN_POINT":
                        pts.append(point(r))
                continue
            stack.extend(refs(a))
        return pts

    # ---- representaciones ----
    # SHAPE_DEFINITION_REPRESENTATION(PRODUCT_DEFINITION_SHAPE -> PD, SHAPE_REPRESENTATION)
    pds_to_pd = {}
    for e, (t, a) in ents.items():
        if t == "PRODUCT_DEFINITION_SHAPE":
            r = refs(a)
            if r:
                pds_to_pd[e] = r[-1]
    pd_to_rep = {}
    for e, (t, a) in ents.items():
        if t == "SHAPE_DEFINITION_REPRESENTATION":
            r = refs(a)
            if len(r) >= 2 and r[0] in pds_to_pd:
                pd_to_rep[pds_to_pd[r[0]]] = r[1]

    # SHAPE_REPRESENTATION_RELATIONSHIP sin transformacion: une SHAPE_REPRESENTATION con la de breps
    rep_links = {}
    for e, (t, a) in ents.items():
        if t in ("SHAPE_REPRESENTATION_RELATIONSHIP",):
            r = refs(a)
            if len(r) >= 2:
                rep_links.setdefault(r[0], []).append(r[1])
                rep_links.setdefault(r[1], []).append(r[0])
    BREPS = {"MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS"}

    def rep_breps(rep):
        out = []
        todo = [rep]
        seen = set()
        while todo:
            r = todo.pop()
            if r in seen:
                continue
            seen.add(r)
            t, a = ents[r]
            args = split_args(a)
            for it in refs(args[1]) if len(args) > 1 else []:
                if ents.get(it, ("",))[0] in BREPS:
                    out.append(it)
            for l in rep_links.get(r, []):
                if ents.get(l, ("",))[0] in ("ADVANCED_BREP_SHAPE_REPRESENTATION", "MANIFOLD_SURFACE_SHAPE_REPRESENTATION"):
                    todo.append(l)
        return out

    # ---- nombres ----
    pd_name = {}
    for e, (t, a) in ents.items():
        if t == "PRODUCT_DEFINITION":
            r = refs(a)
            if r:
                pdf = ents.get(r[0])
                if pdf:
                    pr = refs(pdf[1])
                    if pr and ents.get(pr[0], ("",))[0] == "PRODUCT":
                        m = re.match(r"\s*'((?:[^']|'')*)'", ents[pr[0]][1])
                        pd_name[e] = m.group(1) if m else "?"

    # ---- arbol del ensamble ----
    # NAUO(id,name,desc, parentPD, childPD, $)
    nauo = {}
    children = {}
    for e, (t, a) in ents.items():
        if t == "NEXT_ASSEMBLY_USAGE_OCCURRENCE":
            r = refs(a)
            parent, child = r[0], r[1]
            nauo[e] = (parent, child)
    # CDSR( RRWT , PDS(nauo) )
    pds_of = {e: refs(a)[-1] for e, (t, a) in ents.items() if t == "PRODUCT_DEFINITION_SHAPE"}
    for e, (t, a) in ents.items():
        if t == "CONTEXT_DEPENDENT_SHAPE_REPRESENTATION":
            rr, pds = refs(a)[:2]
            n = pds_of.get(pds)
            if n not in nauo:
                continue
            # RRWT es entidad compleja: buscar rep_1, rep_2 y la ITEM_DEFINED_TRANSFORMATION
            t2, a2 = ents[rr]
            rlist = refs(a2)
            idt = [x for x in rlist if ents.get(x, ("",))[0] == "ITEM_DEFINED_TRANSFORMATION"]
            reps = [x for x in rlist if ents.get(x, ("",))[0] != "ITEM_DEFINED_TRANSFORMATION"]
            if not idt:
                continue
            p1, p2 = refs(ents[idt[0]][1])[:2]
            m = mat_mul(mat_from_place(placement(p2)), mat_inv(mat_from_place(placement(p1))))
            parent, child = nauo[n]
            children.setdefault(parent, []).append((child, m, reps))

    all_children = {c for v in children.values() for c, _, _ in v}
    roots = [p for p in children if p not in all_children]
    print("raices", [pd_name.get(r) for r in roots], file=sys.stderr)

    brep_cache = {}
    parts = []

    def walk(pd, m, path):
        rep = pd_to_rep.get(pd)
        if rep is not None:
            for b in rep_breps(rep):
                if b not in brep_cache:
                    brep_cache[b] = brep_points(b)
                pts = [apply(m, p) for p in brep_cache[b]]
                if pts:
                    parts.append({"name": pd_name.get(pd, "?"), "path": path, "pts": pts})
        for child, cm, reps in children.get(pd, []):
            walk(child, mat_mul(m, cm), path + [pd_name.get(child, "?")])

    for r in roots:
        walk(r, ident, [pd_name.get(r, "?")])
    print("instancias con geometria", len(parts), file=sys.stderr)

    def hull(points):
        pts = sorted(set((round(p[0], 3), round(p[1], 3)) for p in points))
        if len(pts) <= 2:
            return pts

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lo, up = [], []
        for p in pts:
            while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
                lo.pop()
            lo.append(p)
        for p in reversed(pts):
            while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
                up.pop()
            up.append(p)
        return lo[:-1] + up[:-1]

    # Filtra puntos absurdos (control points / circulos gigantes): fuera de 30 in del centro mediano
    def med(v):
        v = sorted(v); return v[len(v) // 2]
    centers = []
    for p in parts:
        P = p["pts"]
        centers.append([med([q[i] for q in P]) for i in range(3)])
    C0 = [med([c[i] for c in centers]) for i in range(3)]
    LIM = 30 / M_TO_IN
    out = []
    for p in parts:
        Pm = [q for q in p["pts"] if all(abs(q[i] - C0[i]) < LIM for i in range(3))]
        if len(Pm) < 3:
            continue
        P = [[v * M_TO_IN for v in q] for q in Pm]
        xs = [q[0] for q in P]; ys = [q[1] for q in P]; zs = [q[2] for q in P]
        out.append({
            "name": p["name"], "path": p["path"],
            "hullXY": hull(P), "hullXZ": hull([[q[0], q[2]] for q in P]), "hullYZ": hull([[q[1], q[2]] for q in P]),
            "bbox": [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)],
        })
    json.dump(out, open(outp, "w"))
    allx = [b for o in out for b in (o["bbox"][0], o["bbox"][3])]
    ally = [b for o in out for b in (o["bbox"][1], o["bbox"][4])]
    allz = [b for o in out for b in (o["bbox"][2], o["bbox"][5])]
    print("bbox in: x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f" % (min(allx), max(allx), min(ally), max(ally), min(allz), max(allz)), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
