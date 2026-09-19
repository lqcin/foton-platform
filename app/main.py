from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime, timedelta, timezone
import csv, math, uuid

from .db import connect, init_db
from .security import (
    hash_password, verify_password, validate_password, new_token,
    token_hash, generate_temp_password
)
from .services import project_snapshot, project_stats, generate_revisions, log_action
from .config import (
    VIDEO_DIR, SEED_DEMO, required_env, SESSION_HOURS, RESET_TOKEN_MINUTES
)

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"

app = FastAPI(title="FOTON Platform", version="3.0.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

class LoginIn(BaseModel):
    email: str
    password: str

class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

class ResetPasswordIn(BaseModel):
    token: str
    new_password: str

class AdminUserIn(BaseModel):
    email: str
    display_name: str
    role: str
    customer_id: int | None = None
    project_ids: list[int] = []
    temporary_password: str | None = None

class UserStatusIn(BaseModel):
    is_active: bool

class CustomerIn(BaseModel):
    name: str
    code: str

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

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime) -> str:
    return dt.isoformat()

def rowdict(r):
    return dict(r) if r else None

def auth_user(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Oturum gerekli")
    token = authorization.split(" ",1)[1]
    with connect() as conn:
        u=conn.execute("""
            SELECT u.* FROM tokens t JOIN users u ON u.id=t.user_id
            WHERE t.token=? AND u.is_active=1
              AND t.revoked_at IS NULL
              AND (t.expires_at IS NULL OR datetime(t.expires_at) > datetime('now'))
        """,(token,)).fetchone()
    if not u:
        raise HTTPException(401,"Geçersiz veya süresi dolmuş oturum")
    d = rowdict(u)
    d["_token"] = token
    return d

def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "display_name": user["display_name"],
        "customer_id": user.get("customer_id"),
        "is_active": user.get("is_active", 1),
        "must_change_password": user.get("must_change_password", 0),
        "last_login_at": user.get("last_login_at"),
    }

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
                    """INSERT INTO users(
                        email,password_hash,role,display_name,customer_id,must_change_password,password_changed_at
                    ) VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                    (email,hash_password(pwd),role,name,cid,0)
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
    return {"status": "ok", "service": "foton-platform", "version": "3.0.0"}

@app.get("/")
def home():
    return FileResponse(STATIC/"index.html")

@app.post("/api/login")
def login(data:LoginIn):
    email = data.email.lower().strip()
    with connect() as conn:
        u=conn.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if not u or not u["is_active"] or not verify_password(data.password,u["password_hash"]):
            raise HTTPException(401,"E-posta veya şifre hatalı")
        token=new_token()
        expires_at = iso(utcnow() + timedelta(hours=SESSION_HOURS))
        conn.execute(
            "INSERT INTO tokens(token,user_id,expires_at) VALUES(?,?,?)",
            (token,u["id"],expires_at)
        )
        conn.execute("UPDATE users SET last_login_at=CURRENT_TIMESTAMP WHERE id=?",(u["id"],))
        u = conn.execute("SELECT * FROM users WHERE id=?",(u["id"],)).fetchone()
        return {"token":token,"expires_at":expires_at,"user":public_user(dict(u))}

@app.post("/api/logout")
def logout_api(user=Depends(auth_user)):
    with connect() as conn:
        conn.execute("UPDATE tokens SET revoked_at=CURRENT_TIMESTAMP WHERE token=?",(user["_token"],))
    return {"ok": True}

@app.get("/api/me")
def me(user=Depends(auth_user)):
    return public_user(user)

@app.post("/api/change-password")
def change_password(data: ChangePasswordIn, user=Depends(auth_user)):
    ok, message = validate_password(data.new_password)
    if not ok:
        raise HTTPException(400, message)
    with connect() as conn:
        u = conn.execute("SELECT * FROM users WHERE id=?",(user["id"],)).fetchone()
        if not u or not verify_password(data.current_password, u["password_hash"]):
            raise HTTPException(400, "Mevcut şifre hatalı.")
        if verify_password(data.new_password, u["password_hash"]):
            raise HTTPException(400, "Yeni şifre mevcut şifreyle aynı olamaz.")
        conn.execute("""
            UPDATE users
            SET password_hash=?, must_change_password=0, password_changed_at=CURRENT_TIMESTAMP
            WHERE id=?
        """,(hash_password(data.new_password),user["id"]))
        # Bu oturum dışındaki token'ları kapat.
        conn.execute("""
            UPDATE tokens SET revoked_at=CURRENT_TIMESTAMP
            WHERE user_id=? AND token<>? AND revoked_at IS NULL
        """,(user["id"],user["_token"]))
    return {"ok":True}

@app.post("/api/password-reset/complete")
def complete_password_reset(data: ResetPasswordIn):
    ok, message = validate_password(data.new_password)
    if not ok:
        raise HTTPException(400, message)
    th = token_hash(data.token)
    with connect() as conn:
        r = conn.execute("""
            SELECT * FROM password_reset_tokens
            WHERE token_hash=? AND used_at IS NULL
              AND datetime(expires_at) > datetime('now')
        """,(th,)).fetchone()
        if not r:
            raise HTTPException(400, "Sıfırlama bağlantısı geçersiz veya süresi dolmuş.")
        conn.execute("""
            UPDATE users SET password_hash=?, must_change_password=0,
                password_changed_at=CURRENT_TIMESTAMP
            WHERE id=?
        """,(hash_password(data.new_password),r["user_id"]))
        conn.execute("UPDATE password_reset_tokens SET used_at=CURRENT_TIMESTAMP WHERE id=?",(r["id"],))
        conn.execute("UPDATE tokens SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=? AND revoked_at IS NULL",(r["user_id"],))
    return {"ok":True}

@app.get("/api/admin/users")
def admin_users(user=Depends(auth_user)):
    if user["role"]!="admin":
        raise HTTPException(403)
    with connect() as conn:
        rows=conn.execute("""
            SELECT u.id,u.email,u.display_name,u.role,u.customer_id,u.is_active,
                   u.must_change_password,u.created_at,u.last_login_at,
                   c.name customer_name,
                   COUNT(pu.project_id) project_count
            FROM users u
            LEFT JOIN customers c ON c.id=u.customer_id
            LEFT JOIN project_users pu ON pu.user_id=u.id
            GROUP BY u.id
            ORDER BY u.role,u.display_name
        """).fetchall()
    return [dict(r) for r in rows]

@app.post("/api/admin/users")
def create_user(data: AdminUserIn, user=Depends(auth_user)):
    if user["role"]!="admin":
        raise HTTPException(403)
    if data.role not in ("admin","field","customer"):
        raise HTTPException(400,"Geçersiz rol.")
    if data.role=="customer" and not data.customer_id:
        raise HTTPException(400,"Müşteri kullanıcısı için firma seçilmeli.")
    temp = data.temporary_password or generate_temp_password()
    ok, message = validate_password(temp)
    if not ok:
        raise HTTPException(400,message)
    email = data.email.lower().strip()
    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email=?",(email,)).fetchone():
            raise HTTPException(400,"Bu e-posta zaten kayıtlı.")
        cur = conn.execute("""
            INSERT INTO users(
                email,password_hash,role,display_name,customer_id,is_active,
                must_change_password
            ) VALUES(?,?,?,?,?,1,1)
        """,(email,hash_password(temp),data.role,data.display_name.strip(),data.customer_id))
        uid = cur.lastrowid
        project_ids = list(data.project_ids)
        if data.role=="customer" and data.customer_id and not project_ids:
            project_ids=[r["id"] for r in conn.execute(
                "SELECT id FROM projects WHERE customer_id=?",(data.customer_id,)
            ).fetchall()]
        if data.role=="field" and not project_ids:
            project_ids=[r["id"] for r in conn.execute(
                "SELECT id FROM projects WHERE status='ACTIVE'"
            ).fetchall()]
        for pid in project_ids:
            conn.execute("INSERT OR IGNORE INTO project_users(project_id,user_id) VALUES(?,?)",(pid,uid))
    return {"id":uid,"temporary_password":temp,"must_change_password":True}

@app.patch("/api/admin/users/{user_id}/status")
def set_user_status(user_id:int, data:UserStatusIn, user=Depends(auth_user)):
    if user["role"]!="admin":
        raise HTTPException(403)
    if user_id==user["id"] and not data.is_active:
        raise HTTPException(400,"Kendi yönetici hesabınızı pasifleştiremezsiniz.")
    with connect() as conn:
        target=conn.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone()
        if not target:
            raise HTTPException(404,"Kullanıcı bulunamadı.")
        conn.execute("UPDATE users SET is_active=? WHERE id=?",(1 if data.is_active else 0,user_id))
        if not data.is_active:
            conn.execute("UPDATE tokens SET revoked_at=CURRENT_TIMESTAMP WHERE user_id=? AND revoked_at IS NULL",(user_id,))
    return {"ok":True}

@app.post("/api/admin/users/{user_id}/reset-link")
def issue_reset_link(user_id:int, user=Depends(auth_user)):
    if user["role"]!="admin":
        raise HTTPException(403)
    raw = new_token()
    expires = iso(utcnow()+timedelta(minutes=RESET_TOKEN_MINUTES))
    with connect() as conn:
        target=conn.execute("SELECT id,email FROM users WHERE id=?",(user_id,)).fetchone()
        if not target:
            raise HTTPException(404,"Kullanıcı bulunamadı.")
        conn.execute(
            "UPDATE password_reset_tokens SET used_at=CURRENT_TIMESTAMP WHERE user_id=? AND used_at IS NULL",
            (user_id,)
        )
        conn.execute("""
            INSERT INTO password_reset_tokens(token_hash,user_id,expires_at,created_by)
            VALUES(?,?,?,?)
        """,(token_hash(raw),user_id,expires,user["id"]))
    return {"token":raw,"expires_at":expires,"email":target["email"]}

@app.post("/api/admin/customers")
def create_customer(data:CustomerIn,user=Depends(auth_user)):
    if user["role"]!="admin":
        raise HTTPException(403)
    code=data.code.strip().upper()
    if not code or not data.name.strip():
        raise HTTPException(400,"Firma adı ve kod gerekli.")
    with connect() as conn:
        try:
            cur=conn.execute("INSERT INTO customers(name,code) VALUES(?,?)",(data.name.strip(),code))
        except Exception:
            raise HTTPException(400,"Firma kodu zaten kullanılıyor olabilir.")
    return {"id":cur.lastrowid}

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
