/* VietFrame Studio — no mock data, no fake video processing. */
'use strict';
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const state = { csrf: '', accountEmail: '', projects: [], selected: null, capabilities: null, polling: null, view: 'projects', preview: 'source', cleanupDraft: [], elevenlabsConnected: false };
const statusText = { ready: 'Sẵn sàng', queued: 'Đang xếp hàng', downloading: 'Đang tải video', transcribing: 'Nhận dạng thoại', translating: 'Đang dịch', rendering: 'Đang xuất MP4', finishing: 'Đang tạo video hoàn chỉnh', analyzing: 'Gemini đang phân tích video', dubbing: 'Đang lồng tiếng', generating: 'Đang tạo AI', error: 'Có lỗi' };
const ongoing = ['queued','downloading','uploading','transcribing','translating','rendering','dubbing','generating','finishing','analyzing'];

function toast(message, error=false) {
  const el = $('#toast'); el.textContent = message; el.className = error ? 'visible error' : 'visible';
  clearTimeout(toast.timer); toast.timer = setTimeout(() => el.className = '', 6000);
}
async function request(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers || {});
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && state.csrf) headers.set('X-CSRF-Token', state.csrf);
  const response = await fetch(url, {...options, headers, credentials:'same-origin'});
  if (response.status === 401) { window.location.replace('/login'); throw new Error('Phiên đã hết hạn.'); }
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
  if (view === 'settings') { loadCapabilities(); loadElevenStatus(); loadGeminiStatus(); }
}
function showError(error) { toast(error?.message || 'Có lỗi chưa xác định.', true); }
function consent() {
  const box = $('#license-ok');
  if (!box.checked) {
    const wrapper = box.closest('.consent');
    if (wrapper) wrapper.classList.add('needs-confirmation');
    box.scrollIntoView({behavior:'smooth', block:'center'});
    box.focus({preventScroll:true});
    throw new Error('Link đã nhận diện. Hãy tích ô xác nhận quyền sử dụng video bên dưới, rồi bấm tải lại.');
  }
  box.closest('.consent')?.classList.remove('needs-confirmation');
}

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
    const limit=state.capabilities?.max_upload_mb || 25;
    if (file.size > limit * 1024 * 1024) throw new Error('Tệp vượt giới hạn '+limit+' MB của máy chủ.');
    const data = new FormData(); data.append('file', file); data.append('title',file.name); data.append('license_confirmed','true');
    toast(`Đang gửi ${file.name}…`);
    const p = await request('/api/projects/upload', {method:'POST',body:data});
    toast('Tải video lên thành công.'); await loadProjects(); await selectProject(p.id);
  } catch(e) { showError(e); }
  finally { $('#video-upload').value = ''; }
}
async function uploadFailedProjectFile(file) {
  if (!file || !state.selected) return;
  const pid=state.selected.id;
  if (!$('#recovery-license').checked) return showError(new Error('Hãy xác nhận quyền sử dụng video.'));
  const max=state.capabilities?.max_upload_mb || 25;
  if (file.size>max*1024*1024) return showError(new Error('Tệp vượt giới hạn '+max+' MB trên Render.'));
  const input=$('#recovery-file');input.disabled=true;
  try {
    const data=new FormData(); data.append('file',file); data.append('license_confirmed','true');
    toast('Đang chuyển tệp vào dự án lỗi…');
    const project=await request('/api/projects/'+pid+'/replace-source',{method:'POST',body:data});
    state.preview='source';state.selected=project;
    showProject(project);
    await loadProjects();
    toast('Đã nhập video gốc vào dự án. Bạn có thể dùng Gemini và biên tập tiếp.');
  } catch(e){showError(e);} finally {
    input.value='';
    input.disabled=!$('#recovery-license').checked;
  }
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

const jobPhases = {
  analyzing: ['Gửi video','Gemini xử lý','Viết phụ đề Việt','Kiểm tra câu thoại'],
  downloading: ['Xác minh nguồn','Tải video','Kiểm tra MP4'],
  dubbing: ['Kiểm tra hạn mức','Tạo giọng từng câu','Căn chỉnh âm thanh'],
  finishing: ['Chuẩn bị âm thanh','Lồng tiếng','Xuất MP4'],
  rendering: ['Chuẩn bị phụ đề','FFmpeg xuất MP4','Kiểm tra tệp'],
  uploading: ['Nhận tệp thay thế','Kiểm tra video'],
  transcribing: ['Nhận dạng âm thanh','Kiểm tra phụ đề'],
  translating: ['Dịch lời thoại','Kiểm tra phụ đề'],
  generating: ['Kiểm tra GPU','Tạo video'],
  queued: ['Xếp hàng','Đang xử lý']
};
function renderJobProgress(project) {
  const panel=$('#job-progress');
  if (!project) {panel.classList.add('hidden');return;}
  panel.classList.remove('hidden');
  const active=ongoing.includes(project.status),failed=project.status==='error';
  const percent=failed?0:active?Math.max(0,Math.min(99,Number(project.progress)||0)):100;
  const name=failed?'Tác vụ đã dừng vì lỗi':active?(statusText[project.status]||'Đang xử lý'):'Đã hoàn thành bước xử lý';
  text($('#job-title'),name);
  text($('#job-percent'),failed?'Có lỗi':percent+'%');
  panel.classList.toggle('failed',failed);
  panel.classList.toggle('complete',!active&&!failed);
  const meter=$('#job-meter');
  meter.setAttribute('aria-valuenow',String(percent));
  meter.setAttribute('aria-valuetext',failed?'Tác vụ đã lỗi':active?'Đã tới mốc công việc '+percent+' phần trăm':'Sẵn sàng');
  $('#job-meter-fill').style.width=percent+'%';
  const steps=$('#job-steps');steps.replaceChildren();
  const items=jobPhases[project.status]||(failed?['Đã dừng']:['Sẵn sàng chỉnh sửa']);
  // The milestones correspond to server-confirmed actions; never animate fabricated completion.
  const current=project.status==='analyzing'?(percent>=91?3:percent>=67?2:percent>=46?1:0):
    active?(percent>=90?items.length-1:percent>=55?Math.min(1,items.length-1):0):0;
  items.forEach((name,i)=>{if(!name)return;const chip=document.createElement('span');chip.className='job-step'+(i<current?' done':i===current?' current':'');chip.textContent=(i<current?'✓ ':i===current&&active?'● ':'○ ')+name;steps.append(chip);});
  text($('#job-note'),project.message||(active?'Máy chủ đang xử lý video…':'Chọn thao tác tiếp theo.'));
  if(active){$('#job-percent').setAttribute('title','Phần trăm biểu thị mốc đã đạt, không phải thời gian còn lại.');}
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
  $('#import-recovery').classList.toggle('hidden',!(p?.status==='error' && !p?.video_url));
  if (!p) {$('#player').removeAttribute('src');$('#player').load();}
  text($('#project-status'),p ? (statusText[p.status]||p.status):'Chưa chọn');
  text($('#project-message'),p ? `${p.message || 'Video đã được nạp.'}  ${ongoing.includes(p.status) ? `(${p.progress}%)` : ''}` : 'Chọn một dự án để thao tác.');
  $('#progress-bar').style.width = `${p?.progress||0}%`;
  renderJobProgress(p);
  $('#download-export').classList.toggle('hidden', !p?.export_url);
  $('#download-srt').classList.toggle('hidden', !p?.segments?.length);
  $('#dub-preview').classList.toggle('hidden', !p?.dub_url);
  if (p?.dub_url) $('#dub-preview').src=p.dub_url;
  if (p?.export_url) $('#download-export').href=p.export_url;
  if (p?.id) $('#download-srt').href=`/api/projects/${p.id}/subtitles.srt`;
  $('#voice-report').classList.toggle('hidden',!p?.dub_file);
  if(p?.dub_file) $('#voice-report').href=`/api/projects/${p.id}/voice-timing-report`;
  const editable=p?.status==='ready';
  $('#gemini-prerequisite').classList.toggle('hidden',!!p?.video_url);
  ['render-button','complete-video-button','gemini-script-button','save-segments','transcribe','translate','add-segment'].forEach(id => $(`#${id}`).disabled = !editable);
  $('#dub-button').disabled=!editable||$('#voice-provider').value==='original'||!$('#dub-voice').value;
  state.cleanupDraft = p?.cleanup_regions?.map(r=>({...r})) || [];
  renderCleanupList();
  renderSegments(p?.segments||[]);
  refreshSpeakerVoices();
  updateCaptionOverlay();
  updateCleanupOverlay();
}
function makeInput(type,value,cls){const input=document.createElement(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.className=cls;input.value=value;return input;}
function addSegment(seg = {start:0,end:2.5,text:''}) {
  const holder=$('#segments');holder.querySelector('.tip')?.remove();
  const item=document.createElement('div');item.className='segment-card';item.dataset.sourceText=seg.source_text||'';item.dataset.needsReview=String(!!seg.needs_review);
  const top=document.createElement('div');top.className='segment-top';const label=document.createElement('span');label.textContent='ĐOẠN '+(holder.querySelectorAll('.segment-card').length+1);
  const remove=document.createElement('button');remove.type='button';remove.textContent='×';remove.title='Xóa câu';remove.addEventListener('click',()=>{item.remove();renumberSegments();});top.append(label,remove);
  const times=document.createElement('div');times.className='segment-time';
  const startLabel=document.createElement('label');startLabel.textContent='Bắt đầu';startLabel.append(makeInput('text',formatSeconds(seg.start),'seg-start'));
  const endLabel=document.createElement('label');endLabel.textContent='Kết thúc';endLabel.append(makeInput('text',formatSeconds(seg.end),'seg-end'));
  times.append(startLabel,endLabel);
  const content=makeInput('textarea',seg.text,'segment-text');content.placeholder='Phụ đề tiếng Việt…';content.rows=2;
  const voiceLabel=document.createElement('label');voiceLabel.className='voice-line-label';voiceLabel.textContent='Thoại cho ElevenLabs · chỉnh sao cho vừa cảnh';
  const voiceInput=makeInput('textarea',seg.voice_text||seg.text,'segment-voice-text');voiceInput.rows=2;voiceLabel.append(voiceInput);
  const speakerLabel=document.createElement('label');speakerLabel.className='voice-speaker-label';speakerLabel.textContent='Nhân vật';
  const speakerInput=makeInput('text',seg.speaker||'spk1','segment-speaker');speakerInput.pattern='spk[0-9]+';speakerLabel.append(speakerInput);
  const origin=document.createElement('small');origin.className='source-line';origin.textContent=seg.source_text?'Nguyên văn: '+seg.source_text:'';
  if(seg.needs_review){const flag=document.createElement('small');flag.className='review-flag';flag.textContent='Cần kiểm tra lại thời gian/thoại với video gốc';item.append(flag);}
  item.append(top,times,content,voiceLabel,speakerLabel,origin);holder.append(item);
}
function renumberSegments(){ $$('#segments .segment-card').forEach((el,i)=>text(el.querySelector('.segment-top span'),'ĐOẠN '+(i+1))); }
function renderSegments(items) { const container=$('#segments');container.replaceChildren();if(!items.length){const tip=document.createElement('div');tip.className='tip';tip.textContent='Nhập hoặc nhận dạng lời thoại để bắt đầu.';container.append(tip);return;}items.forEach(addSegment); }
function collectSegments() {
  return $$('#segments .segment-card').map((el,i) => {
    const existing=state.selected?.segments?.[i];
    const textValue=el.querySelector('.segment-text').value.trim();
    const spoken=el.querySelector('.segment-voice-text')?.value.trim() || textValue;
    const speaker=el.querySelector('.segment-speaker')?.value.trim() || 'spk1';
    const val={start:parseSeconds(el.querySelector('.seg-start').value),end:parseSeconds(el.querySelector('.seg-end').value),text:textValue,voice_text:spoken,speaker};
    if(el.dataset.sourceText) val.source_text=el.dataset.sourceText;
    if(el.dataset.needsReview==='true')val.needs_review=true;
    return val;
  });
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
function collectVoiceMap(){
  const map={};
  for(const row of $$('#speaker-voices [data-speaker]')){
    const voice=row.querySelector('select')?.value;
    if(voice)map[row.dataset.speaker]=voice;
  }
  return map;
}
async function completeVideo(){
  const button=$('#complete-video-button');
  try{
    if(!state.selected) throw new Error('Chưa chọn video.');
    button.disabled=true;
    await saveSegments(false);
    // Save currently selected text/logo search regions before processing.
    const p=await request('/api/projects/'+state.selected.id+'/cleanup',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({regions:state.cleanupDraft})});
    state.selected=p;
    const provider=$('#voice-provider').value;
    const voice=provider==='original'?null:$('#dub-voice').value;
    if(provider!=='original' && !voice) throw new Error('Hãy liên kết ElevenLabs và chọn một giọng trước khi tạo.');
    await apiPost('/api/projects/'+state.selected.id+'/complete-video', {style:currentStyle(), voice_provider:provider, voice,
      voice_map:collectVoiceMap()});
    toast('Đang tạo video thật: xử lý chữ/logo, đồng bộ giọng và xuất MP4.');
    await refreshCurrent();
  }catch(e){showError(e);}finally{button.disabled=state.selected?.status!=='ready';}
}
function detectLinkPlatform(){
  const raw=$('#video-url').value.trim(),label=$('#link-detect');
  if (!raw) { text(label,'Dán link để nhận diện nền tảng video.'); return; }
  try {
    const parsed=new URL(raw);
    if(parsed.protocol!=='https:') throw new Error('HTTPS only');
    const host=parsed.hostname.toLowerCase().replace(/^www\./,'');
    const families=[['youtube.com','YouTube'],['youtu.be','YouTube'],['facebook.com','Facebook'],['fb.watch','Facebook'],['tiktok.com','TikTok'],['vt.tiktok.com','TikTok'],['douyin.com','Douyin'],['v.douyin.com','Douyin'],['bilibili.com','Bilibili'],['b23.tv','Bilibili'],['instagram.com','Instagram']];
    const match=families.find(([suffix])=>host===suffix||host.endsWith('.'+suffix));
    if (!match) { text(label,'Link chưa thuộc 6 nền tảng được hỗ trợ.'); return; }
    let kind=match[1];
    if(kind==='YouTube' && /^\/shorts\//i.test(parsed.pathname)) {
      const videoId=parsed.pathname.split('/')[2]||'';
      if (!/^[A-Za-z0-9_-]{11}$/.test(videoId)) {
        text(label,'Đây là link YouTube Shorts nhưng mã video chưa hợp lệ (cần 11 ký tự).');
        return;
      }
      kind='YouTube Shorts';
    }
    const confirmed=$('#license-ok').checked;
    text(label,'Đã nhận diện: '+kind+(confirmed
      ? ' · Sẵn sàng thử tải video thật. Bấm nút bên phải.'
      : ' · Hãy tích ô xác nhận quyền sử dụng video ở dưới rồi bấm tải.'));
  } catch { text(label,'Link chưa hợp lệ. Hãy dán URL HTTPS đầy đủ.'); }
}

function showIntegrationConnection(provider, kind, title, detail) {
  const card = $('#'+provider+'-connection');
  if (!card) return;
  card.dataset.state = kind;
  text($('#'+provider+'-connection-title'), title);
  text($('#'+provider+'-status'), detail);
  text(card.querySelector('.integration-check'), kind === 'connected' || kind === 'limited' ? '✓' : kind === 'error' ? '!' : '·');
}
async function loadGeminiStatus(){
  try{
    const s=await request('/api/integrations/gemini');
    showIntegrationConnection('gemini',s.connected?'connected':'disconnected',
      s.connected?'Đã kết nối Gemini thành công':'Chưa kết nối Gemini',
      s.connected?'API key đã xác minh khi liên kết · Model: '+(s.model||'chưa xác định')+'. Lưu ý: tạo phụ đề vẫn cần kiểm tra riêng trên video thật.':'Nhập Gemini API key Free Tier để kết nối.');
    $('#gemini-disconnect').disabled=!s.connected;
    $('#gemini-link-form button[type=submit]').textContent=s.connected?'Cập nhật API key Gemini':'Kết nối Gemini';
    if(s.connected && s.model)$('#gemini-model').value=s.model;
  }catch(e){
    showIntegrationConnection('gemini','error','Không kiểm tra được Gemini',e.message);
    showError(e);
  }
}
async function linkGemini(event){
  event.preventDefault();
  const api_key=$('#gemini-api-key').value.trim();
  try{
    const s=await apiPost('/api/integrations/gemini/link',{api_key,model:$('#gemini-model').value});
    $('#gemini-api-key').value='';
    toast('Đã kết nối Gemini thành công · '+s.model+'. Phân tích video được kiểm tra riêng.');
    await loadGeminiStatus();
  }catch(e){showError(e);}
}
async function unlinkGemini(){
  try{
    await request('/api/integrations/gemini',{method:'DELETE'});
    toast('Đã ngắt kết nối Gemini.');await loadGeminiStatus();
  }catch(e){showError(e);}
}
async function analyzeGeminiScript(){
  try{
    if(!state.selected?.video_file)throw new Error('Chọn hoặc tải video lên trước.');
    if(!window.confirm('Cho phép VietFrame gửi bản sao video này tới Gemini để nhận diện thoại và tạo lời Việt?'))return;
    await apiPost('/api/projects/'+state.selected.id+'/gemini-script',{});
    toast('Gemini đang phân tích nội dung thật của video và viết thoại khớp thời gian.');
    await refreshCurrent();
  }catch(e){showError(e);}
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
    if(!voice)throw new Error('Hãy chọn giọng phù hợp với nhà cung cấp đang kết nối.');
    await saveSegments(false);
    await apiPost('/api/projects/'+state.selected.id+'/dub',{voice,provider:$('#voice-provider').value});
    toast('Đang tổng hợp lời thoại và căn theo thời gian thật.');await refreshCurrent();
  }catch(e){showError(e);}
}
async function loadVoices(){
  const select=$('#dub-voice');select.replaceChildren();
  const provider=$('#voice-provider').value;
  const fallback=document.createElement('option');fallback.value='';fallback.textContent=provider==='kokoro'?'Chưa kết nối KokoroTTS':'Chưa liên kết ElevenLabs';select.append(fallback);
  $('#dub-button').disabled=true;
  if(provider==='original'){text($('#voice-status'),'Giữ âm thanh gốc · miễn phí');return;}
  if(provider==='kokoro' && !state.capabilities?.tts_kokoro_local){text($('#voice-status'),'Chưa bật giọng local');return;}
  try{
    const result=await request(provider==='kokoro'?'/api/voices':'/api/integrations/elevenlabs/voices');
    let voices=Array.isArray(result)?result:Array.isArray(result?.voices)?result.voices:Array.isArray(result?.data)?result.data:[];
    if(provider==='kokoro'){
      const vietnamese=voices.filter(v=>{const name=String(v.name||v.label||'');const lang=String(v.language||v.lang||'');const id=String(v.id||v.voice_id||'');return /vietnam|tiếng việt|\bvi\b|^vi[_-]/i.test(name+' '+lang+' '+id)});
      voices=vietnamese.length?vietnamese:voices;
    }
    for(const item of voices){const val=typeof item==='string'?item:(item.id||item.voice_id||item.name||'');if(!val)continue;const o=document.createElement('option');o.value=val;o.textContent=typeof item==='string'?item:(item.name||item.label||val);select.append(o);}
    if(voices.length){select.removeChild(fallback);text($('#voice-status'),provider==='elevenlabs'?'✓ ElevenLabs đã kết nối · '+voices.length+' giọng khả dụng':voices.length+' giọng khả dụng');$('#dub-button').disabled=!state.selected||state.selected.status!=='ready';}
    else{text($('#voice-status'),'Không có giọng khả dụng trên gói API này');}
  }catch(e){text($('#voice-status'),e.message);$('#dub-button').disabled=true;}
}
function refreshSpeakerVoices(){
  const container=$('#speaker-voices');container.replaceChildren();
  const speakers=[...new Set((state.selected?.segments||[]).map(s=>s.speaker||'spk1'))].sort();
  const options=[...$('#dub-voice').options].filter(o=>o.value).map(o=>({value:o.value,name:o.textContent}));
  if(speakers.length<2 || $('#voice-provider').value==='original')return;
  const hint=document.createElement('small');hint.textContent='Chọn giọng riêng cho từng nhân vật (không bắt buộc)';container.append(hint);
  for(const speaker of speakers){
    const wrapper=document.createElement('label');wrapper.dataset.speaker=speaker;wrapper.textContent=speaker+' · ';
    const select=document.createElement('select');const same=document.createElement('option');same.value='';same.textContent='Giọng mặc định';select.append(same);
    for(const opt of options){const item=document.createElement('option');item.value=opt.value;item.textContent=opt.name;select.append(item);}
    wrapper.append(select);container.append(wrapper);
  }
}

async function loadElevenStatus(){
  try{
    const s=await request('/api/integrations/elevenlabs');
    state.elevenlabsConnected=!!s.connected;
    const limited=!!s.limited;
    showIntegrationConnection('elevenlabs',!s.connected?'disconnected':limited?'limited':'connected',
      s.connected?'Đã kết nối ElevenLabs thành công':'Chưa kết nối ElevenLabs',
      !s.connected?'Nhập API key một lần để chọn giọng.'
        :limited?'API đã xác minh quyền đọc giọng. Chưa thể xác minh hạn mức Free; cần User → Read trước khi tạo tiếng.'
        :'Tài khoản: '+(s.label||'ElevenLabs')+' · API key được lưu mã hóa. Hạn mức Free được kiểm tra trước khi tạo giọng.');
    $('#elevenlabs-disconnect').disabled=!s.connected;
    $('#elevenlabs-link-form button[type=submit]').textContent=s.connected?'Thay API key ElevenLabs':'Liên kết tài khoản';
  }catch(e){
    showIntegrationConnection('elevenlabs','error','Không kiểm tra được ElevenLabs',e.message);
  }
}
async function linkEleven(event){
 event.preventDefault();const input=$('#elevenlabs-api-key'),button=$('#elevenlabs-link-form button[type=submit]');button.disabled=true;
 try{const result=await apiPost('/api/integrations/elevenlabs/link',{api_key:input.value});input.value='';await loadElevenStatus();$('#voice-provider').value='elevenlabs';await loadVoices();if(result.warning){toast('Đã kết nối ElevenLabs để chọn giọng. Cần thêm User → Read trước khi tạo tiếng.',true);}else{toast('Đã kết nối ElevenLabs thành công.');}}
 catch(e){text($('#elevenlabs-status'), 'Không thể liên kết: '+e.message);showError(e);}finally{input.value='';button.disabled=false;}
}
async function unlinkEleven(){
 try{await request('/api/integrations/elevenlabs',{method:'DELETE'});toast('Đã ngắt ElevenLabs.');await loadElevenStatus();$('#voice-provider').value='kokoro';await loadVoices();}catch(e){showError(e);}
}
function updateCleanupOverlay(){
 const mask=$('#cleanup-overlay'),player=$('#player'),screen=$('.screen');
 if(!state.selected||!player.videoWidth||state.preview==='export'||!state.cleanupDraft?.length){mask.style.display='none';return;}
 const region=state.cleanupDraft[0], videoBox=player.getBoundingClientRect(), screenBox=screen.getBoundingClientRect();
 const scale=Math.min(videoBox.width/player.videoWidth,videoBox.height/player.videoHeight);
 const actualW=player.videoWidth*scale,actualH=player.videoHeight*scale;
 const left=videoBox.left-screenBox.left+(videoBox.width-actualW)/2;
 const top=videoBox.top-screenBox.top+(videoBox.height-actualH)/2;
 mask.style.cssText=`display:block;left:${left+region.x*actualW/100}px;top:${top+region.y*actualH/100}px;width:${region.w*actualW/100}px;height:${region.h*actualH/100}px`;
}
function renderCleanupList(){
 const host=$('#cleanup-list');host.replaceChildren();
 (state.cleanupDraft||[]).forEach((r,i)=>{
  const row=document.createElement('div');row.className='cleanup-row';
  const label=document.createElement('span');label.textContent=`Vùng ${i+1}: x ${r.x}%, y ${r.y}%, rộng ${r.w}%, cao ${r.h}%`;
  const remove=document.createElement('button');remove.type='button';remove.className='text-button';remove.textContent='Xóa';remove.addEventListener('click',()=>{state.cleanupDraft.splice(i,1);renderCleanupList();});
  row.append(label,remove);host.append(row);
 });
}
function presetCleanup(x,y,w,h){$('#cleanup-x').value=x;$('#cleanup-y').value=y;$('#cleanup-w').value=w;$('#cleanup-h').value=h; const r={x,y,w,h};const saved=state.cleanupDraft;state.cleanupDraft=[r];updateCleanupOverlay();state.cleanupDraft=saved;}
function addCleanup(){
 if(state.cleanupDraft.length>=3)throw new Error('Tối đa 3 vùng che.');
 const r=Object.fromEntries(['x','y','w','h'].map(k=>[k,Number($('#cleanup-'+k).value)]));
 if(!Object.values(r).every(Number.isInteger)||r.x<0||r.y<0||r.w<2||r.h<2||r.x+r.w>100||r.y+r.h>100)throw new Error('Vùng che vượt khỏi khung video.');
 state.cleanupDraft.push(r);renderCleanupList();
}
async function saveCleanup(){
 if(!state.selected)throw new Error('Chưa chọn dự án.');
 const p=await request('/api/projects/'+state.selected.id+'/cleanup',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({regions:state.cleanupDraft})});
 state.selected=p;showProject(p);toast('Đã lưu các vùng che. Bấm Xuất MP4 để tái tạo nền và chèn chữ Việt.');
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
    else {text($('#project-status'),statusText[p.status]||p.status);text($('#project-message'),`${p.message||''} ${ongoing.includes(p.status)?'('+p.progress+'%)':''}`);$('#progress-bar').style.width=p.progress+'%';renderJobProgress(p);$('#download-export').classList.toggle('hidden',!p.export_url);if(p.export_url)$('#download-export').href=p.export_url;}
    if(prev.status!==p.status&&p.status==='error')toast(p.message,true);
    if(prev.status!==p.status&&p.status==='ready')toast(p.message||'Đã xử lý xong.');
    managePolling();
  } catch(e) {showError(e);}
}
function managePolling(){clearInterval(state.polling);if(state.selected&&ongoing.includes(state.selected.status)){state.polling=setInterval(async()=>{await refreshCurrent();await loadProjects();},1800);}}
async function loadCapabilities(){
  try {const data=await request('/api/capabilities');state.capabilities=data;const labels={ffmpeg:'FFmpeg / xuất video',link_import:'Tải video 6 nền tảng',offline_transcription:'Whisper nhận dạng thoại',offline_translation:'Argos Translate',tts_kokoro_local:'Giọng Việt local (Kokoro)',elevenlabs_link_supported:'Kết nối ElevenLabs (1 lần)',gemini_video_script_supported:'Gemini phân tích video & thoại Việt',static_text_cleanup:'Che chữ/logo cố định',ai_video_local:'AI video GPU cục bộ',gpu:'GPU CUDA'};
    const holder=$('#capability-list');holder.replaceChildren();Object.entries(labels).forEach(([key,label])=>{const row=document.createElement('div');row.className='capability';const dot=document.createElement('span');dot.className=data[key]?'yes':'no';dot.textContent=data[key]?'●':'○';const t=document.createElement('b');t.textContent=label;const status=document.createElement('small');status.textContent=data[key]?'Sẵn sàng':'Chưa cài';row.append(dot,t,status);holder.append(row);});
    $('#ai-generate').disabled=!data.ai_video_local;
    const lim=data.max_upload_mb||25,dur=data.max_duration_seconds||120;
    text($('#upload-limit'),`MP4, MOV, WEBM, MKV · tối đa ${lim} MB · ${dur} giây`);
    text($('#recovery-limit'),`Giới hạn tải lên: ${lim} MB, ${dur} giây. Lời thoại Gemini/ElevenLabs chỉ chạy sau khi có video thật.`);
    await loadVoices();
    text($('#ai-state'),data.ai_video_local?'Model local đã được cài. Tác vụ tạo video có thể tốn nhiều VRAM và thời gian.':'Chưa có GPU + model video tương thích. Tính năng khóa để không tạo kết quả giả.');
  }catch(e){showError(e);}
}
async function generateAI(){
  try{const prompt=$('#ai-prompt').value.trim();if(prompt.length<12)throw new Error('Mô tả cảnh cần ít nhất 12 ký tự.');
    const p=await apiPost('/api/ai/create-video',{prompt});toast('Đã gửi tác vụ tạo video đến GPU cục bộ.');await loadProjects();await selectProject(p.id);
  }catch(e){showError(e);}
}
async function authorize(){
  try {
    const identity = await request('/api/auth/me');
    state.csrf = identity.csrf;
    state.accountEmail = identity.email;
    text($('#account-email'), identity.email);
    init();
  } catch (_) { window.location.replace('/login'); }
}
async function signOut(){
  try { await apiPost('/api/auth/logout', {}); }
  finally { window.location.replace('/login'); }
}
async function changePassword(event){
  event.preventDefault();
  const old_password=$('#current-password').value;
  const new_password=$('#new-password').value;
  const submit=$('#change-password-form button[type="submit"]');
  submit.disabled=true;
  try {
    await apiPost('/api/auth/change-password',{old_password,new_password});
    $('#change-password-form').reset();
    window.location.replace('/login');
  } catch(e){ text($('#password-message'),e.message); toast(e.message,true); }
  finally {submit.disabled=false;}
}
function init(){
  $('#logout-button').addEventListener('click',signOut);
  $('#change-password-form').addEventListener('submit',changePassword);
  $$('.nav-item').forEach(x=>x.addEventListener('click',()=>switchView(x.dataset.view)));
  $('#top-new').addEventListener('click',()=>{switchView('projects');$('#video-url').focus();});
  $('#license-ok').addEventListener('change', () => {
    if ($('#license-ok').checked) $('#license-ok').closest('.consent')?.classList.remove('needs-confirmation');
    detectLinkPlatform();
  });
  $('#add-url').addEventListener('click',addLink);
  $('#video-url').addEventListener('keydown',e=>{if(e.key==='Enter')addLink();});
  $('#video-upload').addEventListener('change',e=>upload(e.target.files?.[0]));
  $('#recovery-license').addEventListener('change',e=>{
    $('#recovery-file').disabled=!e.target.checked;
    $('#recovery-file-label').setAttribute('aria-disabled',String(!e.target.checked));
  });
  $('#recovery-file').addEventListener('change',e=>uploadFailedProjectFile(e.target.files?.[0]));
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
  $('#complete-video-button').addEventListener('click',completeVideo);
  $('#open-eleven-settings').addEventListener('click',()=>{switchView('settings');$('#elevenlabs-api-key').focus();});
  $('#video-url').addEventListener('input',detectLinkPlatform);
  $('#transcribe').addEventListener('click',transcribe);
  $('#gemini-script-button').addEventListener('click',analyzeGeminiScript);
  $('#gemini-link-form').addEventListener('submit',linkGemini);
  $('#gemini-disconnect').addEventListener('click',unlinkGemini);
  $('#translate').addEventListener('click',translate);
  $('#suggest-style').addEventListener('click',suggestStyle);
  $('#dub-button').addEventListener('click',dubAudio);
  $('#voice-provider').addEventListener('change',async()=>{await loadVoices();refreshSpeakerVoices();});
  $('#elevenlabs-link-form').addEventListener('submit',linkEleven);
  $('#elevenlabs-disconnect').addEventListener('click',unlinkEleven);
  $('#cleanup-subtitle-preset').addEventListener('click',()=>presetCleanup(10,78,78,9));
  $('#cleanup-logo-preset').addEventListener('click',()=>presetCleanup(77,3,20,12));
  ['cleanup-x','cleanup-y','cleanup-w','cleanup-h'].forEach(id=>$('#'+id).addEventListener('input',()=>{ const r={x:Number($('#cleanup-x').value),y:Number($('#cleanup-y').value),w:Number($('#cleanup-w').value),h:Number($('#cleanup-h').value)}; const saved=state.cleanupDraft;state.cleanupDraft=[r];updateCleanupOverlay();state.cleanupDraft=saved; }));
  $('#cleanup-add').addEventListener('click',()=>{try{addCleanup();}catch(e){showError(e);}});
  $('#cleanup-save').addEventListener('click',()=>saveCleanup().catch(showError));
  $$('.seg-tab').forEach(btn=>btn.addEventListener('click',()=>{ $$('.seg-tab').forEach(x=>x.classList.toggle('active',x===btn));$('#edit-captions').classList.toggle('hidden',btn.dataset.editTab!=='captions');$('#edit-style').classList.toggle('hidden',btn.dataset.editTab!=='style');$('#edit-cleanup').classList.toggle('hidden',btn.dataset.editTab!=='cleanup'); }));
  ['style-font','style-size','style-color','style-outline-color','style-margin','style-bold'].forEach(id=>$('#'+id).addEventListener('input',()=>{updateStylePreview();updateCaptionOverlay();}));
  $('#segments').addEventListener('input',updateCaptionOverlay);
  $('#player').addEventListener('timeupdate',updateCaptionOverlay);
  $('#player').addEventListener('loadedmetadata',()=>{updateCaptionOverlay();updateCleanupOverlay();});
  $('#player').addEventListener('seeked',updateCaptionOverlay);
  window.addEventListener('resize',()=>{updateCaptionOverlay();updateCleanupOverlay();});
  $('#refresh-capabilities').addEventListener('click',loadCapabilities);
  $('#ai-generate').addEventListener('click',generateAI);
  updateStylePreview();loadProjects();(async()=>{await loadElevenStatus();await loadGeminiStatus();await loadCapabilities();})();
}
document.addEventListener('DOMContentLoaded',authorize);
