"use strict";
(() => {
  const LOCAL="http://127.0.0.1:8765";
  let connected=false, running=false, jobId=sessionStorage.getItem("cinemanova-job")||"";
  const statusEl=document.getElementById("connectorStatus");
  const workEl=document.getElementById("workflowArea");
  const makeBtn=document.getElementById("produce");
  const scriptBtn=document.getElementById("aiScript");
  const checkBtn=document.getElementById("checkConnection");
  const player=document.getElementById("moviePlayer");
  const downloadBtn=document.getElementById("downloadMovie");
  function say(text,kind="note"){statusEl.textContent=text;statusEl.style.color=kind==="ok"?"#76e3c1":kind==="error"?"#ffa5a5":"#cfc7ed";}
  function step(text){workEl.textContent=text;}
  function updateButton(){
    makeBtn.disabled=!approved||!connected||running;
    makeBtn.textContent=running?"ĐANG TẠO VIDEO...":connected?"▶ TẠO VIDEO QUA FLOWKIT":"TẠO VIDEO • CHƯA KẾT NỐI";
    scriptBtn.disabled=!connected||running;
  }
  const oldMark=markChanged;
  markChanged=function(){oldMark();updateButton();};
  document.getElementById("approve").addEventListener("click",updateButton);
  const oldRefresh=refresh;
  refresh=function(){oldRefresh();updateButton();};
  async function request(path,payload,timeout=20000){
    const ctl=new AbortController();
    const timeoutId=setTimeout(()=>ctl.abort(),timeout);
    try {
      const response=await fetch(LOCAL+path,{
        method:payload===undefined?"GET":"POST",
        headers:payload===undefined?{}:{"Content-Type":"application/json"},
        body:payload===undefined?undefined:JSON.stringify(payload),
        cache:"no-store",mode:"cors",signal:ctl.signal
      });
      const data=await response.json();
      if(!response.ok||data.ok===false)throw new Error(data.error||("HTTP "+response.status));
      return data;
    } catch(err){
      if(err.name==="TypeError"||err.name==="AbortError"){
        throw new Error("Không thể truy cập cầu nối Windows tại 127.0.0.1:8765. Hãy bật file MO_CINEMA_NOVA_CLOUD.bat (V1.6) trên máy đang dùng, cho phép Chrome truy cập mạng nội bộ khi được hỏi, rồi thử lại.");
      }
      throw err;
    } finally {clearTimeout(timeoutId);}
  }
  async function check(){
    checkBtn.disabled=true;say("Đang kiểm tra cầu nối CINEMA NOVA...");
    try{
      const ping=await request("/bridge/ping",undefined,8000);
      if(ping.version!=="1.6")throw new Error("Máy đang chạy phiên bản cầu nối cũ. Cần mở CINEMA NOVA Cloud Connector V1.6.");
      const s=await request("/bridge/status",undefined,18000);
      if(s.health?.extension_connected!==true)throw new Error("Cầu nối chạy nhưng tiện ích FlowKit chưa kết nối Google Flow. Kiểm tra Chrome và extension.");
      connected=true;
      say("✓ Đã kết nối FlowKit trên máy bạn. Có thể tạo video sau khi duyệt kịch bản.","ok");
      step("FlowKit đã kết nối. Sẵn sàng tạo ảnh và video khi bạn xác nhận.");
      if(jobId)resume(jobId);
    }catch(e){connected=false;say("Chưa kết nối: "+e.message,"error");}
    finally{checkBtn.disabled=false;updateButton();}
  }
  checkBtn.addEventListener("click",check);
  scriptBtn.addEventListener("click",async()=>{
    if(!connected){await check();if(!connected)return}
    if(!String(el("idea").value).trim()){alert("Hãy nhập ý tưởng phim trước.");return}
    scriptBtn.disabled=true;say("Gemini đang viết kịch bản, xin xem kết quả sau khi hoàn tất...");
    try {
      const d=await request("/bridge/script",{
        idea:el("idea").value,genre:el("genre").value,
        duration:Number(el("duration").value),characters:[el("character").value]
      },100000);
      scenes=d.scenes.map(x=>({action:String(x.visual||""),dialogue:String(x.audio||""),duration:Number(x.seconds||0)}));
      markChanged();refresh();
      say("✓ Kịch bản từ "+(d.provider||"AI")+" đã có lời thoại. Hãy đọc, chỉnh và duyệt.","ok");
      el("script").scrollIntoView({behavior:"smooth"});
    } catch(e){say("Chưa thể viết bằng AI: "+e.message,"error");}
    finally{updateButton();}
  });
  async function imageData(){
    const file=el("photo").files?.[0];
    if(!file)return "";
    if(file.size>1800000)throw new Error("Ảnh nhân vật vượt 1.8MB. Hãy chọn ảnh nhỏ hơn.");
    if(!["image/jpeg","image/png","image/webp"].includes(file.type))throw new Error("Ảnh cần định dạng JPG, PNG hoặc WebP.");
    return await new Promise((resolve,reject)=>{
      const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error("Không đọc được ảnh nhân vật"));reader.readAsDataURL(file);
    });
  }
  function mapData(photo){
    return {
      approved:true,title:el("title").value,idea:el("idea").value,
      synopsis:el("idea").value,genre:el("genre").value,
      duration:Number(el("duration").value),ratio:el("ratio").value,
      characters:[{name:el("character").value.trim()||"Nhân vật chính",
        description:"Nhân vật nhất quán trong mọi cảnh. "+el("idea").value.slice(0,350),
        data:photo}],
      scenes:scenes.map(s=>({seconds:Number(s.duration),visual:s.action,audio:s.dialogue}))
    };
  }
  async function create(){
    if(!approved)return alert("Bạn phải duyệt kịch bản trước khi tạo video.");
    if(!connected){await check();if(!connected)return;}
    if(jobId&&running)return;
    const confirmText="XÁC NHẬN SẢN XUẤT\n\nGửi "+scenes.length+" cảnh vào FlowKit và Google Flow? Hành động này có thể tiêu lượt/credit tạo video của tài khoản Google.\n\nChọn OK để bắt đầu.";
    if(!window.confirm(confirmText))return;
    running=true;updateButton();step("Đang gửi dự án và các cảnh đã duyệt vào FlowKit...");player.style.display="none";downloadBtn.style.display="none";
    try {
      const photo=await imageData();
      const receipt=await request("/bridge/publish",mapData(photo),120000);
      step("✓ Đã gửi "+scenes.length+" cảnh. Đang bắt đầu hàng đợi sản xuất...");
      const job=await request("/bridge/start",{receipt:receipt.receipt,confirmed:true},30000);
      jobId=job.job_id;sessionStorage.setItem("cinemanova-job",jobId);
      resume(jobId);
    }catch(e){running=false;step("✕ Không thể bắt đầu: "+e.message);updateButton();}
  }
  makeBtn.addEventListener("click",create);
  async function resume(id){
    running=true;updateButton();step("Đang đọc tiến độ FlowKit...");
    for(;;){
      if(document.visibilityState==="hidden"){await new Promise(r=>setTimeout(r,15000));}
      try{
        const response=await request("/bridge/job?job_id="+encodeURIComponent(id),undefined,12000);
        const job=response.job||{};
        step("Tác vụ "+id.slice(0,8)+" • "+(job.progress||job.step||"Đang thực hiện"));
        if(job.status==="completed"){
          running=false;jobId="";sessionStorage.removeItem("cinemanova-job");
          player.src=LOCAL+job.output;player.style.display="block";
          downloadBtn.style.display="inline-block";
          downloadBtn.onclick=()=>downloadVideo(LOCAL+job.output,id);
          step("✓ Đã ghép MP4 trên máy tính. Có thể xem và tải video bên dưới.");
          updateButton();return;
        }
        if(job.status==="failed"||job.status==="clips_ready"){
          running=false;jobId="";sessionStorage.removeItem("cinemanova-job");
          step(job.status==="failed"?"✕ Tạo phim lỗi: "+(job.error||"Không rõ nguyên nhân"):"Các clip đã hoàn thành trong FlowKit nhưng chưa ghép MP4. Kiểm tra FFmpeg trên máy.");
          updateButton();return;
        }
      }catch(e){running=false;jobId="";sessionStorage.removeItem("cinemanova-job");step("Không lấy được tiến độ: "+e.message);updateButton();return;}
      await new Promise(r=>setTimeout(r,8000));
    }
  }
  async function downloadVideo(url,id){
    try{downloadBtn.disabled=true;const r=await fetch(url,{mode:"cors"});if(!r.ok)throw new Error("HTTP "+r.status);const blob=await r.blob();const u=URL.createObjectURL(blob);const a=document.createElement("a");a.href=u;a.download="cinema-nova-"+id.slice(0,8)+".mp4";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),4000)}
    catch(e){alert("Không tải được MP4: "+e.message)}finally{downloadBtn.disabled=false}
  }
  updateButton();
  // Probe once on page load; network permission may be requested by the browser.
  check();
})();