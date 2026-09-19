let token=localStorage.getItem("foton_token")||"";
let user=null,projects=[],activeProject=null,activeLines=[],customersCache=[],adminUsersCache=[];
let credentialValue="";
const $=id=>document.getElementById(id);
const authHeaders=(extra={})=>({"Authorization":`Bearer ${token}`,...extra});

function setMsg(id,text,type=""){const el=$(id);if(!el)return;el.textContent=text||"";el.className=`form-msg ${type}`.trim()}
function toast(text){const el=$("toast");el.textContent=text;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),3500)}
function roleName(role){return ({admin:"Yönetici",field:"Saha",customer:"Müşteri"})[role]||role}
function initial(name){return (name||"F").trim().charAt(0).toUpperCase()}
function formatDate(x){if(!x)return "-";try{return new Date(x).toLocaleString("tr-TR")}catch{return x}}
function setActiveNav(view){document.querySelectorAll(".nav-btn").forEach(b=>b.classList.toggle("active",b.dataset.view===view))}

async function api(url,opts={}){
  opts.headers={...(opts.headers||{}),...authHeaders()};
  const r=await fetch(url,opts);
  let data=null;const ct=r.headers.get("content-type")||"";
  if(ct.includes("application/json"))data=await r.json();
  if(r.status===401){localStorage.removeItem("foton_token");token="";showLogin();throw new Error(data?.detail||"Oturum süresi doldu")}
  if(!r.ok)throw new Error(data?.detail||"İşlem başarısız");
  return data??r;
}

function checkResetMode(){
  const params=new URLSearchParams(location.search);
  const resetToken=params.get("reset");
  if(resetToken){$("normalLogin").classList.add("hidden");$("resetLogin").classList.remove("hidden");window.__resetToken=resetToken}
}
function showLogin(){$("appView").classList.add("hidden");$("loginView").classList.remove("hidden");checkResetMode()}
async function login(){
  setMsg("loginMsg","");
  const email=$("email").value.trim(),password=$("password").value;
  if(!email||!password){setMsg("loginMsg","E-posta ve şifre gerekli.","error");return}
  try{
    const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email,password})});
    const j=await r.json();
    if(!r.ok)throw new Error(j.detail||"Giriş başarısız");
    token=j.token;localStorage.setItem("foton_token",token);await start();
  }catch(e){setMsg("loginMsg",e.message,"error")}
}
async function logout(){
  try{if(token)await api("/api/logout",{method:"POST"})}catch{}
  localStorage.removeItem("foton_token");token="";user=null;projects=[];showLogin()
}
function forgotInfo(){setMsg("loginMsg","Şifre sıfırlama bağlantısını FOTON yöneticiniz oluşturabilir. E-posta gönderimi sunucuya SMTP bağlandığında otomatikleşecek.","ok")}
function togglePassword(id,btn){const el=$(id);el.type=el.type==="password"?"text":"password";btn.textContent=el.type==="password"?"Göster":"Gizle"}
async function completeReset(){
  const p1=$("resetPassword").value,p2=$("resetPassword2").value;
  if(p1!==p2){setMsg("resetMsg","Şifreler eşleşmiyor.","error");return}
  try{
    const r=await fetch("/api/password-reset/complete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token:window.__resetToken,new_password:p1})});
    const j=await r.json();
    if(!r.ok)throw new Error(j.detail||"İşlem başarısız");
    history.replaceState({},document.title,location.pathname);
    $("resetLogin").classList.add("hidden");$("normalLogin").classList.remove("hidden");
    setMsg("loginMsg","Şifreniz güncellendi. Yeni şifrenizle giriş yapabilirsiniz.","ok")
  }catch(e){setMsg("resetMsg",e.message,"error")}
}

async function start(){
  try{
    user=await api("/api/me");
    $("loginView").classList.add("hidden");$("appView").classList.remove("hidden");
    applyUserUi();
    await loadProjects();showDashboard();
    if(user.must_change_password)openForcePassword();
  }catch(e){showLogin()}
}
function applyUserUi(){
  $("userBadge")?.remove?.();
  $("adminBtn").classList.toggle("hidden",user.role!=="admin");
  $("fieldBtn").classList.toggle("hidden",!["admin","field"].includes(user.role));
  $("manualGenerate").classList.toggle("hidden",!["admin","field"].includes(user.role));
  $("sideName").textContent=user.display_name;$("sideRole").textContent=roleName(user.role);$("sideAvatar").textContent=initial(user.display_name);
  $("topName").textContent=user.display_name;$("topInitial").textContent=initial(user.display_name);
  $("welcomeName").textContent=`${user.display_name}, proje durumunuz güncel.`;
  $("welcomeText").textContent=user.role==="customer"?"Yetkili olduğunuz projelerin görüntüleme ve rapor durumunu takip edebilirsiniz.":"Operasyon ve proje durumunu tek ekrandan yönetebilirsiniz.";
}
function hideAll(){["dashboardView","projectView","adminView","fieldView"].forEach(x=>$(x).classList.add("hidden"))}
function showDashboard(btn){hideAll();$("dashboardView").classList.remove("hidden");$("pageTitle").textContent="Genel Bakış";$("pageEyebrow").textContent=user?.role==="customer"?"MÜŞTERİ PORTALI":"FOTON PORTAL";setActiveNav("dashboard")}
function showProjectList(btn){showDashboard(btn)}
async function showAdmin(btn){hideAll();$("adminView").classList.remove("hidden");$("pageTitle").textContent="Yönetim";setActiveNav("admin");await loadCustomers();await loadAdminUsers()}
async function showField(btn){hideAll();$("fieldView").classList.remove("hidden");$("pageTitle").textContent="Saha";setActiveNav("field");fillFieldProjects();await loadFieldLines()}
function adminTab(name,btn){
  ["adminUsersTab","adminProjectsTab","adminCustomersTab"].forEach(id=>$(id).classList.add("hidden"));
  $({users:"adminUsersTab",projects:"adminProjectsTab",customers:"adminCustomersTab"}[name]).classList.remove("hidden");
  document.querySelectorAll(".admin-tabs button").forEach(b=>b.classList.remove("active"));btn.classList.add("active")
}
async function loadProjects(){
  projects=await api("/api/projects");$("projectCards").innerHTML="";$("importProject").innerHTML=projects.map(p=>`<option value="${p.id}">${p.name}</option>`).join("");
  let totals={projects:projects.length,lines:0,total:0,inspected:0,defects:0};
  for(const p of projects){
    const s=await api(`/api/projects/${p.id}/stats`);
    totals.lines+=s.line_count;totals.total+=s.total_length_m;totals.inspected+=s.inspected_length_m;totals.defects+=s.open_defects;
    const el=document.createElement("div");el.className="project-card";el.onclick=()=>openProject(p.id);
    el.innerHTML=`<div class="eyebrow">${p.customer_name||""}</div><h3>${p.name}</h3><div class="muted">${p.site_name||""}${p.parcel?` • ${p.parcel}`:""}</div><div class="progress"><i style="width:${s.progress_pct}%"></i></div><div style="margin-top:8px;display:flex;justify-content:space-between"><span class="muted">${s.line_count} hat • ${Math.round(s.total_length_m)} m</span><b style="color:#38e8ff">%${s.progress_pct}</b></div>`;
    $("projectCards").appendChild(el);
  }
  $("projectCountBadge").textContent=`${projects.length} proje`;
  $("globalStats").innerHTML=`<div class="stat"><b>${totals.projects}</b><span>Aktif proje</span></div><div class="stat"><b>${totals.lines}</b><span>Toplam hat</span></div><div class="stat"><b>${Math.round(totals.total)} m</b><span>Toplam uzunluk</span></div><div class="stat"><b>${Math.round(totals.inspected)} m</b><span>Görüntülendi</span></div><div class="stat"><b>${totals.defects}</b><span>Açık kusur</span></div>`;
}
async function openProject(id){
  activeProject=projects.find(p=>p.id===id);activeLines=await api(`/api/projects/${id}/lines`);const s=await api(`/api/projects/${id}/stats`);
  hideAll();$("projectView").classList.remove("hidden");$("pageTitle").textContent="Proje";$("projectTitle").textContent=activeProject.name;$("projectMeta").textContent=[activeProject.customer_name,activeProject.site_name,activeProject.parcel,activeProject.coordinate_system].filter(Boolean).join(" • ");
  $("projectStats").innerHTML=`<div class="stat"><b>${s.line_count}</b><span>Hat</span></div><div class="stat"><b>${s.total_length_m} m</b><span>Toplam</span></div><div class="stat"><b>${s.inspected_length_m} m</b><span>Görüntülendi</span></div><div class="stat"><b>${s.remaining_length_m} m</b><span>Kalan</span></div><div class="stat"><b>${s.open_defects}</b><span>Açık kusur</span></div>`;renderMap();renderTable()
}
function state(l){return l.latest_inspection?l.latest_inspection.result:"NOT_INSPECTED"}
function stateText(s){return ({OK:"Uygun",DEFECT:"Kusurlu",RECHECK:"Tekrar kontrol",NO_IMAGE:"Görüntü alınamadı",NOT_INSPECTED:"Görüntülenmedi"})[s]||s}
function color(s){return ({OK:"#7cff9b",DEFECT:"#ff6e7a",RECHECK:"#ffd36e",NO_IMAGE:"#6ce5ff",NOT_INSPECTED:"#70808a"})[s]||"#70808a"}
function renderMap(){const svg=$("mapSvg");svg.innerHTML="";if(!activeLines.length)return;const xs=activeLines.flatMap(l=>[l.x1,l.x2]),ys=activeLines.flatMap(l=>[l.y1,l.y2]);let minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);if(maxX===minX)maxX++;if(maxY===minY)maxY++;const pad=70,W=1200,H=680,sx=x=>pad+(x-minX)/(maxX-minX)*(W-2*pad),sy=y=>H-pad-(y-minY)/(maxY-minY)*(H-2*pad);for(const l of activeLines){const s=state(l),mx=(sx(l.x1)+sx(l.x2))/2,my=(sy(l.y1)+sy(l.y2))/2;svg.insertAdjacentHTML("beforeend",`<line x1="${sx(l.x1)}" y1="${sy(l.y1)}" x2="${sx(l.x2)}" y2="${sy(l.y2)}" stroke="${color(s)}" stroke-width="10" stroke-linecap="round" style="cursor:pointer" onclick="openLine(${l.id})"/><circle cx="${sx(l.x1)}" cy="${sy(l.y1)}" r="8" fill="#effcff"/><circle cx="${sx(l.x2)}" cy="${sy(l.y2)}" r="8" fill="#effcff"/><text x="${mx}" y="${my-12}" fill="#afc2cc" font-size="14" text-anchor="middle">${l.line_code}</text>`)}}
function renderTable(){$("lineTable").innerHTML="";for(const l of activeLines){const s=state(l),d=l.latest_inspection?.inspected_at||"-";const tr=document.createElement("tr");tr.innerHTML=`<td><b>${l.line_code}</b></td><td>${l.line_type}</td><td>Ø${l.diameter_mm||"-"}</td><td>${l.length_m.toFixed(2)} m</td><td>${stateText(s)}</td><td>${formatDate(d)}</td><td><button class="mini" onclick="openLine(${l.id})">Geçmiş</button></td>`;$("lineTable").appendChild(tr)}}
async function openLine(id){const l=activeLines.find(x=>x.id===id);$("modalLineTitle").textContent=l.line_code;const hist=await api(`/api/lines/${id}/history`);if(!hist.length){$("lineHistory").innerHTML='<div class="muted">Henüz görüntüleme kaydı yok.</div>'}else $("lineHistory").innerHTML=hist.map(h=>`<div class="history-item"><h4>${stateText(h.result)} • ${formatDate(h.inspected_at)}</h4><div class="muted">${h.operator_name}</div><p>${h.notes||""}</p>${h.defects.map(d=>`<span class="tag">${d.defect_type}${d.meter!=null?` @ ${d.meter}m`:""} • ${d.severity}</span>`).join("")}<div style="margin-top:9px">${h.videos.map(v=>`<button class="tag" onclick="downloadAuth('${v.url}','${v.original_name.replace(/'/g,"_")}')">▶ ${v.original_name}</button>`).join("")}</div>${["admin","field"].includes(user.role)?`<button class="mini" style="margin-top:8px" onclick="openVideoModal(${h.id})">Video yükle</button>`:""}</div>`).join("");$("lineModal").classList.remove("hidden")}
function closeLineModal(){$("lineModal").classList.add("hidden")}function openVideoModal(id){$("videoInspectionId").value=id;$("videoModal").classList.remove("hidden")}function closeVideoModal(){$("videoModal").classList.add("hidden")}
async function uploadVideo(){const f=$("videoFile").files[0];if(!f){setMsg("videoMsg","Video seçin.","error");return}const form=new FormData();form.append("file",f);try{await api(`/api/inspections/${$("videoInspectionId").value}/videos`,{method:"POST",body:form});setMsg("videoMsg","Video yüklendi.","ok");toast("Video görüntüleme kaydına bağlandı.")}catch(e){setMsg("videoMsg",e.message,"error")}}
async function loadCustomers(){customersCache=await api("/api/customers");const opts=customersCache.map(c=>`<option value="${c.id}">${c.name}</option>`).join("");$("customerSelect").innerHTML=opts;$("newUserCustomer").innerHTML=opts}
async function createProject(){const body={customer_id:Number($("customerSelect").value),name:$("newProjectName").value,code:$("newProjectCode").value,site_name:$("newProjectSite").value,parcel:$("newProjectParcel").value,coordinate_system:$("newProjectCrs").value||"LOCAL"};try{await api("/api/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});setMsg("createMsg","Proje oluşturuldu.","ok");await loadProjects()}catch(e){setMsg("createMsg",e.message,"error")}}
async function uploadCsv(){const f=$("csvFile").files[0];if(!f){$("uploadMsg").textContent="CSV seçin.";return}const form=new FormData();form.append("file",f);form.append("replace",$("replaceRows").checked?"true":"false");try{const j=await api(`/api/projects/${$("importProject").value}/import-csv`,{method:"POST",body:form});$("uploadMsg").textContent=j.ok?`${j.imported} hat yüklendi. Revizyon R${String(j.revision).padStart(2,"0")}`:j.errors.join("\n");await loadProjects()}catch(e){$("uploadMsg").textContent=e.message}}
function fillFieldProjects(){$("fieldProject").innerHTML=projects.map(p=>`<option value="${p.id}">${p.name}</option>`).join("")}
async function loadFieldLines(){const pid=$("fieldProject").value;if(!pid)return;const lines=await api(`/api/projects/${pid}/lines`);$("fieldLine").innerHTML=lines.map(l=>`<option value="${l.id}">${l.line_code} • ${l.line_type}</option>`).join("")}
function toggleDefectFields(){$("defectFields").classList.toggle("hidden",$("fieldResult").value!=="DEFECT")}
async function saveInspection(){const body={result:$("fieldResult").value,notes:$("fieldNotes").value||null};if(body.result==="DEFECT"){body.defect_type=$("defectType").value||"DIGER";body.defect_meter=$("defectMeter").value?Number($("defectMeter").value):null;body.defect_severity=$("defectSeverity").value;body.defect_description=$("defectDesc").value||null}try{const j=await api(`/api/lines/${$("fieldLine").value}/inspections`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});setMsg("inspectionMsg",`Kaydedildi. Rapor ve CAD R${String(j.revision).padStart(2,"0")} oluşturuldu.`,"ok");await loadProjects();await loadFieldLines()}catch(e){setMsg("inspectionMsg",e.message,"error")}}
async function generateRevision(){const j=await api(`/api/projects/${activeProject.id}/generate`,{method:"POST"});toast(`R${String(j.revision).padStart(2,"0")} üretildi`)}
async function loadRevisions(){const j=await api(`/api/projects/${activeProject.id}/revisions`);const map={};for(const r of j.reports)map[r.revision_no]={report:r};for(const c of j.cad){map[c.revision_no]=map[c.revision_no]||{};map[c.revision_no].cad=c}$("revisionList").innerHTML=Object.keys(map).sort((a,b)=>b-a).map(n=>{const x=map[n];return `<div class="revision-row"><b>R${String(n).padStart(2,"0")}</b><div>${x.report?formatDate(x.report.generated_at):"-"}</div><div>${x.cad?formatDate(x.cad.generated_at):"-"}</div><div>${x.report?`<button onclick="downloadAuth('/api/reports/${x.report.id}/download','report_R${n}.pdf')">PDF</button>`:""} ${x.cad?`<button onclick="downloadAuth('/api/cad/${x.cad.id}/download','cad_R${n}.dxf')">DXF</button>`:""}</div></div>`}).join("")||'<div class="muted">Henüz revizyon yok.</div>';$("revisionModal").classList.remove("hidden")}
function closeRevisionModal(){$("revisionModal").classList.add("hidden")}
async function downloadAuth(url,name){const r=await fetch(url,{headers:authHeaders()});if(!r.ok){toast("Dosya alınamadı.");return}const b=await r.blob(),u=URL.createObjectURL(b),a=document.createElement("a");a.href=u;a.download=name;a.click();URL.revokeObjectURL(u)}

function openProfile(){$("profileName").textContent=user.display_name;$("profileEmail").textContent=user.email;$("profileRole").textContent=roleName(user.role);$("profileAvatar").textContent=initial(user.display_name);$("profileModal").classList.remove("hidden")}
function closeProfile(){$("profileModal").classList.add("hidden");setMsg("profileMsg","")}
async function changePassword(){const cur=$("currentPassword").value,p1=$("newPassword").value,p2=$("newPassword2").value;if(p1!==p2){setMsg("profileMsg","Yeni şifreler eşleşmiyor.","error");return}try{await api("/api/change-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({current_password:cur,new_password:p1})});setMsg("profileMsg","Şifreniz değiştirildi. Diğer açık oturumlar kapatıldı.","ok");$("currentPassword").value=$("newPassword").value=$("newPassword2").value=""}catch(e){setMsg("profileMsg",e.message,"error")}}
function openForcePassword(){$("forcePasswordModal").classList.remove("hidden")}
async function forceChangePassword(){const cur=$("forceCurrentPassword").value,p1=$("forceNewPassword").value,p2=$("forceNewPassword2").value;if(p1!==p2){setMsg("forcePasswordMsg","Yeni şifreler eşleşmiyor.","error");return}try{await api("/api/change-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({current_password:cur,new_password:p1})});user.must_change_password=0;$("forcePasswordModal").classList.add("hidden");toast("Yeni şifreniz kaydedildi.")}catch(e){setMsg("forcePasswordMsg",e.message,"error")}}

function toggleCustomerUserFields(){$("newUserCustomerWrap").classList.toggle("hidden",$("newUserRole").value!=="customer")}
async function loadAdminUsers(){adminUsersCache=await api("/api/admin/users");$("usersTable").innerHTML=adminUsersCache.map(u=>`<tr><td><b>${u.display_name}</b><div class="muted">${u.email}</div></td><td>${roleName(u.role)}</td><td>${u.customer_name||"-"}</td><td>${u.project_count}</td><td>${formatDate(u.last_login_at)}</td><td><span class="status-pill ${u.is_active?"status-on":"status-off"}">${u.is_active?"Aktif":"Pasif"}</span>${u.must_change_password?` <span class="status-pill must-change">Şifre bekliyor</span>`:""}</td><td><button class="mini" onclick="issueReset(${u.id},'${u.email.replace(/'/g,"_")}')">Şifre Linki</button> <button class="mini" onclick="setUserStatus(${u.id},${u.is_active?0:1})">${u.is_active?"Pasifleştir":"Aktifleştir"}</button></td></tr>`).join("")}
async function createPortalUser(){const body={email:$("newUserEmail").value.trim(),display_name:$("newUserName").value.trim(),role:$("newUserRole").value,customer_id:$("newUserRole").value==="customer"?Number($("newUserCustomer").value):null};try{const j=await api("/api/admin/users",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});setMsg("newUserMsg","Kullanıcı oluşturuldu.","ok");showCredential("Kullanıcı oluşturuldu",body.email,j.temporary_password);$("newUserEmail").value=$("newUserName").value="";await loadAdminUsers()}catch(e){setMsg("newUserMsg",e.message,"error")}}
async function issueReset(id,email){try{const j=await api(`/api/admin/users/${id}/reset-link`,{method:"POST"});const link=`${location.origin}/?reset=${encodeURIComponent(j.token)}`;showCredential("Şifre sıfırlama bağlantısı",email,link)}catch(e){toast(e.message)}}
async function setUserStatus(id,isActive){try{await api(`/api/admin/users/${id}/status`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({is_active:!!isActive})});await loadAdminUsers();toast(isActive?"Kullanıcı aktifleştirildi.":"Kullanıcı pasifleştirildi.")}catch(e){toast(e.message)}}
function showCredential(title,email,secret){$("credentialTitle").textContent=title;$("credentialEmail").textContent=email;$("credentialSecret").textContent=secret;credentialValue=`${email}\n${secret}`;$("credentialModal").classList.remove("hidden")}
function closeCredentialModal(){$("credentialModal").classList.add("hidden")}
async function copyCredential(){try{await navigator.clipboard.writeText(credentialValue);toast("Panoya kopyalandı.")}catch{toast("Kopyalama başarısız.")}}
async function createCustomer(){try{const j=await api("/api/admin/customers",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:$("newCustomerName").value.trim(),code:$("newCustomerCode").value.trim()})});setMsg("customerMsg","Firma oluşturuldu.","ok");$("newCustomerName").value=$("newCustomerCode").value="";await loadCustomers()}catch(e){setMsg("customerMsg",e.message,"error")}}

checkResetMode();
if(token)start();else showLogin();
