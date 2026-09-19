let token=localStorage.getItem("foton_token")||"";
let user=null,projects=[],activeProject=null,activeLines=[];

const $=id=>document.getElementById(id);
const authHeaders=(extra={})=>({"Authorization":`Bearer ${token}`,...extra});

async function api(url,opts={}){
  opts.headers={...(opts.headers||{}),...authHeaders()};
  const r=await fetch(url,opts);
  if(r.status===401){logout();throw new Error("Oturum gerekli")}
  let data=null;
  const ct=r.headers.get("content-type")||"";
  if(ct.includes("application/json")) data=await r.json();
  if(!r.ok) throw new Error(data?.detail||"İşlem başarısız");
  return data??r;
}

async function login(){
  const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("email").value,password:$("password").value})});
  const j=await r.json();
  if(!r.ok){alert(j.detail||"Giriş başarısız");return}
  token=j.token;localStorage.setItem("foton_token",token);await start();
}
function logout(){localStorage.removeItem("foton_token");token="";user=null;$("appView").classList.add("hidden");$("loginView").classList.remove("hidden")}
async function start(){
  try{
    user=await api("/api/me");
    $("loginView").classList.add("hidden");$("appView").classList.remove("hidden");
    $("userBadge").textContent=`${user.display_name} • ${user.role}`;
    $("adminBtn").classList.toggle("hidden",user.role!=="admin");
    $("fieldBtn").classList.toggle("hidden",!["admin","field"].includes(user.role));
    $("manualGenerate").classList.toggle("hidden",!["admin","field"].includes(user.role));
    await loadProjects();showDashboard();
  }catch(e){logout()}
}
function hideAll(){["dashboardView","projectView","adminView","fieldView"].forEach(x=>$(x).classList.add("hidden"))}
function showDashboard(){hideAll();$("dashboardView").classList.remove("hidden");$("pageTitle").textContent="Genel Bakış"}
function showProjectList(){showDashboard()}
async function showAdmin(){hideAll();$("adminView").classList.remove("hidden");$("pageTitle").textContent="Yönetici";await loadCustomers()}
async function showField(){hideAll();$("fieldView").classList.remove("hidden");$("pageTitle").textContent="Saha";fillFieldProjects();await loadFieldLines()}
async function loadProjects(){
  projects=await api("/api/projects");
  $("projectCards").innerHTML="";
  $("importProject").innerHTML=projects.map(p=>`<option value="${p.id}">${p.name}</option>`).join("");
  let totals={projects:projects.length,lines:0,total:0,inspected:0,defects:0};
  for(const p of projects){
    const s=await api(`/api/projects/${p.id}/stats`);
    totals.lines+=s.line_count;totals.total+=s.total_length_m;totals.inspected+=s.inspected_length_m;totals.defects+=s.open_defects;
    const el=document.createElement("div");el.className="project-card";el.onclick=()=>openProject(p.id);
    el.innerHTML=`<div class="eyebrow">${p.customer_name||""}</div><h3>${p.name}</h3><div class="muted">${s.line_count} hat • ${s.total_length_m} m</div><div style="margin-top:10px;color:#38e8ff">%${s.progress_pct} tamamlandı</div>`;
    $("projectCards").appendChild(el);
  }
  $("globalStats").innerHTML=`
    <div class="stat"><b>${totals.projects}</b><span>Proje</span></div>
    <div class="stat"><b>${totals.lines}</b><span>Hat</span></div>
    <div class="stat"><b>${Math.round(totals.total)} m</b><span>Toplam</span></div>
    <div class="stat"><b>${Math.round(totals.inspected)} m</b><span>Görüntülendi</span></div>
    <div class="stat"><b>${totals.defects}</b><span>Açık kusur</span></div>`;
}
async function openProject(id){
  activeProject=projects.find(p=>p.id===id);activeLines=await api(`/api/projects/${id}/lines`);const s=await api(`/api/projects/${id}/stats`);
  hideAll();$("projectView").classList.remove("hidden");$("pageTitle").textContent="Proje";$("projectTitle").textContent=activeProject.name;
  $("projectStats").innerHTML=`
    <div class="stat"><b>${s.line_count}</b><span>Hat</span></div>
    <div class="stat"><b>${s.total_length_m} m</b><span>Toplam</span></div>
    <div class="stat"><b>${s.inspected_length_m} m</b><span>Görüntülendi</span></div>
    <div class="stat"><b>${s.remaining_length_m} m</b><span>Kalan</span></div>
    <div class="stat"><b>${s.open_defects}</b><span>Açık kusur</span></div>`;
  renderMap();renderTable();
}
function state(l){return l.latest_inspection?l.latest_inspection.result:"NOT_INSPECTED"}
function stateText(s){return ({OK:"Uygun",DEFECT:"Kusurlu",RECHECK:"Tekrar kontrol",NO_IMAGE:"Görüntü alınamadı",NOT_INSPECTED:"Görüntülenmedi"})[s]||s}
function color(s){return ({OK:"#7cff9b",DEFECT:"#ff6e7a",RECHECK:"#ffd36e",NO_IMAGE:"#6ce5ff",NOT_INSPECTED:"#70808a"})[s]||"#70808a"}
function renderMap(){
  const svg=$("mapSvg");svg.innerHTML="";if(!activeLines.length)return;
  const xs=activeLines.flatMap(l=>[l.x1,l.x2]),ys=activeLines.flatMap(l=>[l.y1,l.y2]);
  let minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);if(maxX===minX)maxX++;if(maxY===minY)maxY++;
  const pad=70,W=1200,H=680,sx=x=>pad+(x-minX)/(maxX-minX)*(W-2*pad),sy=y=>H-pad-(y-minY)/(maxY-minY)*(H-2*pad);
  for(const l of activeLines){
    const s=state(l),mx=(sx(l.x1)+sx(l.x2))/2,my=(sy(l.y1)+sy(l.y2))/2;
    svg.insertAdjacentHTML("beforeend",`<line x1="${sx(l.x1)}" y1="${sy(l.y1)}" x2="${sx(l.x2)}" y2="${sy(l.y2)}" stroke="${color(s)}" stroke-width="10" stroke-linecap="round" style="cursor:pointer" onclick="openLine(${l.id})"/><circle cx="${sx(l.x1)}" cy="${sy(l.y1)}" r="8" fill="#effcff"/><circle cx="${sx(l.x2)}" cy="${sy(l.y2)}" r="8" fill="#effcff"/><text x="${mx}" y="${my-12}" fill="#afc2cc" font-size="14" text-anchor="middle">${l.line_code}</text>`);
  }
}
function renderTable(){
  $("lineTable").innerHTML="";
  for(const l of activeLines){
    const s=state(l),d=l.latest_inspection?.inspected_at||"-";
    const tr=document.createElement("tr");
    tr.innerHTML=`<td>${l.line_code}</td><td>${l.line_type}</td><td>Ø${l.diameter_mm||"-"}</td><td>${l.length_m.toFixed(2)} m</td><td>${stateText(s)}</td><td>${d}</td><td><button class="mini" onclick="openLine(${l.id})">Geçmiş</button></td>`;
    $("lineTable").appendChild(tr);
  }
}
async function openLine(id){
  const l=activeLines.find(x=>x.id===id);$("modalLineTitle").textContent=l.line_code;
  const hist=await api(`/api/lines/${id}/history`);
  if(!hist.length){$("lineHistory").innerHTML='<div class="muted">Henüz görüntüleme kaydı yok.</div>'}
  else $("lineHistory").innerHTML=hist.map(h=>`<div class="history-item"><h4>${stateText(h.result)} • ${h.inspected_at}</h4><div class="muted">${h.operator_name}</div><p>${h.notes||""}</p>${h.defects.map(d=>`<span class="tag">${d.defect_type}${d.meter!=null?` @ ${d.meter}m`:""} • ${d.severity}</span>`).join("")}<div style="margin-top:9px">${h.videos.map(v=>`<button class="tag" onclick="downloadAuth('${v.url}','${v.original_name.replace(/'/g,"_")}')">▶ ${v.original_name}</button>`).join("")}</div>${["admin","field"].includes(user.role)?`<button class="mini" style="margin-top:8px" onclick="openVideoModal(${h.id})">Video yükle</button>`:""}</div>`).join("");
  $("lineModal").classList.remove("hidden");
}
function closeLineModal(){$("lineModal").classList.add("hidden")}
function openVideoModal(id){$("videoInspectionId").value=id;$("videoModal").classList.remove("hidden")}
function closeVideoModal(){$("videoModal").classList.add("hidden")}
async function uploadVideo(){
  const f=$("videoFile").files[0];if(!f){alert("Video seç");return}
  const form=new FormData();form.append("file",f);
  try{await api(`/api/inspections/${$("videoInspectionId").value}/videos`,{method:"POST",body:form});$("videoMsg").textContent="Video yüklendi.";await openLine(activeLines.find(l=>l.latest_inspection?.id==$("videoInspectionId").value)?.id||activeLines[0].id)}catch(e){$("videoMsg").textContent=e.message}
}
async function loadCustomers(){
  const cs=await api("/api/customers");$("customerSelect").innerHTML=cs.map(c=>`<option value="${c.id}">${c.name}</option>`).join("");
}
async function createProject(){
  const body={customer_id:Number($("customerSelect").value),name:$("newProjectName").value,code:$("newProjectCode").value,site_name:$("newProjectSite").value,parcel:$("newProjectParcel").value,coordinate_system:$("newProjectCrs").value||"LOCAL"};
  try{await api("/api/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});$("createMsg").textContent="Proje oluşturuldu.";await loadProjects()}catch(e){$("createMsg").textContent=e.message}
}
async function uploadCsv(){
  const f=$("csvFile").files[0];if(!f){alert("CSV seç");return}
  const form=new FormData();form.append("file",f);form.append("replace",$("replaceRows").checked?"true":"false");
  try{const j=await api(`/api/projects/${$("importProject").value}/import-csv`,{method:"POST",body:form});$("uploadMsg").textContent=j.ok?`${j.imported} hat yüklendi. Revizyon R${String(j.revision).padStart(2,"0")}`:j.errors.join("\n");await loadProjects()}catch(e){$("uploadMsg").textContent=e.message}
}
function fillFieldProjects(){$("fieldProject").innerHTML=projects.map(p=>`<option value="${p.id}">${p.name}</option>`).join("")}
async function loadFieldLines(){const pid=$("fieldProject").value;if(!pid)return;const lines=await api(`/api/projects/${pid}/lines`);$("fieldLine").innerHTML=lines.map(l=>`<option value="${l.id}">${l.line_code} • ${l.line_type}</option>`).join("")}
function toggleDefectFields(){$("defectFields").classList.toggle("hidden",$("fieldResult").value!=="DEFECT")}
async function saveInspection(){
  const body={result:$("fieldResult").value,notes:$("fieldNotes").value||null};
  if(body.result==="DEFECT"){body.defect_type=$("defectType").value||"DIGER";body.defect_meter=$("defectMeter").value?Number($("defectMeter").value):null;body.defect_severity=$("defectSeverity").value;body.defect_description=$("defectDesc").value||null}
  try{const j=await api(`/api/lines/${$("fieldLine").value}/inspections`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});$("inspectionMsg").textContent=`Kaydedildi. Rapor ve CAD otomatik R${String(j.revision).padStart(2,"0")} oluşturuldu.`;await loadProjects();await loadFieldLines()}catch(e){$("inspectionMsg").textContent=e.message}
}
async function generateRevision(){const j=await api(`/api/projects/${activeProject.id}/generate`,{method:"POST"});alert(`R${String(j.revision).padStart(2,"0")} üretildi`)}
async function loadRevisions(){
  const j=await api(`/api/projects/${activeProject.id}/revisions`);
  const map={};for(const r of j.reports)map[r.revision_no]={report:r};for(const c of j.cad){map[c.revision_no]=map[c.revision_no]||{};map[c.revision_no].cad=c}
  $("revisionList").innerHTML=Object.keys(map).sort((a,b)=>b-a).map(n=>{const x=map[n];return `<div class="revision-row"><b>R${String(n).padStart(2,"0")}</b><div>${x.report?x.report.generated_at:"-"}</div><div>${x.cad?x.cad.generated_at:"-"}</div><div>${x.report?`<button onclick="downloadAuth('/api/reports/${x.report.id}/download','report_R${n}.pdf')">PDF</button>`:""} ${x.cad?`<button onclick="downloadAuth('/api/cad/${x.cad.id}/download','cad_R${n}.dxf')">DXF</button>`:""}</div></div>`}).join("");
  $("revisionModal").classList.remove("hidden");
}
function closeRevisionModal(){$("revisionModal").classList.add("hidden")}
async function downloadAuth(url,name){const r=await fetch(url,{headers:authHeaders()});if(!r.ok){alert("Dosya alınamadı");return}const b=await r.blob(),u=URL.createObjectURL(b),a=document.createElement("a");a.href=u;a.download=name;a.click();URL.revokeObjectURL(u)}
if(token)start();
