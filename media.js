// ============================================================
// МЕДИА-МОДУЛЬ «Библиотеки тафсиров» — фазы 1–2: аудио-плеер + записи пользователя
// ============================================================
// ES-модуль. Грузится ЛЕНИВО из index.html (mediaMod() → import("./media.js")):
// пока пользователь не тронул аудио — ни байта этого кода, ни <audio>-элементов.
//
// Архитектура (развязка слоёв вокруг оси аята):
//   • ОСЬ АЯТА: указатель POS {sura, ayah} — единственный источник истины.
//     Смена аята эмитит событие; подписчики — текстовый слой (подсветка/скролл,
//     followText) и, в следующих фазах, визуальный слой и караоке-подсветка
//     (внешний хук — export onAyahChange).
//   • ИСТОЧНИК: единый интерфейс async getMediaFor(s,a) → {url}|{blob}|null.
//     Реализованы: audio_cdn «файл-на-аят» (EveryAyah) и audio_user_recording
//     (наборы записей пользователя, blob в IndexedDB). Сплошной файл с
//     таблицей таймингов (QUL) встанет за тот же интерфейс.
//   • Смена источника (чтец ↔ набор записей) не трогает указатель аята —
//     текст и (в будущем) визуальный слой не сбиваются.
//   • ЗАПИСИ: модель «одна запись = один аят»; blob как отдал MediaRecorder
//     (webm/opus в Chrome, mp4/aac в Safari) + его MIME. Хранение ТОЛЬКО в
//     IndexedDB (не localStorage, не SW-кэш); метаданные наборов (id+имя) —
//     tl_mediaSets в localStorage приложения (вне облачного синка).
//
// UI: панель-плеер НЕ плавает над текстом — вставляется обычным рядом
// flex-колонки main.center над нижней навигацией; сворачивается в узкую
// полоску (состояние запоминается, tl_mediaMin).
//
// Связь с приложением — ТОЛЬКО через ctx из index.html: let-глобалы (ST,
// CONFIG, qpcMeta) — геттеры, функции (resolveUrl, jumpTo, gs/ss, esc,
// renderRP, renderCenter) — как есть.

let ctx=null;

// ---------- ось аята: указатель + событие смены ----------
const POS={sura:0,ayah:0};
const ayahSubs=[]; // (sura,ayah)=>… ; сюда же встанут визуальный слой и караоке
export function onAyahChange(cb){ayahSubs.push(cb);}
function setPos(s,a){
  if(POS.sura===s&&POS.ayah===a)return;
  POS.sura=s;POS.ayah=a;
  for(const cb of ayahSubs){try{cb(s,a);}catch(e){console.error("media: подписчик оси аята:",e);}}
}
const key=(s,a)=>s*1000+a;            // порядок аятов для сравнения диапазонов
const sa=(s,a)=>s+":"+a;              // строковый адрес аята (как всюду в приложении)
function ayahCount(s){const su=ctx.SURAHS.find(x=>x.id===s);return su?su.n:0;}
function nextAyah(s,a){
  if(a<ayahCount(s))return{sura:s,ayah:a+1};
  return s<114?{sura:s+1,ayah:1}:null;
}
function prevAyah(s,a){
  if(a>1)return{sura:s,ayah:a-1};
  return s>1?{sura:s-1,ayah:ayahCount(s-1)}:null;
}

// ---------- IndexedDB: записи пользователя (blob) ----------
// store recordings: ключ [set, "s:a"] → {set, ayah:"s:a", blob, mime, size, ts}
let _db=null;
function idb(){
  if(_db)return Promise.resolve(_db);
  return new Promise((res,rej)=>{
    const rq=indexedDB.open("tafsirMedia",1);
    rq.onupgradeneeded=()=>{rq.result.createObjectStore("recordings",{keyPath:["set","ayah"]});};
    rq.onsuccess=()=>{_db=rq.result;res(_db);};
    rq.onerror=()=>rej(rq.error);
  });
}
function idbReq(r){return new Promise((res,rej)=>{r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);});}
async function idbPut(rec){const db=await idb();return idbReq(db.transaction("recordings","readwrite").objectStore("recordings").put(rec));}
async function idbGet(set,ayah){const db=await idb();return idbReq(db.transaction("recordings").objectStore("recordings").get([set,ayah]));}
async function idbDel(set,ayah){const db=await idb();return idbReq(db.transaction("recordings","readwrite").objectStore("recordings").delete([set,ayah]));}
function setRange(set){return IDBKeyRange.bound([set,""],[set,"￿"]);}
async function idbKeys(set){const db=await idb();return idbReq(db.transaction("recordings").objectStore("recordings").getAllKeys(setRange(set)));}
async function idbClearSet(set){const db=await idb();return idbReq(db.transaction("recordings","readwrite").objectStore("recordings").delete(setRange(set)));}

// Кэш «в каких аятах есть запись» для набора наборов (индикаторы 🎙 и скип-логика)
const RECKEYS={}; // setId -> Set("s:a")
async function loadRecKeys(setId){
  if(RECKEYS[setId])return RECKEYS[setId];
  const ks=await idbKeys(setId).catch(()=>[]);
  return RECKEYS[setId]=new Set(ks.map(k=>k[1]));
}
function recSets(){return ctx.gs("mediaSets",[]);}
// Активный набор ДЛЯ ЗАПИСИ (куда пишет 🎙); играть можно любой (rec:<id>)
function recSetId(){
  const sets=recSets();if(!sets.length)return null;
  const id=ctx.gs("mediaRecSet",sets[0].id);
  return sets.some(s=>s.id===id)?id:sets[0].id;
}
// Индикатор для рендера аятов в index.html (синхронный — по кэшу ключей)
export function hasRec(s,a){
  const id=recSetId();
  return !!(id&&RECKEYS[id]&&RECKEYS[id].has(sa(s,a)));
}

// ---------- аудио-источники ----------
function reciters(){return(ctx.CONFIG.audio&&ctx.CONFIG.audio.reciters)||[];}
function activeSourceId(){
  const rs=reciters();
  return ctx.gs("mediaReciter",(ctx.CONFIG.audio&&ctx.CONFIG.audio.default)||(rs[0]&&rs[0].id)||"");
}
function makeCdnSource(rec){
  return{
    id:rec.id,name:rec.name,type:rec.type||"audio_cdn",
    // «файл-на-аят»: сегмент = весь файл, таймингов нет
    async getMediaFor(s,a){
      const file=String(s).padStart(3,"0")+String(a).padStart(3,"0")+".mp3";
      return{url:ctx.resolveUrl("audio_cdn",{subdir:rec.subdir,file})};
    },
    async has(){return true;} // CDN считаем полным (ошибку скажет сам плеер)
  };
}
function makeRecSource(set){
  return{
    id:"rec:"+set.id,name:set.name,type:"audio_user_recording",
    async getMediaFor(s,a){
      const r=await idbGet(set.id,sa(s,a)).catch(()=>null);
      return r?{blob:r.blob}:null;
    },
    async has(s,a){const ks=await loadRecKeys(set.id);return ks.has(sa(s,a));}
  };
}
function makeSourceById(id){
  if(id&&id.startsWith("rec:")){
    const set=recSets().find(x=>x.id===id.slice(4));
    return set?makeRecSource(set):null;
  }
  const rec=reciters().find(r=>r.id===id)||reciters()[0];
  return rec?makeCdnSource(rec):null;
}
let SRC=null;

// ---------- плеер ----------
const P={
  audio:null,pre:null,      // основной <audio> и префетчер следующего аята
  playing:false,
  active:false,             // панель показана (плеер «включён»)
  min:false,                // панель свёрнута в полоску
  rate:1,
  repeat:0,                 // повтор аята: 0=выкл, 2/3=N раз, Infinity=∞
  played:0,                 // сколько раз доигран текущий аят (для repeat)
  range:null,               // повтор диапазона {a:{sura,ayah}, b:{sura,ayah}}
  rangeArm:null,            // первый тап A–B: помечено начало, ждём конец
  err:"",
  objUrl:null,              // текущий object URL записи (revoke при смене)
  token:0,                  // защита от гонок async-загрузки (быстрые ⏮/⏭)
};
function ensureAudio(){
  if(P.audio)return P.audio;
  const au=new Audio();
  au.preload="auto";
  au.addEventListener("ended",onEnded);
  au.addEventListener("error",()=>{
    if(!P.active||!au.getAttribute("src"))return; // намеренная остановка — не ошибка
    P.playing=false;P.err="аудио недоступно (сеть/CDN)";renderBar();
  });
  P.audio=au;
  return au;
}
function setSrc(au,m){
  if(P.objUrl){URL.revokeObjectURL(P.objUrl);P.objUrl=null;}
  au.src=m.blob?(P.objUrl=URL.createObjectURL(m.blob)):m.url;
}
async function playCur(){
  const t=++P.token;
  const m=await SRC.getMediaFor(POS.sura,POS.ayah).catch(()=>null);
  if(t!==P.token)return;                   // пока грузили — ушли на другой аят
  if(!m){
    if(SRC.type==="audio_user_recording"){ // на этом аяте записи нет → к ближайшей
      const nx=await nextPlayable(POS.sura,POS.ayah);
      if(t!==P.token)return;
      if(nx){setPos(nx.sura,nx.ayah);playCur();return;}
    }
    P.playing=false;
    P.err=SRC.type==="audio_user_recording"?"в наборе нет записей":"аудио недоступно";
    renderBar();return;
  }
  const au=ensureAudio();
  P.err="";
  setSrc(au,m);
  au.defaultPlaybackRate=P.rate;au.playbackRate=P.rate;
  const pr=au.play();
  if(pr)pr.catch(err=>{
    if(t!==P.token)return;
    P.playing=false;
    // NotAllowedError — iOS/автоплей без жеста (ждём явного ▶); прочее — сеть/CDN
    P.err=err&&err.name==="NotAllowedError"?"нажмите ▶ (автовоспроизведение заблокировано)":"аудио недоступно (сеть/CDN)";
    renderBar();
  });
  P.playing=true;renderBar();
  prefetchNext();
}
// Следующий аят с учётом диапазона A–B; для наборов записей — скип пустых
// аятов (иначе набор с пропусками останавливался бы на каждом «дыре»)
async function nextPlayable(s,a){
  let nx=nextAyah(s,a);
  if(P.range&&(!nx||key(nx.sura,nx.ayah)>key(P.range.b.sura,P.range.b.ayah)))
    nx={sura:P.range.a.sura,ayah:P.range.a.ayah};    // конец диапазона → к началу
  if(!nx||SRC.type!=="audio_user_recording")return nx;
  // скип: ищем ближайший записанный (в пределах диапазона, не дальше конца Корана)
  let guard=6236;
  while(nx&&guard--){
    if(await SRC.has(nx.sura,nx.ayah))return nx;
    let n2=nextAyah(nx.sura,nx.ayah);
    if(P.range&&(!n2||key(n2.sura,n2.ayah)>key(P.range.b.sura,P.range.b.ayah))){
      // в диапазоне записей нет вообще — не зацикливаемся
      if(key(nx.sura,nx.ayah)===key(P.range.a.sura,P.range.a.ayah))return null;
      n2={sura:P.range.a.sura,ayah:P.range.a.ayah};
    }
    nx=n2;
  }
  return null;
}
async function onEnded(){
  P.played++;
  if(P.repeat&&P.played<P.repeat){P.audio.currentTime=0;P.audio.play();return;}
  P.played=0;
  const nx=await nextPlayable(POS.sura,POS.ayah);
  if(!nx){P.playing=false;renderBar();return;}       // конец Корана / пустой набор
  setPos(nx.sura,nx.ayah);
  playCur();
}
async function prefetchNext(){
  const nx=nextAyah(POS.sura,POS.ayah);
  if(!nx||SRC.type==="audio_user_recording")return;  // записи локальны — префетч не нужен
  const m=await SRC.getMediaFor(nx.sura,nx.ayah).catch(()=>null);
  if(!m||!m.url)return;
  if(!P.pre){P.pre=new Audio();P.pre.preload="auto";P.pre.muted=true;}
  P.pre.src=m.url;
}
function togglePlay(){
  const au=ensureAudio();
  if(P.playing){au.pause();P.playing=false;renderBar();return;}
  if(au.getAttribute("src")&&!au.ended){ // пауза → продолжить с места
    au.play().catch(()=>{});P.playing=true;renderBar();
  }else playCur();                       // остановились на конце — заново текущий аят
}
function navStep(dir){
  const t=dir>0?nextAyah(POS.sura,POS.ayah):prevAyah(POS.sura,POS.ayah);
  if(!t)return;
  P.played=0;setPos(t.sura,t.ayah);playCur();
}
function stopAll(){
  closeMenu();
  P.playing=false;P.active=false;P.range=null;P.rangeArm=null;P.played=0;P.err="";P.token++;
  if(P.audio){P.audio.pause();P.audio.removeAttribute("src");P.audio.load();}
  if(P.pre)P.pre.removeAttribute("src");
  if(P.objUrl){URL.revokeObjectURL(P.objUrl);P.objUrl=null;}
  const el=document.getElementById("mediaPill");if(el)el.remove();
  document.querySelectorAll(".media-cur").forEach(e=>e.classList.remove("media-cur"));
}

// ---------- следование текста за указателем ----------
// Подсветка/автоскролл текущего аята; смена суры или страницы мусхафа — через
// jumpTo приложения. Внутри суры НЕ ре-рендерим (только скролл) — дёшево.
function followText(s,a){
  document.querySelectorAll(".media-cur").forEach(e=>e.classList.remove("media-cur"));
  const ST=ctx.ST;
  if(ST.homeMode||ST.hifzMode||ST.bmView)return;   // спец-экраны не дёргаем
  if(ST.pageMode){
    const pg=pageOfAyah(s,a);
    if(pg&&pg!==ST.mushafPage)ctx.jumpTo({page:pg});
    return;                                        // в мусхафе поаятной подсветки нет
  }
  if(ST.surah!==s)ctx.jumpTo({surah:s,ayah:a});    // перешли суру — обычный переход
  markCur(a);
}
function markCur(a){
  const el=document.querySelector(`.ayah-block[data-aid="${a}"],.wbw-ayah[data-aid="${a}"]`);
  if(el){el.classList.add("media-cur");el.scrollIntoView({behavior:"smooth",block:"center"});}
}
// Страница мусхафа, содержащая аят (по qpcMeta.pageStart; линейно по 604 — дёшево)
function pageOfAyah(s,a){
  const meta=ctx.qpcMeta;
  if(!meta||!meta.pageStart)return null;
  const total=meta.pages||604,k=key(s,a);
  let pg=null;
  for(let p=1;p<=total;p++){
    const st=meta.pageStart[p];if(!st)continue;
    if(key(st.surah,st.ayah)<=k)pg=p;else break;
  }
  return pg;
}

// ---------- панель плеера (встроена над нижней навигацией, не плавает) ----------
function barEl(){
  let el=document.getElementById("mediaPill");
  if(!el){
    el=document.createElement("div");
    el.id="mediaPill";el.className="media-bar";
    el.addEventListener("click",onBarClick);
    const nav=document.getElementById("bottomNav");
    if(nav)nav.before(el);else document.body.appendChild(el);
  }
  return el;
}
// Короткая подпись состояния повтора на кнопке (полный выбор — в меню loop).
function loopLabel(){
  if(P.range)return"🔁 "+P.range.a.ayah+"–"+P.range.b.ayah;
  if(P.repeat===Infinity)return"🔁 ∞";
  if(P.repeat)return"🔁 ×"+P.repeat;
  return"🔁 Повтор";
}
function srcName(){return SRC?SRC.name:"—";}
function srcIcon(){return SRC&&SRC.type==="audio_user_recording"?"🎙":"🎧";}
function renderBar(){
  if(D.on)dfSyncPlay();               // диафильм открыт — синхронизировать его ▶/⏸ со состоянием плеера
  if(!P.active)return;
  closeMenu();
  const el=barEl();
  el.classList.toggle("min",P.min);
  if(P.min){ // свёрнут: полоска ▶/⏸ + аят + развернуть + закрыть
    el.innerHTML=
      `<button data-act="pp" class="pp" title="${P.playing?"Пауза":"Слушать"}">${P.playing?"⏸":"▶"}</button>`+
      `<span class="lbl" data-act="goto" title="Показать аят в тексте">${POS.sura}:${POS.ayah}</span>`+
      (P.err?`<span class="err" title="${ctx.escAttr(P.err)}">⚠</span>`:"")+
      `<button data-act="min" class="ghost" title="Развернуть плеер">⌃</button>`+
      `<button data-act="close" class="ghost" title="Закрыть плеер">✕</button>`;
    return;
  }
  // Кнопки сгруппированы: транспорт | источник+повторы+скорость | свернуть/закрыть.
  // Группы переносятся по строкам целиком (flex-wrap) — на узком экране всё видно.
  el.innerHTML=
    `<span class="mb-grp">`+
      `<button data-act="prev" title="Предыдущий аят">⏮</button>`+
      `<button data-act="pp" class="pp" title="${P.playing?"Пауза":"Слушать"}">${P.playing?"⏸":"▶"}</button>`+
      `<button data-act="next" title="Следующий аят">⏭</button>`+
      `<span class="lbl" data-act="goto" title="Тап — показать этот аят в тексте">${POS.sura}:${POS.ayah}</span>`+
    `</span>`+
    `<span class="mb-grp">`+
      `<button data-act="src" class="src" title="Выбрать чтеца или набор своих записей">${srcIcon()} ${ctx.esc(srcName())} ▾</button>`+
      `<button data-act="loop" class="${(P.repeat||P.range||P.rangeArm)?"on":""}" title="Повтор аята или диапазона — выбрать из списка">${loopLabel()} ▾</button>`+
      `<button data-act="rate" title="Скорость чтения">⏩ ${P.rate}×</button>`+
    `</span>`+
    `<span class="mb-grp">`+
      `<button data-act="film" title="Полноэкранный визуальный ряд (диафильм)">🎬</button>`+
      `<button data-act="rec" title="Записать текущий аят своим голосом">🎙</button>`+
    `</span>`+
    `<span class="mb-grp">`+
      `<button data-act="min" class="ghost" title="Свернуть плеер в полоску">⌄</button>`+
      `<button data-act="close" class="ghost" title="Закрыть плеер">✕</button>`+
    `</span>`+
    (P.err?`<span class="err" title="${ctx.escAttr(P.err)}">⚠ ${ctx.esc(P.err)}</span>`:"");
}
// Меню выбора источника прямо из плеера: чтецы + наборы записей
function closeMenu(){
  const m=document.getElementById("mediaMenu");if(m)m.remove();
  document.removeEventListener("pointerdown",outsideMenu,true);
}
function outsideMenu(e){
  const m=document.getElementById("mediaMenu");
  if(m&&!m.contains(e.target)&&!e.target.closest('[data-act="src"],[data-act="loop"]'))closeMenu();
}
function openMenu(){
  closeMenu();
  const cur=activeSourceId(),sets=recSets();
  let rs=(ctx.recVisible?ctx.recVisible():reciters());   // только чтецы набора
  // активный чтец всегда в списке, даже если скрыт
  if(!/^rec:/.test(cur)&&!rs.some(r=>r.id===cur)){const c=reciters().find(r=>r.id===cur);if(c)rs=[c,...rs];}
  let h="";
  if(rs.length)h+=`<div class="mm-h">Чтецы</div>`+rs.map(r=>
    `<button data-src="${ctx.escAttr(r.id)}" class="${r.id===cur?"on":""}">🎧 ${ctx.esc(r.name)}</button>`).join("");
  if(sets.length)h+=`<div class="mm-h">Мои записи</div>`+sets.map(s=>
    `<button data-src="rec:${ctx.escAttr(s.id)}" class="${("rec:"+s.id)===cur?"on":""}">🎙 ${ctx.esc(s.name)}</button>`).join("");
  h+=`<div class="mm-h"></div><button data-act="manage">⚙ Управлять чтецами…</button>`;
  const menu=document.createElement("div");
  menu.id="mediaMenu";menu.className="media-menu";menu.innerHTML=h;
  menu.addEventListener("click",e=>{
    const mg=e.target.closest('[data-act="manage"]');
    if(mg){closeMenu();if(ctx.openReciterManager)ctx.openReciterManager();return;}
    const b=e.target.closest("[data-src]");if(!b)return;
    ctx.ss("mediaReciter",b.dataset.src);
    closeMenu();
    setReciter(b.dataset.src);   // сменить источник (сам вызовет renderBar)
    (ctx.renderAudio?ctx.renderAudio():ctx.renderRP());   // синхронизировать радиокнопки в панели 🎧
  });
  barEl().appendChild(menu);
  setTimeout(()=>document.addEventListener("pointerdown",outsideMenu,true),0);
}
// Меню ВЫБОРА повтора — явный список вместо тапа-по-кругу (чтобы было понятно,
// как выбрать цикл). Повтор одного аята и повтор диапазона A–B в одном списке.
function openRepeatMenu(){
  closeMenu();
  const rowNone=!P.repeat&&!P.range;
  let h=`<div class="mm-h">Повтор одного аята</div>`+
    `<button data-loop="off" class="${rowNone?"on":""}">Без повтора</button>`+
    `<button data-loop="r2" class="${P.repeat===2?"on":""}">Повторять 2 раза</button>`+
    `<button data-loop="r3" class="${P.repeat===3?"on":""}">Повторять 3 раза</button>`+
    `<button data-loop="rinf" class="${P.repeat===Infinity?"on":""}">Повторять бесконечно</button>`+
    `<div class="mm-h">Повтор диапазона аятов</div>`;
  if(P.range)
    h+=`<button data-loop="abclear" class="on">Диапазон ${P.range.a.sura}:${P.range.a.ayah} – ${P.range.b.sura}:${P.range.b.ayah} · сбросить</button>`;
  // Поля «с … по …» в текущей суре: ввод номеров без беготни указателем.
  const n=ayahCount(POS.sura)||1;
  const from=Math.min(POS.ayah,n),to=Math.min(POS.ayah+6,n);
  h+=`<div class="mm-range">В суре ${POS.sura}: с
      <input class="mm-in" id="mmFrom" type="number" inputmode="numeric" min="1" max="${n}" value="${from}"> по
      <input class="mm-in" id="mmTo" type="number" inputmode="numeric" min="1" max="${n}" value="${to}">
      <button class="mm-go" data-loop="abset">Повторять</button></div>`;
  const menu=document.createElement("div");
  menu.id="mediaMenu";menu.className="media-menu";menu.innerHTML=h;
  menu.addEventListener("click",e=>{
    const b=e.target.closest("[data-loop]");if(!b)return;
    if(b.dataset.loop==="abset"){
      const n2=ayahCount(POS.sura)||1;
      const cl=v=>Math.max(1,Math.min(n2,parseInt(v,10)||1));
      let f=cl(menu.querySelector("#mmFrom").value),t=cl(menu.querySelector("#mmTo").value);
      if(f>t){const x=f;f=t;t=x;}
      P.range={a:{sura:POS.sura,ayah:f},b:{sura:POS.sura,ayah:t}};P.rangeArm=null;P.repeat=0;
      P.played=0;closeMenu();
      // сразу встать на начало диапазона и играть, если плеер активен
      if(P.active){setPos(POS.sura,f);if(P.playing)playCur();else renderBar();}else renderBar();
      return;
    }
    switch(b.dataset.loop){
      case"off": P.repeat=0;P.range=null;P.rangeArm=null;break;
      case"r2":  P.repeat=2;P.range=null;P.rangeArm=null;break;
      case"r3":  P.repeat=3;P.range=null;P.rangeArm=null;break;
      case"rinf":P.repeat=Infinity;P.range=null;P.rangeArm=null;break;
      case"abclear":P.range=null;P.rangeArm=null;break;
    }
    P.played=0;closeMenu();renderBar();
  });
  barEl().appendChild(menu);
  setTimeout(()=>document.addEventListener("pointerdown",outsideMenu,true),0);
}
const RATE_STEPS=[1,1.25,1.5,0.75];
function onBarClick(e){
  const b=e.target.closest("[data-act]");if(!b)return;
  switch(b.dataset.act){
    case"prev":navStep(-1);break;
    case"next":navStep(1);break;
    case"pp":togglePlay();break;
    case"goto":followText(POS.sura,POS.ayah);break;
    case"film":ctx.openDiafilm(POS.ayah);break;         // диафильм из плеера
    case"rec":openRecPopup(POS.sura,POS.ayah);break;    // запись текущего аята (перенесено с аята)
    case"src":openMenu();break;
    case"loop":openRepeatMenu();break;
    case"min":P.min=!P.min;ctx.ss("mediaMin",P.min);renderBar();break;
    case"rate":{
      P.rate=RATE_STEPS[(RATE_STEPS.indexOf(P.rate)+1)%RATE_STEPS.length];
      ctx.ss("mediaRate",P.rate);
      if(P.audio){P.audio.defaultPlaybackRate=P.rate;P.audio.playbackRate=P.rate;}
      renderBar();break;
    }
    case"close":stopAll();break;
  }
}

// ---------- запись своего чтения (🎙 у аята) ----------
// getUserMedia + MediaRecorder; формат — какой отдал браузер (webm/opus в
// Chrome, mp4/aac в Safari), blob хранится как есть вместе с MIME.
const R={mr:null,stream:null,chunks:[],t0:0,timer:null,pop:null,ayah:null};
function recMime(){
  if(typeof MediaRecorder==="undefined")return null;
  for(const m of ["audio/webm;codecs=opus","audio/webm","audio/mp4","audio/ogg;codecs=opus",""])
    if(m===""||MediaRecorder.isTypeSupported(m))return m;
  return null;
}
function closePop(){
  stopRecTracks();
  if(R.pop){R.pop.remove();R.pop=null;R.ayah=null;}
  document.removeEventListener("pointerdown",outsidePop,true);
}
function outsidePop(e){if(R.pop&&!R.pop.contains(e.target))closePop();}
function stopRecTracks(){
  clearInterval(R.timer);R.timer=null;
  if(R.mr&&R.mr.state!=="inactive")try{R.mr.stop();}catch(e){}
  if(R.stream){R.stream.getTracks().forEach(t=>t.stop());R.stream=null;}
  R.mr=null;
}
export async function openRecPopup(s,a,btn){
  closePop();
  let sets=recSets();
  if(!sets.length){ // первый заход: автосоздаём набор по умолчанию
    sets=[{id:"s"+Date.now().toString(36),name:"Мои записи"}];
    ctx.ss("mediaSets",sets);ctx.renderAudio&&ctx.renderAudio();
  }
  R.ayah={s,a};
  // Подкрутить записываемый аят вверх — чтобы его текст был виден НАД нижним
  // листом записи и его можно было читать во время записи.
  const blk=document.querySelector(`.ayah-block[data-aid="${a}"],.wbw-ayah[data-aid="${a}"]`);
  if(blk)blk.scrollIntoView({behavior:"smooth",block:"start"});
  const pop=document.createElement("div");
  pop.className="rec-pop";R.pop=pop;                 // позиция — нижний лист (CSS)
  document.body.appendChild(pop);
  document.addEventListener("pointerdown",outsidePop,true);
  renderPop();
}
// Рисуем СРАЗУ (без ожидания IndexedDB): «есть ли запись» берём из
// in-memory кэша RECKEYS; если набор ещё не подгружен — покажем без индикатора
// и перерисуем, когда idb ответит (устойчиво к медленному/недоступному idb).
function renderPop(){
  if(!R.pop)return;
  const {s,a}=R.ayah,sets=recSets(),cur=recSetId();
  const recording=R.mr&&R.mr.state==="recording";
  const ks=cur?RECKEYS[cur]:null;
  if(cur&&!ks)loadRecKeys(cur).then(()=>renderPop()); // подтянуть и перерисовать
  const has=!!(ks&&ks.has(sa(s,a)));
  const opts=sets.map(x=>`<option value="${ctx.escAttr(x.id)}" ${x.id===cur?"selected":""}>${ctx.esc(x.name)}</option>`).join("");
  const secs=recording?Math.round((Date.now()-R.t0)/1000):0;
  R.pop.innerHTML=
    `<div class="rp-title"><span>🎙 Запись · аят ${s}:${a}</span><button class="rp-x" data-act="cancel" title="Закрыть">✕</button></div>`+
    `<select data-act="set" title="Набор, куда пишется запись">${opts}</select>`+
    `<div class="rp-row">`+
    (recording
      ?`<button data-act="stop" class="hot">⏹ Стоп</button><span class="rp-rec">${secs} с</span>`
      :`<button data-act="rec" class="hot">● ${has?"Перезаписать":"Записать"}</button>`+
       (has?`<button data-act="play">▶ Прослушать</button><button data-act="del" class="danger">🗑</button>`:""))+
    `</div>`+
    `<div class="rp-note">${has&&!recording?"На этом аяте есть запись. ":""}Текст аята виден выше — читайте во время записи. Хранится только на устройстве, офлайн.</div>`;
  R.pop.onclick=onPopClick;
  const sel=R.pop.querySelector("select");
  if(sel)sel.onchange=()=>{ctx.ss("mediaRecSet",sel.value);renderPop();ctx.renderCenter();};
}
async function onPopClick(e){
  const b=e.target.closest("[data-act]");if(!b)return;
  const {s,a}=R.ayah,set=recSetId();
  switch(b.dataset.act){
    case"cancel":closePop();return;
    case"rec":{
      if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){
        alert("Запись недоступна: нужен HTTPS (или localhost) и поддержка микрофона браузером.");return;
      }
      const mime=recMime();
      if(mime===null){alert("Браузер не поддерживает запись аудио (MediaRecorder).");return;}
      if(P.playing)togglePlay(); // не писать поверх играющего аудио
      try{R.stream=await navigator.mediaDevices.getUserMedia({audio:true});}
      catch(err){
        alert(err&&err.name==="NotAllowedError"
          ?"Доступ к микрофону запрещён. Разрешите его в настройках браузера для этого сайта."
          :"Не удалось открыть микрофон: "+(err&&err.name||err));return;
      }
      R.chunks=[];
      R.mr=new MediaRecorder(R.stream,mime?{mimeType:mime}:undefined);
      R.mr.ondataavailable=ev=>{if(ev.data&&ev.data.size)R.chunks.push(ev.data);};
      R.mr.onstop=async()=>{
        const blob=new Blob(R.chunks,{type:R.mr&&R.mr.mimeType||mime||"audio/webm"});
        if(R.stream){R.stream.getTracks().forEach(t=>t.stop());R.stream=null;}
        R.mr=null;clearInterval(R.timer);R.timer=null;
        if(!blob.size){await renderPop();return;}
        await idbPut({set,ayah:sa(s,a),blob,mime:blob.type,size:blob.size,ts:Date.now()});
        (await loadRecKeys(set)).add(sa(s,a));
        await renderPop();ctx.renderCenter(); // индикатор 🎙 у аята
      };
      R.mr.start();R.t0=Date.now();
      R.timer=setInterval(renderPop,1000);
      await renderPop();break;
    }
    case"stop":stopRecTracks();break; // onstop сохранит и перерисует
    case"play":{
      const r=await idbGet(set,sa(s,a)).catch(()=>null);
      if(!r)return;
      const u=URL.createObjectURL(r.blob);
      const au=new Audio(u);
      au.onended=au.onerror=()=>URL.revokeObjectURL(u);
      au.play().catch(()=>URL.revokeObjectURL(u));
      break;
    }
    case"del":{
      if(!confirm("Удалить запись аята "+s+":"+a+"?"))return;
      await idbDel(set,sa(s,a));
      if(RECKEYS[set])RECKEYS[set].delete(sa(s,a));
      await renderPop();ctx.renderCenter();
      break;
    }
  }
}
// Удаление набора целиком (вызывает index.html после подтверждения):
// blob-ы из IndexedDB; если играл этот набор — остановить
export async function deleteSetData(id){
  await idbClearSet(id).catch(()=>{});
  delete RECKEYS[id];
  if(SRC&&SRC.id==="rec:"+id){SRC=null;stopAll();}
}

// ---------- визуальный слой (фаза 3): картинки по темам фихриста ----------
// Ведётся ТЕМ ЖЕ указателем аята, что и аудио (onAyahChange). Пул картинок
// аята = объединение картинок всех его тем (data/topics/byAyah.json →
// data/media/visual.json). При ВХОДЕ в аят — случайный выбор из пула, держим
// пока аят не сменился (повтор/цикл не перевыбирает); не повторяем предыдущую.
// render_type пока "image" (<img> как background); "video_file" — та же карта.
// Слой НЕЗАВИСИМ от аудио: без аудио ведётся верхним видимым аятом (скролл).
const V={map:null,byAyah:null,loading:null};        // карта visual.json (общая для диафильма)
function loadVisual(){
  if(V.map)return Promise.resolve(true);
  if(V.loading)return V.loading;
  V.loading=Promise.all([
    fetch(ctx.resolveUrl("visual_map")).then(r=>r.ok?r.json():null).catch(()=>null),
    fetch(ctx.resolveUrl("topics",{file:"byAyah.json"})).then(r=>r.ok?r.json():null).catch(()=>null),
  ]).then(([m,b])=>{V.map=m||{topics:{},default:[],pins:{}};V.byAyah=b||{};return true;})
    .catch(()=>{V.map={topics:{},default:[],pins:{}};V.byAyah={};return true;});
  return V.loading;
}
function imgUrl(src){return /^https?:/i.test(src)?src:ctx.resolveUrl("visual_media",{file:src});}
// КУРИРУЕМЫЙ пул аята: пин > объединение картинок его тем (БЕЗ общего default).
// Пусто = у аята нет своей картинки (не подготовлена или намеренно не задана).
function poolCurated(s,a){
  const map=V.map;if(!map)return[];
  const k=sa(s,a);
  if(map.pins&&map.pins[k])return[map.pins[k]];
  const topics=(V.byAyah&&V.byAyah[k])||[];
  const out=[];
  for(const t of topics){const imgs=map.topics&&map.topics[String(t)];if(imgs)for(const im of imgs)if(!out.includes(im))out.push(im);}
  return out;
}
// Выбор картинки для диафильма: держим выбор в пределах аята (state.cur), не
// повторяем предыдущую (state.last). Пул — только курируемый (пин+темы): пусто →
// src="" → нейтральный фон (не заглушка/чужой кадр). Возвращает {src, changed}.
function pickInto(state,s,a){
  const k=sa(s,a);
  if(k===state.cur)return{src:state.img,changed:false};
  state.cur=k;
  const pool=poolCurated(s,a);
  if(!pool.length){state.img="";return{src:"",changed:true};}
  let pick;
  if(pool.length===1)pick=pool[0];
  else{const alt=pool.filter(p=>p!==state.last);const arr=alt.length?alt:pool;pick=arr[Math.floor(Math.random()*arr.length)];}
  state.last=pick;state.img=pick;return{src:pick,changed:true};
}

// ---------- ДИАФИЛЬМ (полноэкранный визуальный ряд) ----------
// Отдельный полноэкранный слой поверх ТОЙ ЖЕ карты (visual.json) и общей функции
// выбора (chooseImage), что и полоса — но полосу НЕ трогает. Строго ОДИН аят =
// ОДИН кадр. Указатель ведёт аудио-плеер (onAyahChange) при прослушивании, либо
// ручной свайп/тап при выключенном звуке (НЕ «верхний видимый»). Пустой пул →
// нейтральный фон (не подставляем чужую картинку). Видео — только задел.
const D={on:false,sura:0,ayah:0,textMode:"artr",textHidden:false,imgOn:true,audio:true,fit:"cover",scale:1,wake:null,el:null,la:null,lb:null,front:0,token:0,swiped:false};
const Dsel={cur:"",last:"",img:""};                  // СВОЁ состояние выбора картинки (отдельно от полосы)
const DF_MODES=["artr","ar","tr","none"];
const DF_LABEL={artr:"Аа+ع",ar:"ع",tr:"Аа",none:"—"};
const DF_SCALES=[0.85,1,1.2,1.45];                   // свой размер шрифта диафильма (независим от чтения)
let dfKaraoke=null;                                   // ХУК караоке (оставлен, не реализован)
export function onDiafilmWord(cb){dfKaraoke=cb;}      // подписка на слово-по-слову (задел)

function dfEnsure(){
  if(D.el)return D.el;
  const el=document.createElement("div");el.id="diafilm";el.className="diafilm";
  el.innerHTML=`<div class="df-layer" data-l="0"></div><div class="df-layer" data-l="1"></div>`+
    `<div class="df-scrim"></div><div class="df-text" id="dfText"></div>`+
    `<div class="df-ctrls"><button class="df-btn" data-act="pp" title="Аудио: включить/пауза">${P.playing?"⏸":"▶"}</button>`+
    `<button class="df-btn" data-act="mode" title="Текст: арабский/перевод/оба/нет">${DF_LABEL[D.textMode]}</button>`+
    `<button class="df-btn" data-act="img" title="Картинки вкл/выкл (без картинок — чистое пофреймовое слушание)">${D.imgOn?"🖼":"🚫"}</button>`+
    `<button class="df-btn" data-act="fit" title="Кадр: заполнить (обрезать) / вписать (целиком)">${D.fit==="contain"?"▭":"⤢"}</button>`+
    `<button class="df-btn" data-act="size" title="Размер шрифта">A</button>`+
    `<button class="df-btn" data-act="close" title="Выйти">✕</button></div>`+
    `<button class="df-nav df-prev" data-act="prev" title="Предыдущий аят">‹</button>`+
    `<button class="df-nav df-next" data-act="next" title="Следующий аят">›</button>`;
  document.body.appendChild(el);
  D.el=el;D.la=el.querySelector('[data-l="0"]');D.lb=el.querySelector('[data-l="1"]');D.front=0;
  el.addEventListener("click",e=>{
    const b=e.target.closest("[data-act]");
    if(!b){if(D.swiped){D.swiped=false;return;}dfToggleText();return;}   // тап по экрану → скрыть/показать текст
    e.stopPropagation();
    const act=b.dataset.act;
    if(act==="close")ctx.exitDiafilm();
    else if(act==="pp")dfTogglePlay();
    else if(act==="mode")dfCycleMode();
    else if(act==="img")dfToggleImg();
    else if(act==="fit")dfCycleFit();
    else if(act==="size")dfCycleSize();
    else if(act==="prev")dfManual(-1);
    else if(act==="next")dfManual(1);
  });
  // Свайп влево/вправо — листание аятов (актуально при выключенном звуке)
  let x0=null,y0=null;
  el.addEventListener("touchstart",e=>{if(e.touches.length===1){x0=e.touches[0].clientX;y0=e.touches[0].clientY;}},{passive:true});
  el.addEventListener("touchend",e=>{
    if(x0==null)return;const t=e.changedTouches[0];const dx=t.clientX-x0,dy=t.clientY-y0;x0=null;
    if(Math.abs(dx)>48&&Math.abs(dx)>Math.abs(dy)*1.4){D.swiped=true;dfManual(dx<0?1:-1);}
  },{passive:true});
  return el;
}
function dfShow(src){
  dfEnsure();
  const show=D.front===0?D.lb:D.la, hide=D.front===0?D.la:D.lb;
  if(src){show.style.backgroundImage=`url("${imgUrl(src).replace(/"/g,'%22')}")`;show.classList.remove("df-neutral");}
  else{show.style.backgroundImage="";show.classList.add("df-neutral");}   // пустой пул → нейтральный фон
  show.classList.remove("kb");void show.offsetWidth;show.classList.add("kb"); // Ken Burns
  show.style.opacity="1";hide.style.opacity="0";                              // crossfade
  D.front=D.front===0?1:0;
}
async function dfRenderText(s,a){
  const el=document.getElementById("dfText");if(!el)return;
  if(D.textMode==="none"||D.textHidden){el.classList.add("hidden");return;}
  el.classList.remove("hidden");
  const tok=++D.token, mode=D.textMode;
  let ar="",tr="",trId=null;
  if(mode==="ar"||mode==="artr"){await ctx.ensureText("_arabic",s).catch(()=>{});ar=ctx.getArabic(s,a)||"";}
  if(mode==="tr"||mode==="artr"){trId=ctx.primaryTransId();if(trId){await ctx.ensureText(trId,s).catch(()=>{});tr=ctx.getText(trId,s,a)||"";}}
  if(tok!==D.token||!D.on)return;                       // устарело (сменился аят/режим/закрылось)
  let html=`<div class="df-key">${s}:${a}</div>`;
  if(ar)html+=`<div class="df-ar arabic-main">${ctx.esc(ar)}</div>`;
  if(tr)html+=`<div class="df-tr">${ctx.esc(tr)}</div>`;
  el.innerHTML=html;
}
function dfGoto(s,a){
  D.sura=s;D.ayah=a;
  if(D.el)D.el.classList.toggle("df-audio",!!(P.active&&P.playing));   // аудио ведёт → прячем стрелки
  if(D.imgOn){const r=pickInto(Dsel,s,a);dfShow(r.src);}              // пустой пул → нейтральный фон
  else dfShow("");                                  // режим без картинок — всегда нейтральный фон
  dfRenderText(s,a);
  if(P.playing)dfWake(true);
  if(dfKaraoke)try{dfKaraoke(s,a);}catch(e){}
}
// Ручное листание (свайп/стрелки). При активном аудио — двигаем плеер (он сам
// через onAyahChange вернётся в dfGoto); иначе двигаем только диафильм.
function dfManual(dir){
  const t=dir>0?nextAyah(D.sura,D.ayah):prevAyah(D.sura,D.ayah);
  if(!t)return;
  if(P.active){P.played=0;setPos(t.sura,t.ayah);if(P.playing)playCur();}
  else dfGoto(t.sura,t.ayah);
}
function dfOnAyah(s,a){if(D.on)dfGoto(s,a);}            // подписчик оси аята (аудио ведёт кадр)
function dfToggleText(){D.textHidden=!D.textHidden;dfRenderText(D.sura,D.ayah);}
// Аудио прямо из диафильма: старт с кадра / пауза. Запоминает намерение
// (tl_dfAudio) — при следующем входе аудио стартует само (или нет).
function dfTogglePlay(){
  if(P.active)togglePlay();          // играет или на паузе — переключить
  else playFrom(D.sura,D.ayah);      // ещё не запускали — старт с кадра
  D.audio=!!P.playing;ctx.ss("dfAudio",D.audio);
  dfSyncPlay();
}
function dfSyncPlay(){
  if(!D.el)return;
  const b=D.el.querySelector('[data-act="pp"]');if(b)b.textContent=P.playing?"⏸":"▶";
  D.el.classList.toggle("df-audio",!!(P.active&&P.playing));   // аудио ведёт → прячем стрелки
}
function dfToggleImg(){
  D.imgOn=!D.imgOn;ctx.ss("dfImg",D.imgOn);
  const b=D.el&&D.el.querySelector('[data-act="img"]');if(b)b.textContent=D.imgOn?"🖼":"🚫";
  dfGoto(D.sura,D.ayah);                              // перерисовать: картинка ↔ нейтральный фон
}
function dfApplyScale(){if(D.el)D.el.style.setProperty("--df-scale",D.scale);}
function dfApplyFit(){if(D.el)D.el.classList.toggle("df-contain",D.fit==="contain");}   // вписать (contain) ↔ заполнить (cover)
function dfCycleFit(){
  D.fit=D.fit==="contain"?"cover":"contain";ctx.ss("dfFit",D.fit);
  const b=D.el&&D.el.querySelector('[data-act="fit"]');if(b)b.textContent=D.fit==="contain"?"▭":"⤢";
  dfApplyFit();
}
function dfCycleSize(){
  let i=DF_SCALES.indexOf(D.scale);D.scale=DF_SCALES[(i+1)%DF_SCALES.length];
  ctx.ss("dfScale",D.scale);dfApplyScale();
}
function dfCycleMode(){
  const i=DF_MODES.indexOf(D.textMode);D.textMode=DF_MODES[(i+1)%DF_MODES.length];
  ctx.ss("dfText",D.textMode);
  const b=D.el&&D.el.querySelector('[data-act="mode"]');if(b)b.textContent=DF_LABEL[D.textMode];
  D.textHidden=false;dfRenderText(D.sura,D.ayah);
}
async function dfWake(on){
  try{
    if(on){if(("wakeLock"in navigator)&&!D.wake){D.wake=await navigator.wakeLock.request("screen");
      if(D.wake&&D.wake.addEventListener)D.wake.addEventListener("release",()=>{D.wake=null;});}}
    else if(D.wake){await D.wake.release();D.wake=null;}
  }catch(e){D.wake=null;}                                // нет API / отказ — молча (фолбэк)
}
export async function openDiafilm(s,a){
  D.textMode=ctx.gs("dfText","artr");if(!DF_MODES.includes(D.textMode))D.textMode="artr";
  D.imgOn=ctx.gs("dfImg",true)!==false;
  D.audio=ctx.gs("dfAudio",true)!==false;            // по умолчанию аудио стартует само
  D.fit=ctx.gs("dfFit","cover")==="contain"?"contain":"cover";
  D.scale=ctx.gs("dfScale",1);if(!DF_SCALES.includes(D.scale))D.scale=1;
  D.textHidden=false;
  Dsel.cur="";                                       // свежий случайный выбор при входе
  await loadVisual();
  dfEnsure();
  dfApplyScale();dfApplyFit();
  D.on=true;document.body.classList.add("df-open");
  const st=(P.active&&P.playing)?{s:POS.sura,a:POS.ayah}:{s:s||ctx.ST.surah,a:a||1};
  dfGoto(st.s,st.a);
  // Авто-старт чтения (по умолчанию): в жесте входа, если ещё не играет.
  if(D.audio&&!(P.active&&P.playing))playFrom(st.s,st.a);
  if(P.playing)dfWake(true);
  dfSyncPlay();
}
export function closeDiafilm(){
  if(!D.on)return;
  D.on=false;document.body.classList.remove("df-open");
  dfWake(false);
  if(D.el){D.el.remove();D.el=null;}
}
export function diafilmPos(){return{s:D.sura,a:D.ayah};}
export function diafilmOpen(){return D.on;}

// ---------- публичный интерфейс (вызывается из index.html) ----------
export function init(c){
  ctx=c;
  P.rate=+ctx.gs("mediaRate",1)||1;
  if(!RATE_STEPS.includes(P.rate))P.rate=1;
  P.min=ctx.gs("mediaMin",true)!==false;   // плеер свёрнут в тонкую полоску по умолчанию
  onAyahChange(followText);     // текстовый слой — первый подписчик оси аята
  onAyahChange(dfOnAyah);       // диафильм — тот же указатель ведёт кадр
  // индикаторы 🎙: подтянуть ключи активного набора и перекрасить аяты
  const rid=recSetId();
  if(rid)loadRecKeys(rid).then(ks=>{if(ks.size)ctx.renderCenter();});
}
// Старт (или перескок) воспроизведения с аята s:a активным источником
export function playFrom(s,a){
  if(!SRC){
    SRC=makeSourceById(activeSourceId());
    if(!SRC){alert("В конфигурации нет чтецов (config.json → audio.reciters).");return;}
  }
  P.active=true;P.played=0;
  const same=POS.sura===s&&POS.ayah===a;
  setPos(s,a);
  if(same)followText(s,a); // повторный ▶ на том же аяте: событие не эмитится — подсветим явно
  playCur();
}
// Смена источника (чтец или набор записей rec:<id>) на лету:
// источник новый, указатель аята тот же
export function setReciter(id){
  const src=makeSourceById(id);
  if(!src)return;
  SRC=src;
  if(P.active){renderBar();if(P.playing)playCur();} // тот же аят — новым голосом
}
export function stop(){stopAll();}
export function isActive(){return P.active;}
