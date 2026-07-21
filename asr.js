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
    // Ручной оверрайд: localStorage tl_asrDevice = "wasm" | "webgpu".
    let dev=ctx.gs("asrDevice","");
    if(dev!=="wasm"&&dev!=="webgpu"){
      dev="wasm";
      try{if(navigator.gpu&&await navigator.gpu.requestAdapter())dev="webgpu";}catch(e){}
    }
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

// ============================================================
// ЖИВОЕ ЧТЕНИЕ (фазы 2–3): follow-along и «по памяти».
// Слой поверх режима 📖 Аяты: микрофон слушает непрерывно, VAD режет речь на
// фразы, каждая фраза распознаётся и ВЫРАВНИВАЕТСЯ с текстом текущей суры —
// подсветка (.asr-cur) бежит за чтением. «По памяти» (hidden): аяты размыты
// (body.asr-hidemode + .asr-open на открытых), аят проявляется, когда прочитан;
// 💡 подсказка / ⏭ не помню; итог аята уходит в SRS хифза (hifzRecordReview:
// 2 — сам, 1 — с подсказкой, 0 — не вспомнил).
// ============================================================
const L={on:false,hidden:false,hifz:false,s:0,cur:1,lastA:1,ptr:0,W:[],aStart:{},aEnd:{},
  peeked:{},grades:{},stream:null,ac:null,proc:null,buf:[],speechMs:0,silMs:0,segQ:[],busy:false,
  pill:null,mo:null,lastTr:"",stat:""};

export async function startLive(opts){
  if(L.on)stopLive();
  closePop();
  const ST=ctx.ST;
  if(ST.pageMode||ST.hifzMode||ST.homeMode){alert("Живое чтение работает в режиме 📖 Аяты: откройте суру.");return;}
  if(!ctx.gs("asrReady",0)&&!A.pipe){
    if(!confirm("Распознавание речи работает на устройстве: один раз скачается модель (~130 МБ, лучше по Wi-Fi), дальше — офлайн. Загрузить?"))return;
  }
  L.hidden=!!(opts&&opts.hidden);L.hifz=L.hidden;   // «по памяти» = проверка → SRS
  L.s=ST.surah;L.cur=(opts&&opts.ayah)||ctx.curTopAyah()||1;
  L.peeked={};L.grades={};L.lastTr="";L.stat="";
  // индекс слов суры: плоский список + границы аятов
  const Q=await ctx.loadWhole("_arabic_clean").catch(()=>null);
  const su=Q&&Q[String(L.s)];
  if(!su){alert("Не удалось загрузить текст суры.");return;}
  L.W=[];L.aStart={};L.aEnd={};
  const aids=Object.keys(su).map(Number).sort((a,b)=>a-b);
  L.lastA=aids[aids.length-1];
  for(const a of aids){
    L.aStart[a]=L.W.length;
    for(const w of qWords(su[a]))L.W.push({a,w});
    L.aEnd[a]=L.W.length;                       // exclusive
  }
  if(L.aStart[L.cur]==null)L.cur=aids.find(a=>a>=L.cur)||aids[0];
  L.start0=L.cur;                               // всё до этого аята не прячем
  L.ptr=L.aStart[L.cur];
  // модель — параллельно с первым чтением
  ensurePipe().then(()=>{L.stat="";updatePill();}).catch(e=>{alert(loadErrMsg(e));stopLive();});
  if(!A.pipe)L.stat="модель…";
  // микрофон: непрерывный захват сразу в 16 кГц (AudioContext ресемплирует сам)
  try{L.stream=await navigator.mediaDevices.getUserMedia({audio:true});}
  catch(err){alert("Не удалось открыть микрофон: "+(err&&err.name||err));return;}
  const AC=window.AudioContext||window.webkitAudioContext;
  L.ac=new AC();                 // нативная частота: 16-кГц контекст с микрофоном
  const src=L.ac.createMediaStreamSource(L.stream);   // капризен; ресемплим сами (to16k)
  L.buf=[];L.speechMs=0;L.silMs=0;L.segQ=[];L.busy=false;
  // Захват — AudioWorklet (аудиопоток): главный поток занят WASM-инференсом
  // секундами, ScriptProcessor в это время ТЕРЯЕТ звук (колбэки не successors);
  // worklet копит и шлёт пачками, сообщения доезжают, когда главный поток освободится.
  if(L.ac.audioWorklet){
    const code=`class C extends AudioWorkletProcessor{
      constructor(){super();this.b=[];this.n=0;}
      process(i){const c=i[0]&&i[0][0];
        if(c){this.b.push(new Float32Array(c));this.n+=c.length;
          if(this.n>=2048){const f=new Float32Array(this.n);let o=0;
            for(const x of this.b){f.set(x,o);o+=x.length;}
            this.port.postMessage(f,[f.buffer]);this.b=[];this.n=0;}}
        return true;}}
      registerProcessor("asr-cap",C);`;
    await L.ac.audioWorklet.addModule(URL.createObjectURL(new Blob([code],{type:"text/javascript"})));
    L.proc=new AudioWorkletNode(L.ac,"asr-cap",{numberOfOutputs:0});
    src.connect(L.proc);
    L.proc.port.onmessage=e=>onAudioChunk(e.data);
  }else{ // фолбэк: старые браузеры
    L.proc=L.ac.createScriptProcessor(4096,1,1);
    src.connect(L.proc);L.proc.connect(L.ac.destination);
    L.proc.onaudioprocess=e=>onAudioChunk(new Float32Array(e.inputBuffer.getChannelData(0)));
  }
  L.on=true;
  document.body.classList.add("asr-live");
  if(L.hidden)document.body.classList.add("asr-hidemode");
  // после ре-рендеров ленты классы слетают — возвращаем наблюдателем
  L.mo=new MutationObserver(()=>applyClasses());
  const cb=document.getElementById("centerBody");
  if(cb)L.mo.observe(cb,{childList:true,subtree:true});
  makePill();applyClasses();scrollCur();
}
export function stopLive(summary){
  if(!L.on)return;
  L.on=false;
  try{if(L.proc)L.proc.disconnect();}catch(e){}
  try{if(L.ac)L.ac.close();}catch(e){}
  if(L.stream){L.stream.getTracks().forEach(t=>t.stop());L.stream=null;}
  L.proc=null;L.ac=null;L.mo&&L.mo.disconnect();L.mo=null;
  document.body.classList.remove("asr-hidemode","asr-live");
  document.querySelectorAll(".asr-cur").forEach(e=>e.classList.remove("asr-cur"));
  document.querySelectorAll(".asr-open").forEach(e=>e.classList.remove("asr-open"));
  if(L.pill){L.pill.remove();L.pill=null;}
  if(summary&&L.hidden){
    const g=Object.values(L.grades),n=g.length;
    if(n)alert(`Проверка чтением: аятов ${n} · сам ${g.filter(x=>x===2).length} · с подсказкой ${g.filter(x=>x===1).length} · не вспомнил ${g.filter(x=>x===0).length}${L.hifz?"\nРезультат записан в хифз (SRS).":""}`);
  }
}
export function liveOn(){return L.on;}

// --- захват + VAD ---
// Скользящее окно: копим НЕПРЕРЫВНЫЙ хвост звука (до ~14 с). Пауза ≥0.8 с после
// ≥0.6 с речи (или речь дольше 8 с) → окно уходит на распознавание ЦЕЛИКОМ —
// фраза попадает в Whisper с контекстом предыдущей, а не рваным огрызком.
// После распознавания хвост подрезается до ~2.5 с (контекст следующей фразы);
// повторное узнавание старых слов гасится монотонностью указателя в advance().
function onAudioChunk(d){
  const sr=L.ac?L.ac.sampleRate:16000;
  L.buf.push(d);
  let n=L.buf.reduce((s,c)=>s+c.length,0);
  while(n>sr*12&&L.buf.length>1){n-=L.buf[0].length;L.buf.shift();}
  let sum=0;for(let i=0;i<d.length;i+=4)sum+=d[i]*d[i];
  const rms=Math.sqrt(sum/(d.length/4));
  const ms=d.length/sr*1000;
  if(rms>0.015){L.speechMs+=ms;L.silMs=0;}else L.silMs+=ms;
  if((L.speechMs>=600&&L.silMs>=800)||L.speechMs>=8000)takeSegment();
}
function takeSegment(){
  const sr=L.ac?L.ac.sampleRate:16000;
  const total=L.buf.reduce((n,c)=>n+c.length,0);
  let f32=new Float32Array(total);
  let o=0;for(const c of L.buf){f32.set(c,o);o+=c.length;}
  if(total>sr*10)f32=f32.subarray(total-sr*10);  // потолок окна: WASM-инференс на слабом CPU
  // хвост-контекст ~2.5 с остаётся в буфере
  let keep=0,i=L.buf.length-1;
  for(;i>=0&&keep<sr*2.5;i--)keep+=L.buf[i].length;
  L.buf=L.buf.slice(i+1);
  L.speechMs=0;L.silMs=0;
  if(window._asrDbg)window._asrDbg("seg "+(f32.length/sr).toFixed(1)+"s");
  L.segQ.push(f32);pumpQ();
}
// AudioContext не дал 16 кГц (старый Safari) → ресемплируем сегмент сами
async function to16k(f32){
  const sr=L.ac?L.ac.sampleRate:16000;
  if(sr===16000)return f32;
  const oc=new OfflineAudioContext(1,Math.ceil(f32.length/sr*16000),16000);
  const b=oc.createBuffer(1,f32.length,sr);b.copyToChannel(f32,0);
  const s=oc.createBufferSource();s.buffer=b;s.connect(oc.destination);s.start();
  return (await oc.startRendering()).getChannelData(0);
}
async function pumpQ(){
  if(L.busy||!L.segQ.length)return;
  L.busy=true;L.stat=A.pipe?"распознаю…":"модель…";updatePill();
  try{
    // накопившиеся сегменты склеиваем: распознаём один раз, без отставания
    let segs=L.segQ;L.segQ=[];
    const total=segs.reduce((n,c)=>n+c.length,0);
    let f32;
    if(segs.length===1)f32=segs[0];
    else{f32=new Float32Array(total);let o=0;for(const c of segs){f32.set(c,o);o+=c.length;}}
    const sr=L.ac?L.ac.sampleRate:16000;
    if(f32.length>sr*10)f32=f32.subarray(f32.length-sr*10);   // потолок и после склейки
    const text=await transcribeF32(await to16k(f32));
    if(L.on&&text){L.lastTr=text;advance(text);}
  }catch(e){console.error("ASR live:",e);}
  L.busy=false;L.stat="";
  if(L.on){updatePill();if(L.segQ.length)pumpQ();}
}

// --- выравнивание фразы с текстом суры ---
// Транскрипт неточен (клееные приставки «بالعالمين», обрезки), поэтому слова
// сравниваем нечётко (равенство ИЛИ вхождение при длине ≥3), окно начинается
// ЧУТЬ ПОЗАДИ указателя (в скользящем аудио-окне есть уже прочитанное), а
// продвижение — только вперёд (монотонно).
function wEq(a,b){return a===b||(a.length>=3&&b.length>=3&&(a.includes(b)||b.includes(a)));}
// Жадная примерка фразы T (с якорного слова ai) к тексту с позиции s0:
// сколько слов легло и докуда дошли. Пропуски терпим (просмотр вперёд ≤8).
function alignFrom(T,ai,s0,end){
  let cur=s0+1,m=1,last=s0;
  for(let k=ai+1;k<T.length;k++){
    for(let j=cur;j<Math.min(cur+8,end);j++){
      if(wEq(L.W[j].w,T[k])){m++;cur=j+1;last=j;break;}
    }
  }
  return {m,last};
}
function advance(text){
  const T=qWords(text).filter(w=>w.length>=2);
  if(!T.length)return;
  const start=Math.max(0,L.ptr-25);             // чуть назад: в окне есть уже прочитанное
  const end=Math.min(L.W.length,L.ptr+80);      // и вперёд: ~2-3 аята
  // Якорь — первое (или 2-е/3-е, если первое — мусор) слово фразы; пробуем ВСЕ
  // его вхождения в окне. Годятся только примерки, продвигающие указатель
  // ВПЕРЁД; из равных берём БЛИЖАЙШУЮ к указателю — иначе в сурах с рефреном
  // (ар-Рахман: одинаковые аяты) прыгали бы через повторы.
  let best=null;
  for(let ai=0;ai<Math.min(3,T.length);ai++){
    for(let s0=start;s0<end;s0++){
      if(!wEq(L.W[s0].w,T[ai]))continue;
      const r=alignFrom(T,ai,s0,end);
      if(r.last+1<=L.ptr)continue;              // назад/на месте — не кандидат
      if(!best||r.m>best.m||(r.m===best.m&&r.last<best.last))best=r;
    }
    if(best&&best.m>=T.length-ai)break;         // легла вся — хватит
  }
  if(!best||best.m<2||best.m<T.length*0.4)return; // фраза не отсюда (шум/повтор)
  L.ptr=best.last+1;
  // все аяты, чьи слова пройдены, — завершены; текущий — где стоит указатель
  while(L.cur<=L.lastA&&L.aEnd[L.cur]!=null&&L.ptr>=L.aEnd[L.cur])finishAyah(L.cur);
  applyClasses();scrollCur();updatePill();
}
function finishAyah(a){
  if(L.grades[a]==null){
    const g=L.peeked[a]?1:2;
    L.grades[a]=g;
    if(L.hifz)try{ctx.hifzReview(L.s+":"+a,g);}catch(e){console.error(e);}
  }
  const el=blockOf(a);if(el)el.classList.add("asr-open");
  L.cur=a+1;
  if(L.cur>L.lastA){stopLive(true);}
}
function peekCur(){                              // 💡 подсказка: открыть текущий аят
  L.peeked[L.cur]=1;
  const el=blockOf(L.cur);if(el)el.classList.add("asr-open");
  updatePill();
}
function skipCur(){                              // ⏭ не вспомнил: 0 и дальше
  const a=L.cur;
  L.grades[a]=0;
  if(L.hifz)try{ctx.hifzReview(L.s+":"+a,0);}catch(e){console.error(e);}
  const el=blockOf(a);if(el)el.classList.add("asr-open");
  L.cur=a+1;
  if(L.cur>L.lastA){stopLive(true);return;}
  L.ptr=L.aStart[L.cur];
  applyClasses();scrollCur();updatePill();
}

// --- DOM: подсветка/скрытие/пилюля ---
function blockOf(a){return document.querySelector(`.ayah-block[data-aid="${a}"]`);}
function applyClasses(){
  if(!L.on)return;
  document.querySelectorAll(".asr-cur").forEach(e=>e.classList.remove("asr-cur"));
  const cur=blockOf(L.cur);if(cur)cur.classList.add("asr-cur");
  if(L.hidden){
    document.querySelectorAll(".ayah-block[data-aid]").forEach(el=>{
      const a=+el.dataset.aid;
      // открыто: всё ДО старта сессии, завершённые/пропущенные и подсказанные
      if(a<L.start0||L.grades[a]!=null||L.peeked[a])el.classList.add("asr-open");
      else el.classList.remove("asr-open");
    });
  }
}
function scrollCur(){
  const el=blockOf(L.cur);
  if(el)el.scrollIntoView({behavior:"smooth",block:"center"});
}
function makePill(){
  const p=document.createElement("div");
  p.id="asrPill";
  document.body.appendChild(p);L.pill=p;
  p.onclick=e=>{
    const b=e.target.closest("[data-act]");if(!b)return;
    if(b.dataset.act==="stop")stopLive(true);
    else if(b.dataset.act==="peek")peekCur();
    else if(b.dataset.act==="skip")skipCur();
  };
  updatePill();
}
function updatePill(){
  if(!L.pill)return;
  const tr=L.lastTr?`<span class="asp-tr" dir="rtl">${ctx.esc(L.lastTr.split(" ").slice(-5).join(" "))}</span>`:"";
  L.pill.innerHTML=
    `<span class="asp-dot"></span><b>${L.s}:${L.cur}</b>`+
    (L.stat?`<span class="asp-st">${ctx.esc(L.stat)}</span>`:tr)+
    (L.hidden?`<button data-act="peek" title="Подсказка: показать аят">💡</button>
               <button data-act="skip" title="Не вспомнил — открыть и дальше">⏭</button>`:"")+
    `<button data-act="stop" title="Остановить">⏹</button>`;
}
