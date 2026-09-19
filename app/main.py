from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
import csv, math, uuid

from .db import connect, init_db
from .security import hash_password, verify_password, new_token
from .services import project_snapshot, project_stats, generate_revisions, log_action
from .config import VIDEO_DIR, SEED_DEMO, required_env

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

app = FastAPI(title="FOTON Platform", version="2.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

class LoginIn(BaseModel):
    email: str
    password: str

class ProjectIn(BaseModel):
    customer_id: int
    name: str
    code: str
    site_name: str | None = None
    parcel: str | None = None
    coordinate_system: str = "LOCAL"
    start_date: str | None = None

class InspectionIn(BaseModel):
    result: str
    notes: str | None = None
    meter_from: float | None = None
    meter_to: float | None = None
    defect_type: str | None = None
    defect_meter: float | None = None
    defect_severity: str | None = "MEDIUM"
    defect_description: str | None = None

def rowdict(r):
    return dict(r) if r else None

def auth_user(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Oturum gerekli")
    token=authorization.split(" ",1)[1]
    with connect() as conn:
        u=conn.execute("""
            SELECT u.* FROM tokens t JOIN users u ON u.id=t.user_id
            WHERE t.token=? AND u.is_active=1
        """,(token,)).fetchone()
    if not u:
        raise HTTPException(401,"Geçersiz oturum")
    return rowdict(u)

def can_access_project(project_id:int,user:dict):
    if user["role"]=="admin":
        return True
    with connect() as conn:
        ok=conn.execute("""
            SELECT 1 FROM project_users WHERE project_id=? AND user_id=?
        """,(project_id,user["id"])).fetchone()
    return bool(ok)

def ensure_access(project_id:int,user:dict):
    with connect() as conn:
        p=conn.execute("SELECT * FROM projects WHERE id=?",(project_id,)).fetchone()
    if not p:
        raise HTTPException(404,"Proje bulunamadı")
    if not can_access_project(project_id,user):
        raise HTTPException(403,"Bu projeye erişim yok")
    return rowdict(p)

def seed():
    init_db()
    if not SEED_DEMO:
        return

    admin_email = required_env("FOTON_ADMIN_EMAIL").lower().strip()
    admin_password = required_env("FOTON_ADMIN_PASSWORD")
    field_email = required_env("FOTON_FIELD_EMAIL").lower().strip()
    field_password = required_env("FOTON_FIELD_PASSWORD")
    customer_email = required_env("FOTON_CUSTOMER_EMAIL").lower().strip()
    customer_password = required_env("FOTON_CUSTOMER_PASSWORD")

    with connect() as conn:
        if not conn.execute("SELECT 1 FROM customers WHERE code='DEMO'").fetchone():
            conn.execute("INSERT INTO customers(name,code) VALUES(?,?)",("Demo Insaat","DEMO"))
        customer_id=conn.execute("SELECT id FROM customers WHERE code='DEMO'").fetchone()["id"]

        users=[
            (admin_email,admin_password,"admin","FOTON Yonetici",None),
            (field_email,field_password,"field","FOTON Saha Ekibi",None),
            (customer_email,customer_password,"customer","Demo Musteri",customer_id),
        ]
        for email,pwd,role,name,cid in users:
            if not conn.execute("SELECT 1 FROM users WHERE email=?",(email,)).fetchone():
                conn.execute(
                    "INSERT INTO users(email,password_hash,role,display_name,customer_id) VALUES(?,?,?,?,?)",
                    (email,hash_password(pwd),role,name,cid)
                )

        if not conn.execute("SELECT 1 FROM projects WHERE code='151_8'").fetchone():
            conn.execute("""
                INSERT INTO projects(customer_id,name,code,site_name,parcel,coordinate_system,start_date)
                VALUES(?,?,?,?,?,?,?)
            """,(customer_id,"151/8 Parsel","151_8","Demo Konut Projesi","151/8","LOCAL","2026-09-01"))
        pid=conn.execute("SELECT id FROM projects WHERE code='151_8'").fetchone()["id"]

        for email in (field_email, customer_email):
            uid=conn.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()["id"]
            conn.execute("INSERT OR IGNORE INTO project_users(project_id,user_id) VALUES(?,?)",(pid,uid))

        if conn.execute("SELECT COUNT(*) c FROM lines WHERE project_id=?",(pid,)).fetchone()["c"]==0:
            demo=[
                ("H12-H13","H12","H13",1000,1000,1040,1000,"ATIKSU",300),
                ("H13-H14","H13","H14",1040,1000,1080,1020,"YAGMURSUYU",300),
                ("H14-H15","H14","H15",1080,1020,1125,1040,"HASAT",300),
                ("H15-H16","H15","H16",1125,1040,1160,1060,"YAGMURSUYU",400),
            ]
            node_ids={}
            for _,sn,en,x1,y1,x2,y2,*_ in demo:
                for code,x,y in ((sn,x1,y1),(en,x2,y2)):
                    if code not in node_ids:
                        conn.execute(
                            "INSERT OR IGNORE INTO nodes(project_id,node_code,x,y) VALUES(?,?,?,?)",
                            (pid,code,x,y)
                        )
                        node_ids[code]=conn.execute(
                            "SELECT id FROM nodes WHERE project_id=? AND node_code=?",(pid,code)
                        ).fetchone()["id"]
            for code,sn,en,x1,y1,x2,y2,typ,dia in demo:
                length=math.dist((x1,y1),(x2,y2))
                conn.execute("""
                    INSERT INTO lines(project_id,line_code,start_node_id,end_node_id,x1,y1,x2,y2,line_type,diameter_mm,length_m)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,(pid,code,node_ids[sn],node_ids[en],x1,y1,x2,y2,typ,dia,length))

            field_id=conn.execute("SELECT id FROM users WHERE email=?",(field_email,)).fetchone()["id"]
            lrows=conn.execute("SELECT id,line_code FROM lines WHERE project_id=? ORDER BY id",(pid,)).fetchall()
            for line,result,note in [
                (lrows[0],"OK","Hat uygun."),
                (lrows[1],"DEFECT","Conta problemi."),
                (lrows[2],"RECHECK","Tekrar kontrol gerekli."),
            ]:
                cur=conn.execute(
                    "INSERT INTO inspections(line_id,operator_user_id,result,notes) VALUES(?,?,?,?)",
                    (line["id"],field_id,result,note)
                )
                if result=="DEFECT":
                    conn.execute("""
                        INSERT INTO defects(inspection_id,defect_type,meter,severity,description)
                        VALUES(?,?,?,?,?)
                    """,(cur.lastrowid,"CONTA",18.35,"HIGH","Conta cikmasi / gorunmesi"))

@app.on_event("startup")
def startup():
    seed()

@app.get("/health")
def health():
    return {"status": "ok", "service": "foton-platform"}

@app.get("/")
def home():
    return FileResponse(STATIC/"index.html")

@app.post("/api/login")
def login(data:LoginIn):
    with connect() as conn:
        u=conn.execute("SELECT * FROM users WHERE email=?",(data.email.lower().strip(),)).fetchone()
        if not u or not verify_password(data.password,u["password_hash"]):
            raise HTTPException(401,"E-posta veya şifre hatalı")
        token=new_token()
        conn.execute("INSERT INTO tokens(token,user_id) VALUES(?,?)",(token,u["id"]))
        return {"token":token,"user":{"id":u["id"],"email":u["email"],"role":u["role"],"display_name":u["display_name"]}}

@app.get("/api/me")
def me(user=Depends(auth_user)):
    return user

@app.get("/api/customers")
def customers(user=Depends(auth_user)):
    if user["role"]!="admin":
        raise HTTPException(403)
    with connect() as conn:
        rows=conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
    return [rowdict(r) for r in rows]

@app.get("/api/projects")
def projects(user=Depends(auth_user)):
    with connect() as conn:
        if user["role"]=="admin":
            rows=conn.execute("""
                SELECT p.*,c.name customer_name FROM projects p
                JOIN customers c ON c.id=p.customer_id ORDER BY p.id DESC
            """).fetchall()
        else:
            rows=conn.execute("""
                SELECT p.*,c.name customer_name FROM projects p
                JOIN customers c ON c.id=p.customer_id
                JOIN project_users pu ON pu.project_id=p.id
                WHERE pu.user_id=? ORDER BY p.id DESC
            """,(user["id"],)).fetchall()
    return [rowdict(r) for r in rows]

@app.post("/api/projects")
def create_project(data:ProjectIn,user=Depends(auth_user)):
    if user["role"]!="admin":
        raise HTTPException(403,"Sadece yönetici proje oluşturabilir")
    with connect() as conn:
        try:
            cur=conn.execute("""
                INSERT INTO projects(customer_id,name,code,site_name,parcel,coordinate_system,start_date)
                VALUES(?,?,?,?,?,?,?)
            """,(data.customer_id,data.name,data.code,data.site_name,data.parcel,data.coordinate_system,data.start_date))
        except Exception as e:
            raise HTTPException(400,f"Proje oluşturulamadı: {e}")
        pid=cur.lastrowid
        # Yeni projeyi ilgili müşteri kullanıcılarına ve aktif saha kullanıcılarına otomatik bağla.
        related = conn.execute(
            "SELECT id FROM users WHERE is_active=1 AND (customer_id=? OR role='field')",
            (data.customer_id,)
        ).fetchall()
        for ru in related:
            conn.execute("INSERT OR IGNORE INTO project_users(project_id,user_id) VALUES(?,?)", (pid, ru["id"]))
    log_action(pid,user["id"],"PROJECT_CREATED",data.name)
    return {"id":pid}

@app.get("/api/projects/{project_id}")
def project_detail(project_id:int,user=Depends(auth_user)):
    p=ensure_access(project_id,user)
    stats=project_stats(project_id)
    return {"project":p,"stats":stats}

@app.get("/api/projects/{project_id}/lines")
def get_lines(project_id:int,user=Depends(auth_user)):
    ensure_access(project_id,user)
    project,lines=project_snapshot(project_id)
    return lines

@app.get("/api/projects/{project_id}/stats")
def stats(project_id:int,user=Depends(auth_user)):
    ensure_access(project_id,user)
    return project_stats(project_id)

@app.post("/api/projects/{project_id}/import-csv")
async def import_csv(project_id:int,file:UploadFile=File(...),replace:bool=Form(False),user=Depends(auth_user)):
    if user["role"]!="admin":
        raise HTTPException(403,"Sadece yönetici veri yükleyebilir")
    ensure_access(project_id,user)
    raw=(await file.read()).decode("utf-8-sig")
    reader=csv.DictReader(raw.splitlines())
    req={"line_code","start_node","end_node","x1","y1","x2","y2","line_type","diameter_mm"}
    if not req.issubset(set(reader.fieldnames or [])):
        raise HTTPException(400,f"Zorunlu kolonlar eksik: {sorted(req)}")
    rows=list(reader)
    errors=[]
    seen=set()
    for i,r in enumerate(rows,start=2):
        if r["line_code"] in seen:
            errors.append(f"Satır {i}: tekrarlı line_code {r['line_code']}")
        seen.add(r["line_code"])
        try:
            x1,y1,x2,y2=map(float,[r["x1"],r["y1"],r["x2"],r["y2"]])
            if x1==x2 and y1==y2:
                errors.append(f"Satır {i}: sıfır uzunluk")
        except:
            errors.append(f"Satır {i}: koordinat okunamadı")
    if errors:
        return {"ok":False,"errors":errors,"imported":0}

    with connect() as conn:
        if replace:
            conn.execute("DELETE FROM lines WHERE project_id=?",(project_id,))
            conn.execute("DELETE FROM nodes WHERE project_id=?",(project_id,))
        node_ids={}
        for r in rows:
            for code,x,y in [
                (r["start_node"],float(r["x1"]),float(r["y1"])),
                (r["end_node"],float(r["x2"]),float(r["y2"]))
            ]:
                if code not in node_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO nodes(project_id,node_code,x,y) VALUES(?,?,?,?)",
                        (project_id,code,x,y)
                    )
                    node_ids[code]=conn.execute(
                        "SELECT id FROM nodes WHERE project_id=? AND node_code=?",(project_id,code)
                    ).fetchone()["id"]

        for r in rows:
            x1,y1,x2,y2=map(float,[r["x1"],r["y1"],r["x2"],r["y2"]])
            length=float(r.get("length_m") or math.dist((x1,y1),(x2,y2)))
            try:
                conn.execute("""
                    INSERT INTO lines(project_id,line_code,start_node_id,end_node_id,x1,y1,x2,y2,line_type,diameter_mm,length_m)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,(project_id,r["line_code"],node_ids[r["start_node"]],node_ids[r["end_node"]],x1,y1,x2,y2,
                     r["line_type"],int(float(r["diameter_mm"])),length))
            except Exception as e:
                raise HTTPException(400,f"{r['line_code']} eklenemedi: {e}")

    rev,_,_=generate_revisions(project_id,user["id"])
    log_action(project_id,user["id"],"COORDINATES_IMPORTED",f"{len(rows)} hat / R{rev:02d}")
    return {"ok":True,"errors":[],"imported":len(rows),"revision":rev}

@app.post("/api/lines/{line_id}/inspections")
def create_inspection(line_id:int,data:InspectionIn,user=Depends(auth_user)):
    if user["role"] not in ("admin","field"):
        raise HTTPException(403,"Saha kaydı yetkisi yok")
    if data.result not in ("OK","DEFECT","RECHECK","NO_IMAGE"):
        raise HTTPException(400,"Geçersiz sonuç")
    with connect() as conn:
        line=conn.execute("SELECT * FROM lines WHERE id=?",(line_id,)).fetchone()
        if not line:
            raise HTTPException(404,"Hat bulunamadı")
        if not can_access_project(line["project_id"],user) and user["role"]!="admin":
            raise HTTPException(403)
        cur=conn.execute("""
            INSERT INTO inspections(line_id,operator_user_id,result,notes,meter_from,meter_to)
            VALUES(?,?,?,?,?,?)
        """,(line_id,user["id"],data.result,data.notes,data.meter_from,data.meter_to))
        iid=cur.lastrowid
        if data.defect_type:
            conn.execute("""
                INSERT INTO defects(inspection_id,defect_type,meter,severity,description)
                VALUES(?,?,?,?,?)
            """,(iid,data.defect_type,data.defect_meter,data.defect_severity or "MEDIUM",data.defect_description))
        project_id=line["project_id"]
    rev,_,_=generate_revisions(project_id,user["id"])
    log_action(project_id,user["id"],"INSPECTION_CREATED",f"line={line_id}, result={data.result}, R{rev:02d}")
    return {"inspection_id":iid,"revision":rev}

@app.post("/api/inspections/{inspection_id}/videos")
async def upload_video(inspection_id:int,file:UploadFile=File(...),user=Depends(auth_user)):
    if user["role"] not in ("admin","field"):
        raise HTTPException(403)
    with connect() as conn:
        row=conn.execute("""
            SELECT i.id,l.project_id FROM inspections i JOIN lines l ON l.id=i.line_id
            WHERE i.id=?
        """,(inspection_id,)).fetchone()
        if not row:
            raise HTTPException(404,"Görüntüleme kaydı bulunamadı")
        if user["role"]!="admin" and not can_access_project(row["project_id"],user):
            raise HTTPException(403)
        suffix=Path(file.filename or "").suffix.lower() or ".bin"
        stored=f"{uuid.uuid4().hex}{suffix}"
        path=VIDEO_DIR/stored
        size=0
        with path.open("wb") as f:
            while True:
                chunk=await file.read(1024*1024)
                if not chunk: break
                size += len(chunk)
                f.write(chunk)
        conn.execute("""
            INSERT INTO videos(inspection_id,original_name,stored_path,mime_type,size_bytes)
            VALUES(?,?,?,?,?)
        """,(inspection_id,file.filename or stored,stored,file.content_type,size))
    rev,_,_=generate_revisions(row["project_id"],user["id"])
    log_action(row["project_id"],user["id"],"VIDEO_UPLOADED",f"{file.filename or stored} / R{rev:02d}")
    return {"ok":True,"revision":rev,"size_bytes":size}

@app.get("/api/lines/{line_id}/history")
def line_history(line_id:int,user=Depends(auth_user)):
    with connect() as conn:
        line=conn.execute("SELECT * FROM lines WHERE id=?",(line_id,)).fetchone()
        if not line: raise HTTPException(404)
        ensure_access(line["project_id"],user)
        inspections=conn.execute("""
            SELECT i.*,u.display_name operator_name
            FROM inspections i JOIN users u ON u.id=i.operator_user_id
            WHERE i.line_id=? ORDER BY datetime(i.inspected_at) DESC,i.id DESC
        """,(line_id,)).fetchall()
        result=[]
        for i in inspections:
            d=dict(i)
            d["defects"]=[dict(x) for x in conn.execute("SELECT * FROM defects WHERE inspection_id=?",(i["id"],)).fetchall()]
            vids=[]
            for v in conn.execute("SELECT * FROM videos WHERE inspection_id=?",(i["id"],)).fetchall():
                vd=dict(v); vd["url"]=f'/api/videos/{v["id"]}/stream'; vids.append(vd)
            d["videos"]=vids
            result.append(d)
    return result

@app.get("/api/videos/{video_id}/stream")
def stream_video(video_id:int,user=Depends(auth_user)):
    with connect() as conn:
        v=conn.execute("""
            SELECT v.*, l.project_id
            FROM videos v
            JOIN inspections i ON i.id=v.inspection_id
            JOIN lines l ON l.id=i.line_id
            WHERE v.id=?
        """,(video_id,)).fetchone()
    if not v:
        raise HTTPException(404,"Video bulunamadı")
    ensure_access(v["project_id"],user)
    path=VIDEO_DIR/v["stored_path"]
    if not path.exists():
        raise HTTPException(404,"Video dosyası bulunamadı")
    return FileResponse(path,media_type=v["mime_type"] or "application/octet-stream",filename=v["original_name"])

@app.get("/api/projects/{project_id}/revisions")
def revisions(project_id:int,user=Depends(auth_user)):
    ensure_access(project_id,user)
    with connect() as conn:
        reports=[dict(r) for r in conn.execute("SELECT * FROM report_revisions WHERE project_id=? ORDER BY revision_no DESC",(project_id,)).fetchall()]
        cads=[dict(r) for r in conn.execute("SELECT * FROM cad_revisions WHERE project_id=? ORDER BY revision_no DESC",(project_id,)).fetchall()]
    return {"reports":reports,"cad":cads}

@app.post("/api/projects/{project_id}/generate")
def generate(project_id:int,user=Depends(auth_user)):
    ensure_access(project_id,user)
    if user["role"] not in ("admin","field"):
        raise HTTPException(403)
    rev,report,cad=generate_revisions(project_id,user["id"])
    log_action(project_id,user["id"],"REVISION_GENERATED",f"R{rev:02d}")
    return {"revision":rev,"report":report.name,"cad":cad.name}

@app.get("/api/reports/{revision_id}/download")
def report_download(revision_id:int,user=Depends(auth_user)):
    with connect() as conn:
        r=conn.execute("SELECT * FROM report_revisions WHERE id=?",(revision_id,)).fetchone()
    if not r: raise HTTPException(404)
    ensure_access(r["project_id"],user)
    return FileResponse(r["file_path"],media_type="application/pdf",filename=Path(r["file_path"]).name)

@app.get("/api/cad/{revision_id}/download")
def cad_download(revision_id:int,user=Depends(auth_user)):
    with connect() as conn:
        r=conn.execute("SELECT * FROM cad_revisions WHERE id=?",(revision_id,)).fetchone()
    if not r: raise HTTPException(404)
    ensure_access(r["project_id"],user)
    return FileResponse(r["file_path"],media_type="application/dxf",filename=Path(r["file_path"]).name)
