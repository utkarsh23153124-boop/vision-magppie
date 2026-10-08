'use strict';
const $=id=>document.getElementById(id);
let csrf=null, refreshing=false;
const notify=text=>{$('notice').textContent=text;};
function textCell(row,text){const cell=document.createElement('td');cell.textContent=text;row.append(cell);return cell;}
function button(parent,label,action){const b=document.createElement('button');b.textContent=label;b.onclick=async()=>{b.disabled=true;try{await action();await refresh();}catch(e){notify(e.message);}finally{b.disabled=false;}};parent.append(b);}
async function api(path,data){const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf||''},body:JSON.stringify(data)});const result=await response.json();if(response.status===401){showLogin();throw Error('Please sign in.');}if(!response.ok)throw Error(result.error||'Request failed.');return result;}
function showLogin(){csrf=null;$('dashboard').hidden=true;$('login').hidden=false;$('logout').hidden=true;}
async function session(){const result=await api('/api/session');csrf=result.csrf;$('dashboard').hidden=false;$('login').hidden=true;$('logout').hidden=false;await refresh();}
$('date').value=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
$('date').onchange=()=>refresh();
$('loginForm').onsubmit=async event=>{event.preventDefault();try{await api('/api/login',{password:$('password').value});$('password').value='';notify('');await session();}catch(e){notify(e.message);}};
$('logout').onclick=async()=>{try{await api('/api/logout',{});showLogin();}catch(e){notify(e.message);}};
$('cameraForm').onsubmit=async event=>{event.preventDefault();try{await api('/api/cameras',{showroom:$('showroom').value,name:$('cameraName').value,source_ref:$('sourceRef').value,axis:$('axis').value,position:Number($('position').value)/100,in_positive:$('direction').value==='positive'});notify('Camera added. Configure its stream secret on the server, then press Start.');await refresh();}catch(e){notify(e.message);}};
function readPhoto(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Could not read portrait.'));reader.readAsDataURL(file);});}
$('staffForm').onsubmit=async event=>{event.preventDefault();const submit=event.submitter;submit.disabled=true;try{const files=[...$('photos').files];if(!files.length||files.length>5||files.reduce((n,f)=>n+f.size,0)>5_000_000)throw Error('Choose 1–5 portraits, under 5 MB total.');notify('Processing staff portraits…');await api('/api/staff',{showroom:$('staffShowroom').value,name:$('staffName').value,consent:$('consent').checked,photos:await Promise.all(files.map(readPhoto))});$('staffForm').reset();notify('Staff enrolled. Verify exclusion on a real entrance walkthrough.');await refresh();}catch(e){notify(e.message);}finally{submit.disabled=false;}};
async function refresh(){if(!csrf||refreshing)return;refreshing=true;try{
 const data=await api('/api/dashboard?date='+encodeURIComponent($('date').value));
 $('export').href='/api/report.csv?date='+encodeURIComponent($('date').value);
 const totals=data.report.cameras.reduce((a,r)=>({entries:a.entries+r.entries,exits:a.exits+r.exits,excluded:a.excluded+r.staff_excluded}),{entries:0,exits:0,excluded:0});
 for(const key of ['entries','exits','excluded'])$(key).textContent=totals[key];
 $('connected').textContent=Object.values(data.workers).filter(w=>w.state==='connected'&&w.worker_alive&&w.result_age_seconds!==null&&w.result_age_seconds<5).length;
 $('cameras').replaceChildren();$('empty').hidden=data.cameras.length>0;
 for(const camera of data.cameras){const w=data.workers[camera.id]||{},r=data.report.cameras.find(r=>r.camera_id===camera.id)||{};const row=document.createElement('tr');textCell(row,camera.showroom+' / '+camera.name);textCell(row,w.state||(camera.enabled?'Restart pending':'Stopped'));textCell(row,`${r.entries||0} / ${r.exits||0}`);textCell(row,r.staff_excluded||0);textCell(row,`${w.ai_fps||0} FPS · ${w.result_age_seconds==null?'no result':w.result_age_seconds+'s ago'}`);const actions=textCell(row,'');button(actions,'Start',()=>api('/api/cameras/start',{id:camera.id}));button(actions,'Stop',()=>api('/api/cameras/stop',{id:camera.id}));button(actions,'Set line',async()=>{editingCamera=camera.id;$('linePanel').hidden=false;$('lineCamera').textContent=camera.showroom+' / '+camera.name;$('lineAxis').value=camera.axis;$('linePosition').value=camera.position*100;$('lineDirection').value=camera.in_positive?'positive':'negative';});button(actions,'Preview',async()=>{selectedCamera=camera.id;$('previewPanel').hidden=false;});$('cameras').append(row);}
 $('staff').replaceChildren();for(const staff of data.staff){const row=document.createElement('div');row.className='staff-item';const label=document.createElement('span');label.textContent=staff.name+' · '+staff.showroom;row.append(label);button(row,'Remove',async()=>{if(confirm('Delete face templates for '+staff.name+'?'))await api('/api/staff/delete',{id:staff.id});});$('staff').append(row);}
 $('hours').replaceChildren();for(const hour of data.report.hours){const row=document.createElement('tr');textCell(row,String(hour.hour).padStart(2,'0')+':00');textCell(row,hour.entries);textCell(row,hour.exits);$('hours').append(row);}
 $('history').replaceChildren();for(const log of data.report.connection_log){const p=document.createElement('p');p.textContent=new Date(log.at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' · '+(data.cameras.find(c=>c.id===log.camera_id)?.name||log.camera_id)+' · '+log.state;$('history').append(p);}
 }catch(e){notify(e.message);}finally{refreshing=false;}}
session().catch(()=>{});setInterval(refresh,3000);

let selectedCamera=null, previewUrl=null, previewBusy=false;
$('closePreview').onclick=()=>{selectedCamera=null;$('previewPanel').hidden=true;};
setInterval(async()=>{if(!csrf||!selectedCamera||previewBusy)return;previewBusy=true;const id=selectedCamera;try{const response=await fetch('/api/preview?id='+encodeURIComponent(id));if(id!==selectedCamera)return;if(response.status===200){const url=URL.createObjectURL(await response.blob());$('preview').src=url;$('preview').hidden=false;if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=url;$('previewStatus').textContent='Recent annotated frame';}else{$('preview').hidden=true;$('previewStatus').textContent='No recent frame. Check camera connection.';}}catch{$('previewStatus').textContent='Preview unavailable.';}finally{previewBusy=false;}},1000);

let editingCamera=null;
$('lineForm').onsubmit=async event=>{event.preventDefault();try{await api('/api/cameras/configure',{id:editingCamera,axis:$('lineAxis').value,position:Number($('linePosition').value)/100,in_positive:$('lineDirection').value==='positive'});$('linePanel').hidden=true;notify('Line saved. Start the camera and check its preview.');await refresh();}catch(e){notify(e.message);}};
