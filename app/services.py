from pathlib import Path
from io import StringIO
from datetime import datetime
import math

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from .db import connect
from .config import VIDEO_DIR, REPORT_DIR, CAD_DIR

def current_line_state(line_id: int):
    with connect() as conn:
        row = conn.execute("""
            SELECT i.*
            FROM inspections i
            WHERE i.line_id=?
            ORDER BY datetime(i.inspected_at) DESC, i.id DESC
            LIMIT 1
        """, (line_id,)).fetchone()
    return dict(row) if row else None

def project_snapshot(project_id: int):
    with connect() as conn:
        project = conn.execute("""
            SELECT p.*, c.name customer_name
            FROM projects p JOIN customers c ON c.id=p.customer_id
            WHERE p.id=?
        """, (project_id,)).fetchone()
        lines = conn.execute("""
            SELECT l.*,
                   ns.node_code start_node,
                   ne.node_code end_node
            FROM lines l
            JOIN nodes ns ON ns.id=l.start_node_id
            JOIN nodes ne ON ne.id=l.end_node_id
            WHERE l.project_id=?
            ORDER BY l.id
        """, (project_id,)).fetchall()

        enriched = []
        for l in lines:
            d = dict(l)
            latest = conn.execute("""
                SELECT i.*
                FROM inspections i
                WHERE i.line_id=?
                ORDER BY datetime(i.inspected_at) DESC, i.id DESC
                LIMIT 1
            """, (l["id"],)).fetchone()
            d["latest_inspection"] = dict(latest) if latest else None
            if latest:
                defects = conn.execute(
                    "SELECT * FROM defects WHERE inspection_id=? ORDER BY id",
                    (latest["id"],)
                ).fetchall()
                d["latest_defects"] = [dict(x) for x in defects]
            else:
                d["latest_defects"] = []
            enriched.append(d)
    return dict(project), enriched

def line_status(line):
    ins = line.get("latest_inspection")
    if not ins:
        return "NOT_INSPECTED"
    return ins["result"]

def project_stats(project_id: int):
    project, lines = project_snapshot(project_id)
    total = sum(l["length_m"] or 0 for l in lines)
    inspected = sum((l["length_m"] or 0) for l in lines if l["latest_inspection"])
    counts = {"OK":0,"DEFECT":0,"RECHECK":0,"NO_IMAGE":0,"NOT_INSPECTED":0}
    open_defects = 0
    for l in lines:
        s = line_status(l)
        counts[s] = counts.get(s,0)+1
        open_defects += sum(1 for d in l.get("latest_defects",[]) if not d["is_resolved"])
    return {
        "project": project,
        "line_count": len(lines),
        "total_length_m": round(total,2),
        "inspected_length_m": round(inspected,2),
        "remaining_length_m": round(total-inspected,2),
        "progress_pct": round(inspected/total*100,1) if total else 0,
        "counts": counts,
        "open_defects": open_defects,
    }

def build_dxf(project_id: int, revision_no: int):
    project, lines = project_snapshot(project_id)
    out = StringIO()
    def w(code, value):
        out.write(f"{code}\n{value}\n")

    layers = [
        ("FOTON_OK",3),
        ("FOTON_DEFECT",1),
        ("FOTON_RECHECK",2),
        ("FOTON_NO_IMAGE",6),
        ("FOTON_NOT_INSPECTED",8),
        ("FOTON_NODE",5),
        ("FOTON_TEXT",7),
    ]

    w(0,"SECTION");w(2,"HEADER");w(9,"$ACADVER");w(1,"AC1015");w(0,"ENDSEC")
    w(0,"SECTION");w(2,"TABLES")
    w(0,"TABLE");w(2,"LAYER");w(70,len(layers))
    for name,color in layers:
        w(0,"LAYER");w(2,name);w(70,0);w(62,color);w(6,"CONTINUOUS")
    w(0,"ENDTAB");w(0,"ENDSEC")
    w(0,"SECTION");w(2,"ENTITIES")

    for l in lines:
        state = line_status(l)
        layer = {
            "OK":"FOTON_OK",
            "DEFECT":"FOTON_DEFECT",
            "RECHECK":"FOTON_RECHECK",
            "NO_IMAGE":"FOTON_NO_IMAGE",
            "NOT_INSPECTED":"FOTON_NOT_INSPECTED",
        }.get(state,"FOTON_NOT_INSPECTED")

        w(0,"LINE");w(8,layer)
        w(10,l["x1"]);w(20,l["y1"]);w(30,0)
        w(11,l["x2"]);w(21,l["y2"]);w(31,0)

        for x,y in ((l["x1"],l["y1"]),(l["x2"],l["y2"])):
            w(0,"CIRCLE");w(8,"FOTON_NODE");w(10,x);w(20,y);w(30,0);w(40,0.75)

        mx=(l["x1"]+l["x2"])/2; my=(l["y1"]+l["y2"])/2
        label=f'{l["line_code"]} {l["line_type"]} Ø{l["diameter_mm"] or "-"}'
        w(0,"TEXT");w(8,"FOTON_TEXT");w(10,mx);w(20,my);w(30,0);w(40,1.2);w(1,label)

    # title text
    if lines:
        minx=min(min(l["x1"],l["x2"]) for l in lines)
        maxy=max(max(l["y1"],l["y2"]) for l in lines)
        w(0,"TEXT");w(8,"FOTON_TEXT");w(10,minx);w(20,maxy+5);w(30,0);w(40,2.5)
        w(1,f'FOTON - {project["name"]} - REV {revision_no:02d}')
    w(0,"ENDSEC");w(0,"EOF")

    path = CAD_DIR / f'{project["code"]}_R{revision_no:02d}.dxf'
    path.write_bytes(out.getvalue().encode("utf-8"))
    return path

def build_pdf(project_id: int, revision_no: int):
    project, lines = project_snapshot(project_id)
    stats = project_stats(project_id)
    path = REPORT_DIR / f'{project["code"]}_R{revision_no:02d}.pdf'

    c = canvas.Canvas(str(path), pagesize=landscape(A4))
    width, height = landscape(A4)

    c.setFont("Helvetica-Bold", 20)
    c.drawString(36, height-40, "FOTON KANAL GORUNTULEME RAPORU")
    c.setFont("Helvetica", 10)
    c.drawString(36, height-60, f'Proje: {project["name"]}')
    c.drawString(36, height-75, f'Musteri: {project["customer_name"]}')
    c.drawString(36, height-90, f'Koordinat Sistemi: {project["coordinate_system"]}')
    c.drawString(36, height-105, f'Revizyon: R{revision_no:02d}')
    c.drawString(36, height-120, f'Uretim: {datetime.now().strftime("%d.%m.%Y %H:%M")}')

    c.setFont("Helvetica-Bold", 11)
    c.drawString(36, height-150, f'Toplam hat: {stats["line_count"]}')
    c.drawString(170, height-150, f'Toplam uzunluk: {stats["total_length_m"]} m')
    c.drawString(350, height-150, f'Goruntulenen: {stats["inspected_length_m"]} m')
    c.drawString(530, height-150, f'Kalan: {stats["remaining_length_m"]} m')
    c.drawString(680, height-150, f'Acik kusur: {stats["open_defects"]}')

    headers = ["Hat","Baslangic","Bitis","Tip","Cap","Uzunluk","Son Durum","Son Kontrol"]
    xcols = [36,110,180,250,330,375,455,575]
    y = height-180
    c.setFont("Helvetica-Bold",8)
    for x,h in zip(xcols,headers):
        c.drawString(x,y,h)
    y -= 14
    c.setFont("Helvetica",8)

    for l in lines:
        ins=l["latest_inspection"]
        vals=[
            l["line_code"],l["start_node"],l["end_node"],l["line_type"],
            str(l["diameter_mm"] or "-"),f'{l["length_m"]:.2f}',
            line_status(l),
            ins["inspected_at"] if ins else "-"
        ]
        for x,v in zip(xcols,vals):
            c.drawString(x,y,str(v)[:28])
        y -= 13
        if y < 45:
            c.showPage()
            y = height-45

    c.save()
    return path

def generate_revisions(project_id: int, user_id: int):
    with connect() as conn:
        next_report = (conn.execute(
            "SELECT COALESCE(MAX(revision_no),0)+1 n FROM report_revisions WHERE project_id=?",
            (project_id,)
        ).fetchone()["n"])
        next_cad = (conn.execute(
            "SELECT COALESCE(MAX(revision_no),0)+1 n FROM cad_revisions WHERE project_id=?",
            (project_id,)
        ).fetchone()["n"])

    rev = max(next_report, next_cad)
    report_path = build_pdf(project_id, rev)
    cad_path = build_dxf(project_id, rev)

    with connect() as conn:
        conn.execute(
            "INSERT INTO report_revisions(project_id,revision_no,file_path,generated_by) VALUES(?,?,?,?)",
            (project_id, rev, str(report_path), user_id)
        )
        conn.execute(
            "INSERT INTO cad_revisions(project_id,revision_no,file_path,generated_by) VALUES(?,?,?,?)",
            (project_id, rev, str(cad_path), user_id)
        )
    return rev, report_path, cad_path

def log_action(project_id, user_id, action, detail=""):
    with connect() as conn:
        conn.execute(
            "INSERT INTO activity_log(project_id,user_id,action,detail) VALUES(?,?,?,?)",
            (project_id,user_id,action,detail)
        )
