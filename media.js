// ============================================================
// МЕДИА-МОДУЛЬ «Библиотеки тафсиров» — фаза 1: аудио-плеер (поаятные CDN-чтецы)
// ============================================================
// ES-модуль. Грузится ЛЕНИВО из index.html (mediaMod() → import("./media.js")):
// пока пользователь не тронул аудио — ни байта этого кода, ни <audio>-элементов.
//
// Архитектура (развязка слоёв вокруг оси аята):
//   • ОСЬ АЯТА: указатель POS {sura, ayah} — единственный источник истины.
//     Смена аята эмитит событие; подписчики — текстовый слой (подсветка/скролл,
//     followText) и, в следующих фазах, визуальный слой и караоке-подсветка
//     (внешний хук — export onAyahChange).
//   • ИСТОЧНИК: единый интерфейс getMediaFor(s,a) → {url}. Фаза 1 — модель
//     «файл-на-аят» (EveryAyah, audio_cdn). Сплошной файл с таблицей таймингов
//     (QUL) и записи пользователя (фаза 2) встанут за тот же интерфейс.
//   • Смена чтеца меняет только источник; указатель аята сохраняется — текст
//     и (в будущем) визуальный слой не сбиваются.
//
// Связь с приложением — ТОЛЬКО через ctx из index.html: let-глобалы (ST,
// CONFIG, qpcMeta) — геттеры, функции (resolveUrl, jumpTo, gs/ss, esc) — как есть.

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
function ayahCount(s){const su=ctx.SURAHS.find(x=>x.id===s);return su?su.n:0;}
function nextAyah(s,a){
  if(a<ayahCount(s))return{sura:s,ayah:a+1};
  return s<114?{sura:s+1,ayah:1}:null;
}
function prevAyah(s,a){
  if(a>1)return{sura:s,ayah:a-1};
  return s>1?{sura:s-1,ayah:ayahCount(s-1)}:null;
}

// ---------- аудио-источники (фаза 1: audio_cdn «файл-на-аят») ----------
function reciters(){return(ctx.CONFIG.audio&&ctx.CONFIG.audio.reciters)||[];}
function activeReciter(){
  const rs=reciters();if(!rs.length)return null;
  const id=ctx.gs("mediaReciter",(ctx.CONFIG.audio&&ctx.CONFIG.audio.default)||rs[0].id);
  return rs.find(r=>r.id===id)||rs[0];
}
function makeSource(rec){
  return{
    id:rec.id,name:rec.name,type:rec.type||"audio_cdn",
    // «файл-на-аят»: сегмент = весь файл, таймингов нет
    getMediaFor(s,a){
      const file=String(s).padStart(3,"0")+String(a).padStart(3,"0")+".mp3";
      return{url:ctx.resolveUrl("audio_cdn",{subdir:rec.subdir,file})};
    },
  };
}
let SRC=null;

// ---------- плеер ----------
const P={
  audio:null,pre:null,      // основной <audio> и префетчер следующего аята
  playing:false,
  active:false,             // пилюля показана (плеер «включён»)
  rate:1,
  repeat:0,                 // повтор аята: 0=выкл, 2/3=N раз, Infinity=∞
  played:0,                 // сколько раз доигран текущий аят (для repeat)
  range:null,               // повтор диапазона {a:{sura,ayah}, b:{sura,ayah}}
  rangeArm:null,            // первый тап A–B: помечено начало, ждём конец
  err:"",
};
function ensureAudio(){
  if(P.audio)return P.audio;
  const au=new Audio();
  au.preload="auto";
  au.addEventListener("ended",onEnded);
  au.addEventListener("error",()=>{
    if(!P.active||!au.getAttribute("src"))return; // намеренная остановка — не ошибка
    P.playing=false;P.err="аудио недоступно (сеть/CDN)";renderPill();
  });
  P.audio=au;
  return au;
}
function playCur(){
  const m=SRC.getMediaFor(POS.sura,POS.ayah);
  const au=ensureAudio();
  P.err="";
  au.src=m.url;
  au.defaultPlaybackRate=P.rate;au.playbackRate=P.rate;
  const pr=au.play();
  if(pr)pr.catch(err=>{
    P.playing=false;
    // NotAllowedError — iOS/автоплей без жеста (ждём явного ▶); прочее — сеть/CDN
    P.err=err&&err.name==="NotAllowedError"?"нажмите ▶ (автовоспроизведение заблокировано)":"аудио недоступно (сеть/CDN)";
    renderPill();
  });
  P.playing=true;renderPill();
  prefetchNext();
}
function onEnded(){
  P.played++;
  if(P.repeat&&P.played<P.repeat){P.audio.currentTime=0;P.audio.play();return;}
  P.played=0;
  let nx=nextAyah(POS.sura,POS.ayah);
  if(P.range&&(!nx||key(nx.sura,nx.ayah)>key(P.range.b.sura,P.range.b.ayah)))
    nx={sura:P.range.a.sura,ayah:P.range.a.ayah};    // конец диапазона → к началу
  if(!nx){P.playing=false;renderPill();return;}      // конец Корана
  setPos(nx.sura,nx.ayah);
  playCur();
}
function prefetchNext(){
  const nx=nextAyah(POS.sura,POS.ayah);
  if(!nx)return;
  if(!P.pre){P.pre=new Audio();P.pre.preload="auto";P.pre.muted=true;}
  P.pre.src=SRC.getMediaFor(nx.sura,nx.ayah).url;
}
function togglePlay(){
  const au=ensureAudio();
  if(P.playing){au.pause();P.playing=false;renderPill();return;}
  if(au.getAttribute("src")&&!au.ended){ // пауза → продолжить с места
    au.play().catch(()=>{});P.playing=true;renderPill();
  }else playCur();                       // остановились на конце — заново текущий аят
}
function navStep(dir){
  const t=dir>0?nextAyah(POS.sura,POS.ayah):prevAyah(POS.sura,POS.ayah);
  if(!t)return;
  P.played=0;setPos(t.sura,t.ayah);playCur();
}
function stopAll(){
  P.playing=false;P.active=false;P.range=null;P.rangeArm=null;P.played=0;P.err="";
  if(P.audio){P.audio.pause();P.audio.removeAttribute("src");P.audio.load();}
  if(P.pre){P.pre.removeAttribute("src");}
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

// ---------- пилюля (UI плеера) ----------
function pillEl(){
  let el=document.getElementById("mediaPill");
  if(!el){
    el=document.createElement("div");
    el.id="mediaPill";el.className="media-pill";
    el.addEventListener("click",onPillClick);
    document.body.appendChild(el);
  }
  return el;
}
const REP_STEPS=[0,2,3,Infinity];
function repLabel(){return P.repeat===Infinity?"🔁∞":P.repeat?"🔁"+P.repeat:"🔁";}
function abLabel(){return P.rangeArm?"A‥":"A–B";}
function renderPill(){
  if(!P.active)return;
  const el=pillEl();
  el.innerHTML=
    `<button data-act="prev" title="Предыдущий аят">⏮</button>`+
    `<button data-act="pp" class="pp" title="${P.playing?"Пауза":"Слушать"}">${P.playing?"⏸":"▶"}</button>`+
    `<button data-act="next" title="Следующий аят">⏭</button>`+
    `<span class="lbl" data-act="goto" title="Показать аят в тексте">${POS.sura}:${POS.ayah}</span>`+
    `<button data-act="rep" class="${P.repeat?"on":""}" title="Повтор аята: выкл → ×2 → ×3 → ∞">${repLabel()}</button>`+
    `<button data-act="ab" class="${(P.range||P.rangeArm)?"on":""}" title="Повтор диапазона: 1-й тап — начало, 2-й — конец, 3-й — сброс">${abLabel()}</button>`+
    `<button data-act="rate" title="Скорость воспроизведения">${P.rate}×</button>`+
    `<button data-act="close" title="Закрыть плеер">✕</button>`+
    (P.err?`<span class="err" title="${ctx.escAttr(P.err)}">⚠ ${ctx.esc(P.err)}</span>`:"");
}
const RATE_STEPS=[1,1.25,1.5,0.75];
function onPillClick(e){
  const b=e.target.closest("[data-act]");if(!b)return;
  switch(b.dataset.act){
    case"prev":navStep(-1);break;
    case"next":navStep(1);break;
    case"pp":togglePlay();break;
    case"goto":followText(POS.sura,POS.ayah);break;
    case"rep":{
      P.repeat=REP_STEPS[(REP_STEPS.indexOf(P.repeat)+1)%REP_STEPS.length];
      P.played=0;renderPill();break;
    }
    case"ab":{
      if(P.range){P.range=null;P.rangeArm=null;}                 // 3-й тап — сброс
      else if(P.rangeArm){                                       // 2-й тап — конец
        let a=P.rangeArm,b2={sura:POS.sura,ayah:POS.ayah};
        if(key(a.sura,a.ayah)>key(b2.sura,b2.ayah)){const t=a;a=b2;b2=t;}
        P.range={a,b:b2};P.rangeArm=null;
      }else P.rangeArm={sura:POS.sura,ayah:POS.ayah};            // 1-й тап — начало
      renderPill();break;
    }
    case"rate":{
      P.rate=RATE_STEPS[(RATE_STEPS.indexOf(P.rate)+1)%RATE_STEPS.length];
      ctx.ss("mediaRate",P.rate);
      if(P.audio){P.audio.defaultPlaybackRate=P.rate;P.audio.playbackRate=P.rate;}
      renderPill();break;
    }
    case"close":stopAll();break;
  }
}

// ---------- публичный интерфейс (вызывается из index.html) ----------
export function init(c){
  ctx=c;
  P.rate=+ctx.gs("mediaRate",1)||1;
  if(!RATE_STEPS.includes(P.rate))P.rate=1;
  onAyahChange(followText); // текстовый слой — первый подписчик оси аята
}
// Старт (или перескок) воспроизведения с аята s:a активным чтецом
export function playFrom(s,a){
  if(!SRC){
    const rec=activeReciter();
    if(!rec){alert("В конфигурации нет чтецов (config.json → audio.reciters).");return;}
    SRC=makeSource(rec);
  }
  P.active=true;P.played=0;
  const same=POS.sura===s&&POS.ayah===a;
  setPos(s,a);
  if(same)followText(s,a); // повторный ▶ на том же аяте: событие не эмитится — подсветим явно
  playCur();
}
// Смена чтеца на лету: источник новый, указатель аята тот же
export function setReciter(id){
  const rec=reciters().find(r=>r.id===id);
  if(!rec)return;
  SRC=makeSource(rec);
  if(P.active&&P.playing)playCur(); // тот же аят — голосом нового чтеца
}
export function stop(){stopAll();}
export function isActive(){return P.active;}
