/* VietFrame Studio — no mock data, no fake video processing. */
'use strict';
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const state = { projects: [], selected: null, capabilities: null, polling: null, view: 'projects', preview: 'source' };
const statusText = { ready: 'Sẵn sàng', queued: 'Đang xếp hàng', downloading: 'Đang tải video', transcribing: 'Nhận dạng thoại', translating: 'Đang dịch', rendering: 'Đang xuất MP4', dubbing: 'Đang lồng tiếng', generating: 'Đang tạo AI', error: 'Có lỗi' };
const ongoing = ['queued','downloading','transcribing','translating','rendering','dubbing','generating'];

function toast(message, error=false) {
  const el = $('#toast'); el.textContent = message; el.className = error ? 'visible error' : 'visible';
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.className = '', 6000);
}
async function request(url, options = {}) {
  const response = await fetch(url, options);
  const raw = await response.text();
  let body; try { body = JSON.parse(raw); } catch { body = {detail: raw.slice(0,500) || `HTTP ${response.status}`}; }
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail || `HTTP ${response.status}`));
  }
  return body;
}
async function apiPost(path, payload) {
  return request(path, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
}
function text(el, value) { el.textContent = value == null ? '' : String(value); }
function formatSeconds(n) { n = Math.max(0, Number(n) || 0); const mm = Math.floor(n/60), ss = (n % 60).toFixed(2).padStart(5,'0'); return `${String(mm).padStart(2,'0')}:${ss}`; }
function parseSeconds(value) {
  const s = String(value).trim();
  if (/^\d+(?:\.\d+)?$/.test(s)) return Number(s);
  const m = s.match(/^(\d{1,3}):(\d{1,2}(?:\.\d+)?)$/);
  if (m && Number(m[2]) < 60) return 60*Number(m[1]) + Number(m[2]);
  throw new Error(`Thời gian không hợp lệ: ${s}. Ví dụ 00:03.50`);
}
function switchView(view) {
  state.view = view;
  $$('.view').forEach(x => x.classList.add('hidden'));
  $(`#view-${view}`).classList.remove('hidden');
  $$('.nav-item').forEach(x => x.classList.toggle('active', x.dataset.view === view));
  text($('#breadcrumb-view'), ({ projects:'Tổng quan', editor:'Biên tập phụ đề', ai:'Tạo video AI', settings:'Hệ thống' })[view]);
  if (view === 'settings') loadCapabilities();
}
function showError(error) { toast(error?.message || 'Có lỗi chưa xác định.', true); }
function consent() { if (!$('#license-ok').checked) throw new Error('Bạn cần xác nhận quyền sử dụng video.'); }

async function addLink() {
  try {
    consent(); const url = $('#video-url').value.trim();
    if (!url) throw new Error('Hãy nhập link video công khai.');
    $('#add-url').disabled = true;
    const project = await apiPost('/api/projects/from-url', {url, license_confirmed:true});
    toast('Đã tạo tác vụ nhập link. Đang chờ kết quả tải thật.');
    await loadProjects(); await selectProject(project.id);
  } catch (e) { showError(e); }
  finally { $('#add-url').disabled = false; }
}
async function upload(file) {
  if (!file) return;
  try {
    consent();
    if (file.size > 350 * 1024 * 1024) throw new Error('Tệp trên 350 MB.');
    const data = new FormData(); data.append('file', file); data.append('title',file.name); data.append('license_confirmed','true');
    toast(`Đang gửi ${file.name}…`);
    const p = await request('/api/projects/upload', {method:'POST',body:data});
    toast('Tải video lên thành công.'); await loadProjects(); await selectProject(p.id);
  } catch(e) { showError(e); }
  finally { $('#video-upload').value = ''; }
}
function renderProjects() {
  const holder = $('#project-list'); holder.replaceChildren();
  if (!state.projects.length) { const el=document.createElement('div'); el.className='empty-list';el.textContent='Chưa có dự án. Hãy nhập link hoặc tải video lên ở phía trên.'; holder.append(el); return; }
  state.projects.forEach(p => {
    const btn=document.createElement('button'); btn.type='button';btn.className='project-item';
    const thumb=document.createElement('div');thumb.className='project-thumbnail';thumb.textContent='▻';
    const d=document.createElement('div');d.className='project-detail';
    const title=document.createElement('strong');text(title,p.title);
    const date=document.createElement('small');text(date,`${p.source}  ·  ${p.duration ? Math.round(p.duration)+' giây' : 'Chưa xác định'}  ·  ${new Date(p.created_at).toLocaleDateString('vi-VN')}`);
    d.append(title,date);
    const badge=document.createElement('span');badge.className='item-badge '+(p.status==='error'?'error':ongoing.includes(p.status)?'processing':'');text(badge,statusText[p.status]||p.status);
    const arrow=document.createElement('span');arrow.className='item-arrow';arrow.textContent='›';
    btn.append(thumb,d,badge,arrow);btn.addEventListener('click',()=>selectProject(p.id));holder.append(btn);
  });
  const chooser=$('#project-select'), old=state.selected?.id || chooser.value;
  chooser.replaceChildren();const first=document.createElement('option');first.value='';first.textContent='Chọn dự án…';chooser.append(first);
  state.projects.forEach(p => {const option=document.createElement('option');option.value=p.id;option.textContent=p.title+' — '+(statusText[p.status]||p.status);chooser.append(option);});
  chooser.value = state.projects.some(p=>p.id===old) ? old : '';
}
async function loadProjects() { try {state.projects=await request('/api/projects');renderProjects();}catch(e){showError(e);} }
async function selectProject(pid) {
  if (!pid) { state.selected=null;showProject(null);return; }
  try { state.preview='source';state.selected=await request('/api/projects/'+pid); showProject(state.selected);switchView('editor');managePolling(); }
  catch(e) {showError(e);}
}
function updateCaptionOverlay(){
  const overlay=$('#caption-overlay');
  const player=$('#player');
  if (!state.selected || !player.videoWidth || (state.preview==='export' && !!state.selected.export_url)) {overlay.textContent='';return;}
  let active=null;
  try { active=collectSegments().find(seg=>Number.isFinite(seg.start)&&Number.isFinite(seg.end)&&
    seg.start<=player.currentTime && seg.end>player.currentTime && seg.text); }
  catch { overlay.textContent='';return; }
  if (!active) {overlay.textContent='';return;}
  const style=currentStyle();
  const box=player.getBoundingClientRect(),screen=$('.screen').getBoundingClientRect();
  const scale=Math.min(box.width/player.videoWidth,box.height/player.videoHeight);
  const visibleHeight=player.videoHeight*scale;
  overlay.style.bottom=(Math.max(0,(screen.height-visibleHeight)/2) + Math.max(0,style.margin_v)*scale)+'px';
  overlay.style.fontSize=Math.max(10,style.font_size*scale)+'px';
  overlay.style.fontWeight=style.bold?'800':'400';
  overlay.style.fontFamily='"'+style.font.replace(/"/g,'')+'",sans-serif';
  overlay.style.color=style.color;
  overlay.style.webkitTextStroke=Math.min(7,style.outline*scale)+'px '+style.outline_color;
  overlay.style.paintOrder='stroke fill';
  overlay.textContent=active.text;
}

function showProject(p) {
  $('#project-select').value = p?.id || '';
  const playingExport = state.preview==='export' && !!p?.export_url;
  const url = playingExport ? p.export_url : p?.video_url;
  $('#player').hidden = !url;$('#screen-empty').classList.toggle('hidden',!!url);
  if (url && $('#player').getAttribute('src') !== url) { $('#player').src=url;$('#player').load(); }
  $('#show-source').disabled = !p?.video_url;
  $('#show-export').disabled = !p?.export_url;
  $('#show-source').classList.toggle('active',!playingExport);
  $('#show-export').classList.toggle('active',playingExport);
  $('#recover-current').classList.toggle('hidden',p?.status!=='error' || !p?.video_url);
  if (!p) {$('#player').removeAttribute('src');$('#player').load();}
  text($('#project-status'),p ? (statusText[p.status]||p.status):'Chưa chọn');
  text($('#project-message'),p ? `${p.message || 'Video đã được nạp.'}  ${ongoing.includes(p.status) ? `(${p.progress}%)` : ''}` : 'Chọn một dự án để thao tác.');
  $('#progress-bar').style.width = `${p?.progress||0}%`;
  $('#download-export').classList.toggle('hidden', !p?.export_url);
  $('#download-srt').classList.toggle('hidden', !p?.segments?.length);
  $('#dub-preview').classList.toggle('hidden', !p?.dub_url);
  if (p?.dub_url) $('#dub-preview').src=p.dub_url;
  if (p?.export_url) $('#download-export').href=p.export_url;
  if (p?.id) $('#download-srt').href=`/api/projects/${p.id}/subtitles.srt`;
  const editable=p?.status==='ready';
  ['render-button','save-segments','transcribe','translate','add-segment'].forEach(id => $(`#${id}`).disabled = !editable);
  $('#dub-button').disabled=!editable||!state.capabilities?.tts_kokoro_local;
  renderSegments(p?.segments||[]);
  updateCaptionOverlay();
}
function makeInput(type,value,cls){const input=document.createElement(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.className=cls;input.value=value;return input;}
function addSegment(seg = {start:0,end:2.5,text:''}) {
  const holder=$('#segments');holder.querySelector('.tip')?.remove();
  const item=document.createElement('div');item.className='segment-card';
  const top=document.createElement('div');top.className='segment-top';const label=document.createElement('span');label.textContent='ĐOẠN '+(holder.querySelectorAll('.segment-card').length+1);
  const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.title='Xóa câu';remove.addEventListener('click',()=>{item.remove();renumberSegments();});top.append(label,remove);
  const times=document.createElement('div');times.className='segment-time';
  const startLabel=document.createElement('label');startLabel.textContent='Bắt đầu';startLabel.append(makeInput('text',formatSeconds(seg.start),'seg-start'));
  const endLabel=document.createElement('label');endLabel.textContent='Kết thúc';endLabel.append(makeInput('text',formatSeconds(seg.end),'seg-end'));
  times.append(startLabel,endLabel);
  const content=makeInput('textarea',seg.text,'segment-text');content.placeholder='Nhập lời thoại tiếng Việt…';content.rows=2;
  item.append(top,times,content);holder.append(item);
}
function renumberSegments(){ $$('#segments .segment-card').forEach((el,i)=>text(el.querySelector('.segment-top span'),'ĐOẠN '+(i+1))); }
function renderSegments(items) { const container=$('#segments');container.replaceChildren();if(!items.length){const tip=document.createElement('div');tip.className='tip';tip.textContent='Nhập hoặc nhận dạng lời thoại để bắt đầu.';container.append(tip);return;}items.forEach(addSegment); }
function collectSegments() {
  return $$('#segments .segment-card').map((el) => ({start:parseSeconds(el.querySelector('.seg-start').value),end:parseSeconds(el.querySelector('.seg-end').value),text:el.querySelector('.segment-text').value.trim()}));
}
async function saveSegments(showToast=true){
  if(!state.selected) throw new Error('Chưa chọn dự án.');
  const segments=collectSegments();
  if (segments.some(s=>!s.text || s.end<=s.start)) throw new Error('Nội dung hoặc thời gian phụ đề chưa hợp lệ.');
  const saved=await request('/api/projects/'+state.selected.id+'/segments',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({segments})});
  state.selected=saved;
  if(showToast)toast('Đã lưu nội dung phụ đề thật.');return saved;
}
function currentStyle(){return {font:$('#style-font').value,font_size:Number($('#style-size').value),color:$('#style-color').value,outline_color:$('#style-outline-color').value,outline:Number($('#style-outline').value),margin_v:Number($('#style-margin').value),bold:$('#style-bold').checked};}
async function renderVideo(){
  try{if(!state.selected)throw new Error('Chưa chọn video.');await saveSegments(false);
    const result=await apiPost('/api/projects/'+state.selected.id+'/render',currentStyle());
    toast('Đã gửi lệnh render FFmpeg thực tế.');await refreshCurrent();}
  catch(e){showError(e);}
}
async function transcribe(){
  try{if(!state.selected)throw new Error('Chưa chọn dự án.'); await apiPost('/api/projects/'+state.selected.id+'/transcribe',{});toast('Đang phân tích âm thanh bằng Whisper offline.');await refreshCurrent();}
  catch(e){showError(e);}
}
async function translate(){
  try{if(!state.selected)throw new Error('Chưa chọn dự án.');await saveSegments(false);
    await apiPost('/api/projects/'+state.selected.id+'/translate',{source_language:$('#source-lang').value,target_language:'vi'});
    toast('Đang dịch bằng gói ngôn ngữ offline đã cài.');await refreshCurrent();}
  catch(e){showError(e);}
}
async function dubAudio(){
  try {
    if(!state.selected)throw new Error('Chưa chọn dự án.');
    const voice=$('#dub-voice').value;
    if(!voice)throw new Error('Hãy chọn một giọng tiếng Việt đã cài trên KokoroTTS.');
    await saveSegments(false);
    await apiPost('/api/projects/'+state.selected.id+'/dub',{voice});
    toast('Đang tổng hợp lời thoại và căn theo thời gian thật.');await refreshCurrent();
  }catch(e){showError(e);}
}
async function loadVoices(){
  const select=$('#dub-voice');select.replaceChildren();
  const fallback=document.createElement('option');fallback.value='';fallback.textContent='Chưa kết nối KokoroTTS';select.append(fallback);
  if(!state.capabilities?.tts_kokoro_local){text($('#voice-status'),'Chưa bật server giọng Việt');$('#dub-button').disabled=true;return;}
  try{
    const result=await request('/api/voices');
    let voices=Array.isArray(result)?result:Array.isArray(result?.voices)?result.voices:Array.isArray(result?.data)?result.data:[];
    const vietnamese=voices.filter(v=>{const name=String(v.name||v.label||'');const lang=String(v.language||v.lang||'');const id=String(v.id||v.voice_id||'');return /vietnam|tiếng việt|\bvi\b|^vi[_-]/i.test(name+' '+lang+' '+id)});
    voices=vietnamese.length?vietnamese:voices;
    for(const item of voices){const val=typeof item==='string'?item:(item.id||item.voice_id||item.name||'');if(!val)continue;const o=document.createElement('option');o.value=val;o.textContent=typeof item==='string'?item:(item.name||item.label||val);select.append(o);}
    if(voices.length){select.removeChild(fallback);text($('#voice-status'),voices.length+' giọng sẵn sàng');$('#dub-button').disabled=!state.selected||state.selected.status!=='ready';}
    else{text($('#voice-status'),'Chưa có danh sách giọng');}
  }catch(e){text($('#voice-status'),'Lỗi kết nối server giọng Việt');$('#dub-button').disabled=true;}
}
async function suggestStyle(){
  try {if(!state.selected)throw new Error('Chưa chọn video.');const result=await request('/api/projects/'+state.selected.id+'/reference-style');
    if(result.detected){$('#style-color').value=result.color;updateStylePreview();}
    toast(result.reason, !result.detected);
  }catch(e){showError(e);}
}
function updateStylePreview(){const s=currentStyle(),el=$('#style-demo-text');el.style.color=s.color;el.style.fontFamily='"'+s.font.replace(/"/g,'')+'",sans-serif';el.style.fontSize=Math.min(32,Number(s.font_size)/2.3)+'px';el.style.fontWeight=s.bold?'800':'400';el.style.webkitTextStroke=Math.min(4,Number(s.outline)/1.5)+'px '+s.outline_color;el.style.paintOrder='stroke fill';text($('#style-margin-label'),s.margin_v);}
async function refreshCurrent(){
  if(!state.selected)return;
  try {const prev=state.selected;const p=await request('/api/projects/'+prev.id);
    state.selected=p;const changed=JSON.stringify(p.segments)!==JSON.stringify(prev.segments) || p.export_url!==prev.export_url || p.video_url!==prev.video_url;
    // Do not discard unsaved edits on each poll. Only rerender segment fields when a job changes their data.
    if(changed || p.status==='ready'&&prev.status!==p.status) showProject(p);
    else {text($('#project-status'),statusText[p.status]||p.status);text($('#project-message'),`${p.message||''} ${ongoing.includes(p.status)?'('+p.progress+'%)':''}`);$('#progress-bar').style.width=p.progress+'%';$('#download-export').classList.toggle('hidden',!p.export_url);if(p.export_url)$('#download-export').href=p.export_url;}
    if(prev.status!==p.status&&p.status==='error')toast(p.message,true);
    if(prev.status!==p.status&&p.status==='ready')toast(p.message||'Đã xử lý xong.');
    managePolling();
  } catch(e) {showError(e);}
}
function managePolling(){clearInterval(state.polling);if(state.selected&&ongoing.includes(state.selected.status)){state.polling=setInterval(async()=>{await refreshCurrent();await loadProjects();},1800);}}
async function loadCapabilities(){
  try {const data=await request('/api/capabilities');state.capabilities=data;const labels={ffmpeg:'FFmpeg / xuất video',link_import:'Tải video 6 nền tảng',offline_transcription:'Whisper nhận dạng thoại',offline_translation:'Argos Translate',tts_kokoro_local:'Giọng Việt local (Kokoro)',ai_video_local:'AI video GPU cục bộ',gpu:'GPU CUDA'};
    const holder=$('#capability-list');holder.replaceChildren();Object.entries(labels).forEach(([key,label])=>{const row=document.createElement('div');row.className='capability';const dot=document.createElement('span');dot.className=data[key]?'yes':'no';dot.textContent=data[key]?'●':'○';const t=document.createElement('b');t.textContent=label;const status=document.createElement('small');status.textContent=data[key]?'Sẵn sàng':'Chưa cài';row.append(dot,t,status);holder.append(row);});
    $('#ai-generate').disabled=!data.ai_video_local;
    await loadVoices();
    text($('#ai-state'),data.ai_video_local?'Model local đã được cài. Tác vụ tạo video có thể tốn nhiều VRAM và thời gian.':'Chưa có GPU + model video tương thích. Tính năng khóa để không tạo kết quả giả.');
  }catch(e){showError(e);}
}
async function generateAI(){
  try{const prompt=$('#ai-prompt').value.trim();if(prompt.length<12)throw new Error('Mô tả cảnh cần ít nhất 12 ký tự.');
    const p=await apiPost('/api/ai/create-video',{prompt});toast('Đã gửi tác vụ tạo video đến GPU cục bộ.');await loadProjects();await selectProject(p.id);
  }catch(e){showError(e);}
}
function init(){
  $$('.nav-item').forEach(x=>x.addEventListener('click',()=>switchView(x.dataset.view)));
  $('#top-new').addEventListener('click',()=>{switchView('projects');$('#video-url').focus();});
  $('#add-url').addEventListener('click',addLink);
  $('#video-url').addEventListener('keydown',e=>{if(e.key==='Enter')addLink();});
  $('#video-upload').addEventListener('change',e=>upload(e.target.files?.[0]));
  const drop=$('#dropzone');drop.addEventListener('dragover',e=>{e.preventDefault();drop.classList.add('dragover')});drop.addEventListener('dragleave',()=>drop.classList.remove('dragover'));drop.addEventListener('drop',e=>{e.preventDefault();drop.classList.remove('dragover');upload(e.dataTransfer.files?.[0]);});
  $('#refresh-projects').addEventListener('click',loadProjects);
  $('#project-select').addEventListener('change',e=>selectProject(e.target.value));
  $('#refresh-current').addEventListener('click',refreshCurrent);
  $('#show-source').addEventListener('click',()=>{state.preview='source';showProject(state.selected);});
  $('#show-export').addEventListener('click',()=>{if(state.selected?.export_url){state.preview='export';showProject(state.selected);}});
  $('#recover-current').addEventListener('click',async()=>{
    try{if(!state.selected)throw new Error('Chưa chọn dự án.');
      const p=await apiPost('/api/projects/'+state.selected.id+'/recover',{});
      state.selected=p;showProject(p);toast('Đã khôi phục dự án.');await loadProjects();
    }catch(e){showError(e);}
  });
  $('#add-segment').addEventListener('click',()=>addSegment({start: Math.max(0,(state.selected?.duration||5)-3),end:state.selected?.duration||5,text:''}));
  $('#save-segments').addEventListener('click',()=>saveSegments().catch(showError));
  $('#render-button').addEventListener('click',renderVideo);
  $('#transcribe').addEventListener('click',transcribe);
  $('#translate').addEventListener('click',translate);
  $('#suggest-style').addEventListener('click',suggestStyle);
  $('#dub-button').addEventListener('click',dubAudio);
  $$('.seg-tab').forEach(btn=>btn.addEventListener('click',()=>{ $$('.seg-tab').forEach(x=>x.classList.toggle('active',x===btn));$('#edit-captions').classList.toggle('hidden',btn.dataset.editTab!=='captions');$('#edit-style').classList.toggle('hidden',btn.dataset.editTab!=='style'); }));
  ['style-font','style-size','style-color','style-outline-color','style-margin','style-bold'].forEach(id=>$('#'+id).addEventListener('input',()=>{updateStylePreview();updateCaptionOverlay();}));
  $('#segments').addEventListener('input',updateCaptionOverlay);
  $('#player').addEventListener('timeupdate',updateCaptionOverlay);
  $('#player').addEventListener('loadedmetadata',updateCaptionOverlay);
  $('#player').addEventListener('seeked',updateCaptionOverlay);
  window.addEventListener('resize',updateCaptionOverlay);
  $('#refresh-capabilities').addEventListener('click',loadCapabilities);
  $('#ai-generate').addEventListener('click',generateAI);
  updateStylePreview();loadProjects();loadCapabilities();
}
document.addEventListener('DOMContentLoaded',init);
