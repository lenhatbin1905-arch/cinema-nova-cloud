"use strict";
(() => {
  const LOCAL="http://127.0.0.1:8765";
  let connected=false;
  const statusEl=document.getElementById("connectorStatus"), workEl=document.getElementById("workflowArea");
  const makeBtn=document.getElementById("produce"), scriptBtn=document.getElementById("aiScript"), checkBtn=document.getElementById("checkConnection");
  const tokenInput=document.getElementById("pairingToken"), tokenKey="cinema-nova-pairing-token";
  tokenInput.value=sessionStorage.getItem(tokenKey)||"";
  function say(text,kind="note"){statusEl.textContent=text;statusEl.style.color=kind==="ok"?"#76e3c1":kind==="error"?"#ffa5a5":"#cfc7ed";}
  function step(text){workEl.textContent=text;}
  function updateButton(){makeBtn.disabled=true;makeBtn.textContent="TẠO VIDEO • CHƯA CÓ ADAPTER SẢN XUẤT";scriptBtn.disabled=true;}
  async function request(path,timeout=6000,auth=true){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout),headers={};
    const token=tokenInput.value.trim();if(auth&&token)headers["X-CinemaNova-Token"]=token;
    try{const r=await fetch(LOCAL+path,{headers,cache:"no-store",mode:"cors",signal:controller.signal});const d=await r.json();if(!r.ok||d.ok===false)throw new Error(d.error||("HTTP "+r.status));return d;}
    catch(e){if(e.name==="TypeError"||e.name==="AbortError")throw new Error("Không truy cập được connector tại 127.0.0.1:8765. Hãy chạy START_CINEMA_NOVA.bat và cho phép Chrome truy cập mạng nội bộ nếu được hỏi.");throw e;}
    finally{clearTimeout(timer);}
  }
  async function check(){
    checkBtn.disabled=true;say("Đang kiểm tra cầu nối CINEMA NOVA...");
    try{
      if(location.hostname==="127.0.0.1"||location.hostname==="localhost"){
        const local=await request("/api/session",6000,false);tokenInput.value=local.token;sessionStorage.setItem(tokenKey,local.token);
      }
      if(!tokenInput.value.trim())throw new Error("Nhập mã ghép nối đang hiển thị trong cửa sổ connector.");
      sessionStorage.setItem(tokenKey,tokenInput.value.trim());
      const result=await request("/api/providers",8000);connected=true;
      const p=result.providers||{},fa=p.flow_agent?.available===true,fk=p.flowkit?.available===true;
      say("Connector đã xác thực. Flow Agent: "+(fa?"đang phản hồi":"chưa kết nối")+"; FlowKit: "+(fk?"đang phản hồi":"chưa kết nối")+". Tạo video chưa được bật.","ok");
      step("Đã kiểm tra thật Flow Agent /health và FlowKit /api/providers/status. Không có job tạo video nào được gửi.");
    }catch(e){connected=false;say("Chưa kết nối: "+e.message,"error");}
    finally{checkBtn.disabled=false;updateButton();}
  }
  tokenInput.addEventListener("change",()=>sessionStorage.setItem(tokenKey,tokenInput.value.trim()));
  checkBtn.addEventListener("click",check);updateButton();
  request("/api/health",6000,false).then(()=>say("Connector sẵn sàng. Bấm “Kiểm tra kết nối máy tính” để xác thực và đọc provider.","ok")).catch(()=>say("Chưa thấy connector cục bộ. Mở START_CINEMA_NOVA.bat trên Windows.","note"));
})();
