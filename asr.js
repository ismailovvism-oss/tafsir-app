// ============================================================
// ASR-МОДУЛЬ: голосовой поиск аята (фаза 1 распознавания речи).
// Whisper-модель Тартиля (tarteel-ai/whisper-base-ar-quran, ONNX q8)
// крутится ЦЕЛИКОМ в браузере через transformers.js; рантайм и модель
// лежат на R2 (класс "asr" в SOURCES, ~130 МБ разовой загрузки —
// дальше Cache Storage). Сервера нет: аудио никуда не уходит.
// Ленивый import() из index.html — как media.js (ASR_VER — кеш-бастер).
// ============================================================

let ctx=null;               // мост в index.html (resolveUrl, esc, goAyah…)
export function init(c){ctx=c;}

// ---------- модель ----------
const A={
  pipe:null,loading:null,   // пайплайн ASR и promise его загрузки
  pop:null,state:"idle",    // попап и его состояние: rec|busy|done|error
  stream:null,mr:null,chunks:[],t0:0,timer:null,vad:null,
  prog:{},progPct:0,        // прогресс загрузки модели по файлам (байты)
  transcript:"",results:[],err:"",
};

// Абсолютный URL: относительная база ломает dynamic import() (bare specifier)
function asrUrl(path){return new URL(ctx.resolveUrl("asr",{path}),location.href).href;}

async function ensurePipe(){
  if(A.pipe)return A.pipe;
  if(!A.loading)A.loading=(async()=>{
    const T=await import(asrUrl("transformers.min.js"));
    // База модели абсолютная (R2), поэтому канал «remote» с нашим хостом:
    // localModelPath с абсолютным URL v4 молча считает запрещённым remote
    // и отдаёт null-токенайзер/процессор.
    T.env.allowLocalModels=false;T.env.allowRemoteModels=true;
    T.env.remoteHost=asrUrl("models")+"/";
    T.env.remotePathTemplate="{model}/";
    T.env.backends.onnx.wasm.wasmPaths=asrUrl("");
    const progress=p=>{ // суммарный % по байтам всех скачиваемых файлов
      if(p&&p.file&&p.total){A.prog[p.file]=[p.loaded||0,p.total];
        let l=0,t=0;for(const f in A.prog){l+=A.prog[f][0];t+=A.prog[f][1];}
        A.progPct=t?Math.round(l*100/t):0;renderPop();}
    };
    const make=dev=>T.pipeline("automatic-speech-recognition","whisper-base-ar-quran",
      {dtype:"q8",device:dev,progress_callback:progress});
    // WebGPU берём, только если адаптер реально выдаётся (navigator.gpu бывает
    // и без работающего GPU — headless, старые драйверы); иначе честный WASM.
    let dev="wasm";
    try{if(navigator.gpu&&await navigator.gpu.requestAdapter())dev="webgpu";}catch(e){}
    let pipe;
    try{pipe=await make(dev);}
    catch(e){if(dev==="wasm")throw e;pipe=await make("wasm");} // webgpu не завёлся — откат
    ctx.ss("asrReady",1);                     // модель в кеше — конфирм больше не нужен
    A.pipe=pipe;return pipe;
  })().catch(e=>{A.loading=null;throw e;});
  return A.loading;
}

// ---------- индекс Корана для сопоставления ----------
// Транскрипт неточен (1–2 слова могут быть распознаны с ошибкой), поэтому не
// точный поиск, а скоринг: слово запроса = 1 балл, пара соседних слов = 2.
// Текст — монолит _arabic_clean через loadWhole (канал поиска, ~1 МБ, кешируется).
let QIDX=null,QTEXT=null;
function qWords(s){return ctx.normalizeArabic(s).split(/\s+/).filter(Boolean);}
async function ensureQIndex(){
  if(QIDX)return QIDX;
  const Q=await ctx.loadWhole("_arabic_clean");
  if(!Q)return null;
  QTEXT=Q;
  const uni=new Map(),bi=new Map();
  const add=(m,k,ref)=>{let s=m.get(k);if(!s)m.set(k,s=[]);s.push(ref);};
  for(const su in Q)for(const ay in Q[su]){
    const ref=su+":"+ay,ws=qWords(Q[su][ay]);
    const seen=new Set();
    for(let i=0;i<ws.length;i++){
      if(!seen.has(ws[i])){seen.add(ws[i]);add(uni,ws[i],ref);}
      if(i){const b=ws[i-1]+" "+ws[i];if(!seen.has(b)){seen.add(b);add(bi,b,ref);}}
    }
  }
  return QIDX={uni,bi};
}
export async function matchAyahs(text,limit){
  const idx=await ensureQIndex();if(!idx)return[];
  const ws=qWords(text).filter(w=>w.length>=2);
  if(!ws.length)return[];
  const score=new Map();
  const bump=(ref,w)=>score.set(ref,(score.get(ref)||0)+w);
  const su=new Set(),sb=new Set();
  for(const w of ws)if(!su.has(w)){su.add(w);const l=idx.uni.get(w);if(l)for(const r of l)bump(r,1);}
  for(let i=1;i<ws.length;i++){const b=ws[i-1]+" "+ws[i];
    if(!sb.has(b)){sb.add(b);const l=idx.bi.get(b);if(l)for(const r of l)bump(r,2);}}
  const max=su.size+2*sb.size;
  return[...score].map(([ref,sc])=>({ref,rel:sc/max}))
    .filter(x=>x.rel>=(ws.length>2?0.3:0.6))   // короткий запрос — строже
    .sort((a,b)=>b.rel-a.rel).slice(0,limit||8);
}

// ---------- аудио: blob записи → Float32 16 кГц моно ----------
async function blobToF32(blob){
  const buf=await blob.arrayBuffer();
  const AC=window.AudioContext||window.webkitAudioContext;
  const ac=new AC();
  const ab=await ac.decodeAudioData(buf);ac.close();
  const oc=new OfflineAudioContext(1,Math.ceil(ab.duration*16000),16000);
  const src=oc.createBufferSource();src.buffer=ab;src.connect(oc.destination);src.start();
  return (await oc.startRendering()).getChannelData(0);
}
export async function transcribeF32(f32){
  const pipe=await ensurePipe();
  const r=await pipe(f32);
  return (r&&r.text||"").trim();
}

// ---------- попап голосового поиска ----------
export async function openVoiceSearch(){
  closePop();
  const pop=document.createElement("div");
  pop.className="asr-pop";A.pop=pop;
  document.body.appendChild(pop);
  document.addEventListener("pointerdown",outsidePop,true);
  A.transcript="";A.results=[];A.err="";
  if(!A.pipe&&!ctx.gs("asrReady",0)){A.state="confirm";renderPop();return;} // первый раз — спросить про ~130 МБ
  beginListen();
}
function beginListen(){
  // модель и индекс Корана греются параллельно с записью
  ensurePipe().catch(e=>{A.err=loadErrMsg(e);A.state="error";stopRec(true);renderPop();});
  ensureQIndex().catch(()=>{});
  startRec();
}
function loadErrMsg(e){
  console.error("ASR:",e);
  return "Не удалось загрузить модель распознавания (нужна сеть при первом запуске). "+(e&&e.message||e);
}
function outsidePop(e){if(A.pop&&!A.pop.contains(e.target))closePop();}
export function closePop(){
  stopRec(true);
  if(A.pop){A.pop.remove();A.pop=null;}
  document.removeEventListener("pointerdown",outsidePop,true);
}

async function startRec(){
  if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){
    A.state="error";A.err="Микрофон недоступен: нужен HTTPS (или localhost).";renderPop();return;
  }
  try{A.stream=await navigator.mediaDevices.getUserMedia({audio:true});}
  catch(err){
    A.state="error";
    A.err=err&&err.name==="NotAllowedError"
      ?"Доступ к микрофону запрещён. Разрешите его в настройках браузера."
      :"Не удалось открыть микрофон: "+(err&&err.name||err);
    renderPop();return;
  }
  A.chunks=[];
  A.mr=new MediaRecorder(A.stream);
  A.mr.ondataavailable=ev=>{if(ev.data&&ev.data.size)A.chunks.push(ev.data);};
  A.mr.onstop=onRecStop;
  A.mr.start();A.t0=Date.now();A.state="rec";
  startVad();
  A.timer=setInterval(()=>{
    if(Date.now()-A.t0>25000)stopRec();  // потолок 25 с (окно Whisper — 30)
    else renderPop();
  },500);
  renderPop();
}
// Мини-VAD: следим за уровнем; если после начала речи ~1.5 с тишины — стоп сами.
function startVad(){
  const AC=window.AudioContext||window.webkitAudioContext;
  const ac=new AC(),an=ac.createAnalyser();an.fftSize=512;
  ac.createMediaStreamSource(A.stream).connect(an);
  const buf=new Uint8Array(an.fftSize);
  let speechMs=0,silenceMs=0,last=Date.now();
  const iv=setInterval(()=>{
    an.getByteTimeDomainData(buf);
    let dev=0;for(let i=0;i<buf.length;i++)dev=Math.max(dev,Math.abs(buf[i]-128));
    const now=Date.now(),dt=now-last;last=now;
    if(dev>10){speechMs+=dt;silenceMs=0;}else silenceMs+=dt;
    if(speechMs>700&&silenceMs>1500)stopRec();
  },150);
  A.vad={ac,iv};
}
function stopVad(){if(A.vad){clearInterval(A.vad.iv);try{A.vad.ac.close();}catch(e){}A.vad=null;}}
function stopRec(cancel){
  clearInterval(A.timer);A.timer=null;stopVad();
  if(cancel)A.chunks=[];
  if(A.mr&&A.mr.state!=="inactive"){if(cancel)A.mr.onstop=null;try{A.mr.stop();}catch(e){}}
  else if(A.stream){A.stream.getTracks().forEach(t=>t.stop());A.stream=null;}
  A.mr=cancel?null:A.mr;
}
async function onRecStop(){
  const blob=new Blob(A.chunks,{type:A.mr&&A.mr.mimeType||"audio/webm"});
  if(A.stream){A.stream.getTracks().forEach(t=>t.stop());A.stream=null;}
  A.mr=null;
  if(!A.pop)return;                          // попап закрыли — молча выходим
  if(!blob.size){A.state="error";A.err="Пустая запись.";renderPop();return;}
  A.state="busy";renderPop();
  try{
    const f32=await blobToF32(blob);
    A.transcript=await transcribeF32(f32);
    A.results=A.transcript?await matchAyahs(A.transcript):[];
    A.state="done";
  }catch(e){A.state="error";A.err=loadErrMsg(e);}
  renderPop();
}

function surahRu(s){const su=ctx.SURAHS[s-1];return su?su.ru:s;}
function renderPop(){
  if(!A.pop)return;
  const st=A.state,secs=st==="rec"?Math.round((Date.now()-A.t0)/1000):0;
  const modelReady=!!A.pipe;
  let body="";
  if(st==="confirm"){
    body=`<div class="ap-note">Распознавание работает прямо на устройстве: один раз скачается
      модель (~130 МБ, Whisper Тартиля), дальше — из кеша, офлайн. Записи никуда не отправляются.</div>
      <div class="ap-row"><button data-act="go" class="hot">Загрузить и начать</button></div>`;
  }else if(st==="rec"){
    body=`<div class="ap-listen"><span class="ap-dot"></span> Слушаю… читайте аят <b>${secs} с</b></div>
      <div class="ap-row"><button data-act="stop" class="hot">⏹ Готово</button></div>
      <div class="ap-note">${modelReady?"Модель готова. ":"Модель загружается: "+A.progPct+"%. "}Пауза в 1,5 с завершит запись сама. Звук никуда не отправляется — распознавание на устройстве.</div>`;
  }else if(st==="busy"){
    body=`<div class="ap-listen">🕐 Распознаю…${A.pipe?"":" (жду модель: "+A.progPct+"%)"}</div>
      <div class="ap-note">Первый запуск дольше: модель (~130 МБ) кешируется, дальше — быстро.</div>`;
  }else if(st==="done"){
    const Q=QTEXT||{};
    const items=A.results.map(r=>{
      const[s,a]=r.ref.split(":").map(Number);
      const t=(Q[s]&&Q[s][a])||"";
      return `<div class="ap-res" data-go="${s}:${a}">
        <div class="ap-ar" dir="rtl">${ctx.esc(t)}</div>
        <div class="ap-ref">${ctx.esc(surahRu(s))} · ${s}:${a} · ${Math.round(r.rel*100)}%</div></div>`;
    }).join("");
    body=`<div class="ap-tr" dir="rtl">${ctx.esc(A.transcript)||"—"}</div>`+
      (items||`<div class="ap-note">Не нашёл похожий аят. Попробуйте прочитать подряд 3–5 слов одного аята.</div>`)+
      `<div class="ap-row"><button data-act="again" class="hot">🎤 Ещё раз</button></div>`;
  }else if(st==="error"){
    body=`<div class="ap-note">⚠ ${ctx.esc(A.err)}</div>
      <div class="ap-row"><button data-act="again" class="hot">Повторить</button></div>`;
  }
  A.pop.innerHTML=`<div class="ap-title"><span>🎤 Голосовой поиск аята</span>
    <button class="ap-x" data-act="close" title="Закрыть">✕</button></div>`+body;
  A.pop.onclick=onPopClick;
}
function onPopClick(e){
  const g=e.target.closest("[data-go]");
  if(g){const[s,a]=g.dataset.go.split(":").map(Number);closePop();ctx.goAyah(s,a);return;}
  const b=e.target.closest("[data-act]");if(!b)return;
  switch(b.dataset.act){
    case"close":closePop();break;
    case"go":beginListen();break;
    case"stop":stopRec();break;
    case"again":A.transcript="";A.results=[];A.err="";startRec();break;
  }
}
