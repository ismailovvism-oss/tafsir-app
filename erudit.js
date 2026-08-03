// ============================================================
// МОДУЛЬ «🎓 ЭРУДИТ» — занимательные упражнения по Корану
// ============================================================
// ES-модуль. Грузится ЛЕНИВО из index.html (eruditMod() → import("./erudit.js")):
// пока пользователь не зашёл в режим — ни байта этого кода.
//
// Архитектура (движок общий, упражнения — сменные):
//   • ДВИЖОК РАУНДА (startRound/answer/nextQ/finish) ничего не знает о предмете.
//     Он просит у упражнения очередное ЗАДАНИЕ и проверяет ответ по индексу.
//     Генератор АСИНХРОННЫЙ: задания по аятам требуют догрузки чанков суры.
//   • УПРАЖНЕНИЕ = запись в EXERCISES: {id, заголовок, виды заданий, defCfg,
//     genQ(cfg,pool,sess)} → задание {kind, ask, sub, opts[], correct, explain}.
//     Чтобы добавить следующее (темы, тартиб, «Лестница знания»), дописывается
//     одна запись — движок, статистика и экраны не трогаются.
//   • НАСТРОЙКИ У КАЖДОГО УПРАЖНЕНИЯ СВОИ (DB.cfg[exId]): охват «весь Коран»
//     разумен для названий сур и бессмыслен для аятов.
//   • ПУЛ ВЗВЕШЕН: сура, где чаще ошибались, выпадает чаще (items[id].wrong/seen).
//   • ДИСТРАКТОРЫ НЕ СЛУЧАЙНЫ: сосед по номеру и похожее имя для сур; хвосты
//     ДРУГИХ аятов той же суры (та же фасыля) для «продолжить»; формы того же
//     корня для «пропущенного слова». Случайные варианты угадываются по
//     исключению и ничему не учат.
//   • АДАБ ТЕКСТА: обрезанный аят живёт только в вопросе (с многоточием); в
//     разборе всегда даётся КАНОНИЧЕСКИЙ аят целиком (data/tafsirs/_arabic) с
//     переводом и адресом, а неверный вариант гасится — чтобы в памяти оседал
//     верный текст, а не выбранный по ошибке.
//   • В зачёт цели/серии чтения результаты НЕ идут (как проверка заучивания).
//
// Связь с приложением — ТОЛЬКО через ctx из index.html (let-глобалы приходят
// геттерами; текст берётся из тех же чанков и кеша, что у ленты чтения).
// Разметка рисуется в #erdBody, клики — ОДИН делегированный обработчик по
// data-act (inline-onclick недоступен: у модуля своя область видимости).

let ctx=null;
export function init(c){ctx=c;}

const esc=s=>ctx.esc(String(s==null?"":s));

// view: "hub" | "setup" | "round" | "result"
const E={view:"hub",ex:null,sess:null};

// ---------- мелочи ----------
const SU=id=>ctx.SURAHS[id-1];
const rnd=n=>Math.floor(Math.random()*n);
const pick=a=>a[rnd(a.length)];
function shuffle(a){const x=a.slice();for(let i=x.length-1;i>0;i--){const j=rnd(i+1);const t=x[i];x[i]=x[j];x[j]=t;}return x;}
function range(a,b){const o=[];for(let i=a;i<=b;i++)o.push(i);return o;}
const pct=(a,b)=>b?Math.round(a*100/b):0;
function mmss(ms){const s=Math.max(0,Math.round(ms/1000));return Math.floor(s/60)+":"+String(s%60).padStart(2,"0");}
function plural(n,one,few,many){const m10=n%10,m100=n%100;if(m10===1&&m100!==11)return one;if(m10>=2&&m10<=4&&(m100<10||m100>=20))return few;return many;}
function normName(s){
  return String(s||"").toLowerCase().replace(/ё/g,"е")
    .replace(/^(аль|ан|ас|ат|аз|ар|аш|ад)[-\s]/,"").replace(/[-\s'’]/g,"");
}
function commonPrefix(a,b){let i=0;while(i<a.length&&i<b.length&&a[i]===b[i])i++;return i;}
// Перевод приходит размеченным (сноски, жирный, карточки слов) — в варианте
// ответа всё это лишнее и выдаёт длину; оставляем голый текст.
function plain(t){
  return String(t||"")
    .replace(/^\s*\[\^[^\]]+\]:.*$/gm,"")      // определения сносок отдельными строками
    .replace(/\[\^[^\]]+\]/g,"")               // ссылки на сноски
    .replace(/\[\[([^\]:]+)::[^\]]*\]\]/g,"$1")// карточки [[видимое::текст]]
    .replace(/[*_`#>]/g,"")
    .replace(/\s+/g," ").trim();
}
const arSpan=s=>`<span class="erd-ar">${esc(s)}</span>`;
// Знаки вакфа стоят в тексте отдельными «словами» — при нарезке аята это не слова.
const PAUSE=/^[ۖ-ۭؕ-ؚ۟-ۨ]+$/;
const arWords=t=>String(t||"").split(/\s+/).filter(w=>w&&!PAUSE.test(w));
// У первого аята суры басмала входит в текст. Для «продолжить» и «пропущенное
// слово» такой аят негоден: разрез (или пропуск) попадает внутрь басмалы, и
// вопрос теряет смысл — «что идёт после بسم الله الرحمن الرحيم» верно для 113 сур.
const BASMALA=/^بسم\s+الله\s+الرحمن\s+الرحيم/;
function startsWithBasmala(t){
  const n=String(t||"").replace(/[ً-ْٰٓ-ٕـۖ-ۭ]/g,"").replace(/[آأإٱ]/g,"ا").replace(/\s+/g," ").trim();
  return BASMALA.test(n);
}
function snip(t,n){                            // короткая выжимка длинного аята для варианта ответа
  const w=String(t||"").split(/\s+/).filter(Boolean);
  return w.length<=n?w.join(" "):w.slice(0,n).join(" ")+" …";
}

// ---------- хранилище (tl_erudit; вне облачного синка — результат локален) ----------
const DEF_CFG={
  suraNames:{scope:"all",custom:"78-114",len:10,kinds:{name:true,arabic:true,count:true,order:true}},
  ayahs:{scope:"j30",custom:"78-114",len:10,lang:"mix",kinds:{sura:true,cont:true,next:true,word:true}},
};
let DB=null;
function db(){
  if(DB)return DB;
  const raw=ctx.gs("erudit",null)||{};
  let cfg=raw.cfg||{};
  if(cfg.scope)cfg={suraNames:cfg};              // миграция: до появления второго упражнения конфиг был плоским
  DB={v:2,ex:raw.ex||{},items:raw.items||{},cfg:{}};
  for(const id of Object.keys(DEF_CFG)){
    const d=DEF_CFG[id],c=Object.assign({},d,cfg[id]||{});
    c.kinds=Object.assign({},d.kinds,(cfg[id]||{}).kinds||{});
    DB.cfg[id]=c;
  }
  return DB;
}
function dbSave(){ctx.ss("erudit",db());}
const cfg=()=>db().cfg[E.ex]||DEF_CFG[E.ex];
function exStat(id){const d=db();if(!d.ex[id])d.ex[id]={plays:0,best:0,attempts:0,correct:0,lastTs:0};return d.ex[id];}
function itemStat(key){const d=db();if(!d.items[key])d.items[key]={seen:0,wrong:0,ts:0};return d.items[key];}

// ---------- охваты ----------
const SCOPES=[
  {id:"all",label:"Весь Коран",sub:"1–114",list:()=>range(1,114)},
  {id:"j30",label:"Джуз 30",sub:"78–114",list:()=>range(78,114)},
  {id:"mufassal",label:"Муфассаль",sub:"50–114",list:()=>range(50,114)},
  {id:"first",label:"Начало",sub:"1–20",list:()=>range(1,20)},
  {id:"custom",label:"Свои суры",sub:"список",list:c=>parseSuras(c.custom).list},
];
// «78-114, 36» → номера сур. Плохие токены ВОЗВРАЩАЕМ (UI покажет): опечатка
// «115» иначе тихо сузила бы охват, и человек искал бы причину сам.
function parseSuras(str){
  const out=new Set(),bad=[];
  for(const tok of String(str||"").split(/[,;\s]+/)){
    if(!tok)continue;
    const m=tok.match(/^(\d{1,3})(?:[-–—](\d{1,3}))?$/);
    if(!m){bad.push(tok);continue;}
    let a=+m[1],b=m[2]?+m[2]:a;
    if(a<1||a>114||b<1||b>114){bad.push(tok);continue;}
    if(a>b){const t=a;a=b;b=t;}
    for(let x=a;x<=b;x++)out.add(x);
  }
  return {list:[...out].sort((x,y)=>x-y),bad};
}
function scopeList(c){
  const sc=SCOPES.find(s=>s.id===c.scope)||SCOPES[0];
  const l=sc.list(c);
  return l.length?l:range(1,114);
}

// ---------- взвешенный выбор суры ----------
function weightOf(id){
  const st=db().items[String(id)];
  if(!st||!st.seen)return 1.8;                   // ещё не спрашивали — покажем скорее
  return 1+2.5*(st.wrong/st.seen);
}
function pickWeighted(pool,exclude){
  const cand=exclude?pool.filter(x=>x!==exclude):pool;
  if(!cand.length)return pool[rnd(pool.length)];
  let sum=0;const w=cand.map(id=>{const v=weightOf(id);sum+=v;return v;});
  let r=Math.random()*sum;
  for(let i=0;i<cand.length;i++){r-=w[i];if(r<=0)return cand[i];}
  return cand[cand.length-1];
}

// ---------- дистракторы-суры ----------
// Сосед по номеру, похожее имя, случайная. Если охват короче четырёх — добираем
// из всего Корана, иначе в списке из двух сур вопрос вырождается.
function distractors(correct,pool,n){
  const base=pool.length>=n+1?pool:range(1,114);
  const cand=base.filter(x=>x!==correct);
  const out=[];
  const take=arr=>{for(const x of arr){if(out.length>=n)break;if(!out.includes(x))out.push(x);}};
  const near=cand.filter(x=>Math.abs(x-correct)<=6).sort((a,b)=>Math.abs(a-correct)-Math.abs(b-correct));
  take(shuffle(near.slice(0,4)).slice(0,1));
  const cn=normName(SU(correct).ru);
  const sim=cand.map(x=>({x,s:commonPrefix(cn,normName(SU(x).ru))})).filter(o=>o.s>=3)
    .sort((a,b)=>b.s-a.s).map(o=>o.x);
  take(sim.slice(0,3));
  take(shuffle(cand));
  return out.slice(0,n);
}
function countDistractors(correct,n){            // соперники — РЕАЛЬНЫЕ длины других сур
  const val=SU(correct).n;
  const seen=new Set([val]),out=[];
  const others=ctx.SURAHS.filter(s=>s.id!==correct).map(s=>s.n)
    .sort((a,b)=>Math.abs(a-val)-Math.abs(b-val));
  for(const v of others){if(out.length>=n)break;if(seen.has(v))continue;seen.add(v);out.push(v);}
  while(out.length<n){const v=val+1+out.length;if(!seen.has(v)){seen.add(v);out.push(v);}}
  return out;
}

// ============================================================
// УПРАЖНЕНИЕ 1 — «Названия сур»
// ============================================================
const SURA_KINDS=[
  {id:"name",ic:"🔢",label:"Номер ↔ название",hint:"«Сура 36 — какая?» и обратно"},
  {id:"arabic",ic:"🕌",label:"Арабское ↔ русское",hint:"الكهف ↔ Аль-Кахф"},
  {id:"count",ic:"📏",label:"Число аятов",hint:"«Сколько аятов в Аль-Кахф?»"},
  {id:"order",ic:"↕️",label:"Соседи и порядок",hint:"«Что после Ан-Наср?», расстановка"},
];
function suraFact(id){
  const su=SU(id);
  return `${id}. ${esc(su.ru)} ${arSpan(su.name)} — ${su.n} ${plural(su.n,"аят","аята","аятов")}`;
}
function mcq(kind,ask,sub,correct,others,label,explain){
  const ids=shuffle([correct].concat(others));
  return {kind,ask,sub,sura:correct,
    opts:ids.map(id=>({html:label(id)})),
    correct:ids.indexOf(correct),explain};
}
async function genSuraQ(c,pool){
  const kinds=SURA_KINDS.filter(k=>c.kinds[k.id]).map(k=>k.id);
  const k=kinds.length?pick(kinds):"name";
  if(k==="name"){
    const id=pickWeighted(pool),d=distractors(id,pool,3);
    if(Math.random()<0.5)
      return mcq("name",`Сура <b>№${id}</b> — какая это сура?`,"Номер → название",id,d,
        x=>`${esc(SU(x).ru)} ${arSpan(SU(x).name)}`,suraFact(id));
    return mcq("name",`«${esc(SU(id).ru)}» — какой номер?`,"Название → номер",id,d,
      x=>`№ ${x}`,suraFact(id));
  }
  if(k==="arabic"){
    const id=pickWeighted(pool),d=distractors(id,pool,3);
    if(Math.random()<0.5)
      return mcq("arabic",`Какая это сура: ${arSpan(SU(id).name)}?`,"Арабское → русское",id,d,
        x=>`${esc(SU(x).ru)}`,suraFact(id));
    return mcq("arabic",`Как пишется «${esc(SU(id).ru)}»?`,"Русское → арабское",id,d,
      x=>arSpan(SU(x).name),suraFact(id));
  }
  if(k==="count"){
    const id=pickWeighted(pool),su=SU(id);
    const vals=shuffle([su.n].concat(countDistractors(id,3)));
    return {kind:"count",ask:`Сколько аятов в суре «${esc(su.ru)}» ${arSpan(su.name)}?`,
      sub:"Число аятов",sura:id,
      opts:vals.map(v=>({html:String(v)})),correct:vals.indexOf(su.n),
      explain:suraFact(id)};
  }
  if(Math.random()<0.6){                          // сосед по мусхафу
    const cand=pool.filter(x=>x>=2&&x<=113);
    const id=cand.length?pickWeighted(cand):2;
    const after=Math.random()<0.5,ans=after?id+1:id-1;
    const near=[id,ans+1,ans-1,ans+2,ans-2].filter(x=>x>=1&&x<=114&&x!==ans);
    const d=shuffle([...new Set(near)]).slice(0,3);
    while(d.length<3){const x=1+rnd(114);if(x!==ans&&!d.includes(x))d.push(x);}
    return mcq("order",
      `Какая сура идёт <b>${after?"после":"перед"}</b> «${esc(SU(id).ru)}» (№${id})?`,
      "Порядок мусхафа",ans,d,x=>`${x}. ${esc(SU(x).ru)}`,
      `${after?"После":"Перед"} ${id}. ${esc(SU(id).ru)} идёт ${suraFact(ans)}`);
  }
  const base=pool.length>=4?pool:range(1,114);     // расстановка четырёх сур
  const four=shuffle(base).slice(0,4).sort((a,b)=>a-b);
  return {kind:"order",type:"sort",ask:"Расставьте суры по порядку мусхафа",
    sub:"От первой к последней",sura:four[0],
    items:shuffle(four),answer:four,
    explain:four.map(x=>`${x}. ${esc(SU(x).ru)}`).join(" · ")};
}

// ============================================================
// УПРАЖНЕНИЕ 2 — «Аяты»
// ============================================================
const AYAH_KINDS=[
  {id:"sura",ic:"📖",label:"Из какой это суры",hint:"Показан аят — выбрать суру"},
  {id:"cont",ic:"➡️",label:"Продолжить аят",hint:"Первая половина → четыре продолжения"},
  {id:"next",ic:"⏭",label:"Следующий аят",hint:"Что идёт за этим аятом"},
  {id:"word",ic:"🔤",label:"Пропущенное слово",hint:"Варианты — формы того же корня"},
];
const LANGS=[{id:"ar",label:"Арабский"},{id:"ru",label:"Перевод"},{id:"mix",label:"Вперемешку"}];
// Слова-«содержательные»: пропускать предлог или артикль бессмысленно —
// вариантов, отличимых по смыслу, для них не построить.
const CONTENT_POS=new Set(["N","PN","V","ADJ","ACT_PCPL","PASS_PCPL","VN","ADV","T","LOC"]);

let AMBIG=null;                                   // аяты, дословно повторяющиеся в разных сурах
async function loadAmbig(){
  if(AMBIG)return AMBIG;
  try{
    const r=await fetch(ctx.resolveUrl("erudit_pool",{file:"pool.json"}));
    const d=r.ok?await r.json():null;
    AMBIG=new Set((d&&d.ambiguous)||[]);
  }catch(e){AMBIG=new Set();}                     // без списка упражнение работает, просто менее строго
  return AMBIG;
}
// Данные одной суры. Перевод тянем ВСЕГДА (если он включён): даже когда вопрос
// по оригиналу, разбор после ответа обязан показать аят с переводом.
// Морфология и конкорданс — только под «пропущенное слово» (это ~1 МБ корней).
async function ensureSura(s,need){
  const tid=ctx.transId();
  const jobs=[ctx.ensureText("_arabic",s)];
  if(tid)jobs.push(ctx.ensureText(tid,s));
  let mi=-1;
  if(need.morph){mi=jobs.length;jobs.push(ctx.loadMorph(s),ctx.loadGloss(s),ctx.loadRoots());}
  const res=await Promise.all(jobs.map(p=>Promise.resolve(p).catch(()=>null)));
  return {tid,morph:mi>=0?res[mi]:null,gloss:mi>=0?res[mi+1]:null};
}
const ar=(s,a)=>ctx.getArabic(s,a);
const ru=(tid,s,a)=>tid?plain(ctx.getText(tid,s,+a)):"";
// Слова аята по КОРПУСУ: у 116 аятов разбиение _arabic по пробелам с корпусом не
// сходится (знаки вакфа, муката'ат), поэтому для пословных заданий берём формы
// из самой морфологии — там индексы верны по построению и совпадают с глоссами.
function morphWords(morph,a){
  const m=morph&&morph[String(a)];
  if(!m)return [];
  const out=[];
  for(let i=1;m[String(i)];i++)out.push(m[String(i)].map(g=>g.ar).join(""));
  return out;
}
function morphInfo(morph,a,w){
  const segs=(morph&&morph[String(a)]&&morph[String(a)][String(w)])||[];
  const stem=segs.find(g=>g.type==="stem")||segs[0]||{};
  return {root:stem.root||"",pos:stem.pos||"",lemma:stem.lemma||""};
}
// Аяты суры, годные для вида задания. Возвращаем номера, а не тексты: тексты
// длинные, а выбор ещё будет взвешенным.
function eligible(s,kind,data,ambig,wantRu){
  const su=SU(s),out=[];
  for(let a=1;a<=su.n;a++){
    const t=ar(s,a);if(!t)continue;
    const n=arWords(t).length;
    if(kind==="sura"){
      if(n<4||ambig.has(s+":"+a))continue;         // короткие и межсурные двойники — вопрос без ответа
      if(wantRu&&!ru(data.tid,s,a))continue;
    }else if(kind==="cont"){
      if(n<8)continue;                             // короче — резать нечего
      if(startsWithBasmala(t))continue;
    }else if(kind==="next"){
      if(a>=su.n)continue;                         // последний аят: переход через границу суры — другой навык
      if(!ar(s,a+1))continue;
      if(n<3||arWords(ar(s,a+1)).length<3)continue;
    }else if(kind==="word"){
      if(startsWithBasmala(t))continue;
      const w=morphWords(data.morph,a);
      if(w.length<5||w.length>28)continue;
    }
    out.push(a);
  }
  return out;
}
async function genAyahQ(c,pool,sess){
  const ambig=await loadAmbig();
  const kinds=AYAH_KINDS.filter(k=>c.kinds[k.id]).map(k=>k.id);
  const kind=kinds.length?pick(kinds):"sura";
  // «Продолжить» и «пропущенное слово» всегда по оригиналу: продолжение перевода
  // — это память о переводе, а не об аяте.
  const wantRu=(kind==="sura"||kind==="next")&&!!ctx.transId()
    &&(c.lang==="ru"||(c.lang==="mix"&&Math.random()<0.5));
  const need={morph:kind==="word"};

  // Суры пробуем по одной: если в выпавшей нет годных аятов (короткая сура для
  // «продолжить»), берём следующую, а не отдаём пустое задание.
  const tried=new Set();
  for(let attempt=0;attempt<6;attempt++){
    const left=(sess.suras||pool).filter(x=>!tried.has(x));
    if(!left.length)break;
    const s=pickWeighted(left);tried.add(s);
    const data=await ensureSura(s,need);
    const list=eligible(s,kind,data,ambig,wantRu);
    if(!list.length)continue;
    const a=pick(list);
    const q=buildAyahQ(kind,s,a,c,pool,data,wantRu);
    if(q)return q;
  }
  return null;
}
function ayahFull(s,a,tid){                        // разбор: канонический аят целиком + перевод + адрес
  const t=ru(tid,s,a);
  return `<div class="erd-ayah">${esc(ar(s,a))}</div>`
    +(t?`<div class="erd-tr">${esc(t)}</div>`:"")
    +`<div class="erd-addr">${s}:${a} · ${esc(SU(s).ru)}</div>`;
}
function buildAyahQ(kind,s,a,c,pool,data,wantRu){
  const tid=data.tid;
  const su=SU(s);
  if(kind==="sura"){
    const shown=wantRu?ru(tid,s,a):ar(s,a);
    if(!shown)return null;
    const d=distractors(s,pool,3);
    const ids=shuffle([s].concat(d));
    return {kind,sub:wantRu?"Перевод → сура":"Аят → сура",
      ask:`Из какой это суры?`,
      body:wantRu?`<div class="erd-tr big">${esc(shown)}</div>`:`<div class="erd-ayah">${esc(shown)}</div>`,
      sura:s,ayah:a,
      opts:ids.map(x=>({html:`${x}. ${esc(SU(x).ru)}`})),correct:ids.indexOf(s),
      explain:ayahFull(s,a,tid)};
  }
  if(kind==="cont"){
    const w=arWords(ar(s,a));
    const cut=Math.max(3,Math.min(w.length-3,Math.round(w.length*(0.4+Math.random()*0.2))));
    const head=w.slice(0,cut).join(" "),tail=w.slice(cut).join(" ");
    const tlen=w.length-cut;
    // Хвосты ДРУГИХ аятов той же суры сопоставимой длины: у них та же фасыля,
    // поэтому вариант не отсеивается «на слух» — нужно знать сам аят.
    const others=[];
    for(let x=1;x<=su.n&&others.length<40;x++){
      if(x===a)continue;
      const ww=arWords(ar(s,x));
      if(ww.length<tlen+2)continue;
      const t=ww.slice(Math.max(1,ww.length-tlen)).join(" ");
      if(t&&t!==tail)others.push(t);
    }
    if(others.length<3)return null;
    const opts=shuffle([tail].concat(shuffle(others).slice(0,3)));
    return {kind,sub:"Продолжите аят",ask:"Что идёт дальше?",
      body:`<div class="erd-ayah">${esc(head)} …</div>`,
      sura:s,ayah:a,
      opts:opts.map(t=>({html:`<span class="erd-ar">${esc(t)}</span>`})),correct:opts.indexOf(tail),
      explain:ayahFull(s,a,tid)};
  }
  if(kind==="next"){
    const shown=wantRu?ru(tid,s,a):ar(s,a);
    const right=wantRu?ru(tid,s,a+1):ar(s,a+1);
    if(!shown||!right)return null;
    const others=[];
    // Первый аят суры несёт басмалу — такой вариант виден сразу и подсказывает,
    // что он не «следующий». Соперники берутся рядом с показанным аятом, чтобы
    // вопрос решался памятью, а не темой.
    for(let x=Math.max(2,a-8);x<=Math.min(su.n,a+9)&&others.length<12;x++){
      if(x===a||x===a+1)continue;
      const t=wantRu?ru(tid,s,x):ar(s,x);
      if(t&&t!==right)others.push(t);
    }
    if(others.length<3)return null;
    const opts=shuffle([right].concat(shuffle(others).slice(0,3)));
    const cell=t=>wantRu?`<span>${esc(snip(t,14))}</span>`:`<span class="erd-ar">${esc(snip(t,9))}</span>`;
    return {kind,sub:"Следующий аят",ask:"Какой аят идёт следующим?",
      body:wantRu?`<div class="erd-tr big">${esc(shown)}</div>`:`<div class="erd-ayah">${esc(shown)}</div>`,
      sura:s,ayah:a+1,
      opts:opts.map(t=>({html:cell(t)})),correct:opts.indexOf(right),
      explain:ayahFull(s,a,tid)+`<div class="erd-addr">Показан был аят ${s}:${a}</div>`};
  }
  // "word" — пропущенное слово
  const words=morphWords(data.morph,a);
  if(words.length<5)return null;
  const cands=[];
  for(let i=1;i<=words.length;i++){
    const info=morphInfo(data.morph,a,i);
    if(info.root&&CONTENT_POS.has(info.pos))cands.push({i,info});
  }
  if(!cands.length)return null;
  const {i,info}=pick(cands);
  const correct=words[i-1];
  const forms=[];
  const R=ctx.getRoots&&ctx.getRoots();
  const rec=R&&R[info.root];
  if(rec&&rec.f)for(const [form] of rec.f){if(form&&form!==correct&&!forms.includes(form))forms.push(form);}
  let opts=shuffle(forms).slice(0,3);
  if(opts.length<3){                               // редкий корень: добираем словами того же аята-соседа
    for(let x=1;x<=SU(s).n&&opts.length<3;x++){
      for(const w of morphWords(data.morph,x)){
        if(w!==correct&&!opts.includes(w)&&w.length>2){opts.push(w);break;}
      }
    }
  }
  if(opts.length<3)return null;
  const all=shuffle([correct].concat(opts.slice(0,3)));
  const line=words.map((w,idx)=>idx===i-1?`<span class="erd-gap">▁▁▁</span>`:esc(w)).join(" ");
  const g=data.gloss&&data.gloss[String(a)]&&data.gloss[String(a)][String(i)];
  const gloss=g&&(g.ru||g.en)?`<div class="erd-addr">Пропущенное слово: «${esc(g.ru||g.en)}», корень ${arSpan(info.root)}</div>`:"";
  return {kind,sub:"Пропущенное слово",ask:"Какое слово пропущено?",
    body:`<div class="erd-ayah">${line}</div>`,
    sura:s,ayah:a,
    opts:all.map(w=>({html:`<span class="erd-ar">${esc(w)}</span>`})),correct:all.indexOf(correct),
    explain:ayahFull(s,a,tid)+gloss};
}

// ---------- реестр упражнений ----------
const EXERCISES=[
  {id:"suraNames",ic:"🔢",title:"Названия сур",
   about:"Номера, арабские и русские имена, число аятов и порядок сур в мусхафе.",
   kinds:SURA_KINDS,genQ:genSuraQ},
  {id:"ayahs",ic:"📖",title:"Аяты",
   about:"Узнать суру по аяту, продолжить аят, назвать следующий, вспомнить пропущенное слово.",
   kinds:AYAH_KINDS,lang:true,suraPool:12,genQ:genAyahQ},
];
const exById=id=>EXERCISES.find(x=>x.id===id);

// ============================================================
// ДВИЖОК РАУНДА
// ============================================================
function startRound(){
  const c=cfg(),ex=exById(E.ex);
  if(!Object.values(c.kinds).some(Boolean)){alert("Выберите хотя бы один вид задания.");return;}
  const pool=scopeList(c);
  // Пул СУР на раунд ограничен: аяты грузятся чанками по суре, и тянуть 114
  // чанков ради десяти вопросов незачем.
  const suras=ex.suraPool?shuffle(pool).slice(0,Math.min(ex.suraPool,pool.length)):pool;
  E.sess={pool,suras,q:null,idx:0,correct:0,streak:0,bestStreak:0,answered:null,
    wrong:[],t0:Date.now(),len:c.len,sort:[],token:0,loading:false,lastAsk:""};
  nextQ();
}
async function nextQ(){
  const s=E.sess;if(!s)return;
  if(s.len&&s.idx>=s.len){finish();return;}
  const ex=exById(E.ex);
  s.idx++;s.q=null;s.answered=null;s.sort=[];s.loading=true;
  const token=++s.token;
  E.view="round";render();
  let q=null;
  try{
    for(let i=0;i<6;i++){
      q=await ex.genQ(cfg(),s.pool,s);
      if(!q||q.ask!==s.lastAsk||q.body)break;      // не повторять вопрос подряд (у аятов тело разное всегда)
    }
  }catch(e){console.error("erudit: генератор задания:",e);}
  if(E.sess!==s||token!==s.token)return;           // раунд бросили или перезапустили, пока грузили
  s.loading=false;s.q=q;if(q)s.lastAsk=q.ask;
  render();
}
function answer(i){
  const s=E.sess;if(!s||!s.q||s.answered!==null)return;
  s.answered=i;
  recordAnswer(i===s.q.correct,s.q);
  render();
}
// Расстановка: тап ставит суру в следующую свободную позицию (повторный — снимает);
// когда все расставлены, проверяем разом — частичная проверка ничему не учит.
function sortPick(id){
  const s=E.sess;if(!s||!s.q||s.answered!==null)return;
  const at=s.sort.indexOf(id);
  if(at>=0)s.sort.splice(at,1); else s.sort.push(id);
  if(s.sort.length===s.q.items.length){
    const ok=s.sort.every((x,i)=>x===s.q.answer[i]);
    s.answered=ok?0:1;                             // для сортировки важен факт, а не индекс
    recordAnswer(ok,s.q);
  }
  render();
}
function recordAnswer(ok,q){
  const s=E.sess;
  if(ok){s.correct++;s.streak++;if(s.streak>s.bestStreak)s.bestStreak=s.streak;}
  else{s.streak=0;s.wrong.push({q});}
  const keys=q.type==="sort"?q.answer.map(String):[String(q.sura)];
  for(const key of keys){const it=itemStat(key);it.seen++;if(!ok)it.wrong++;it.ts=Date.now();}
  const st=exStat(E.ex);st.attempts++;if(ok)st.correct++;
  dbSave();
}
function finish(){
  const s=E.sess;if(!s)return;
  s.ms=Date.now()-s.t0;
  // «Без конца» подводит итог по фактически отвеченным: незавершённый вопрос,
  // на котором нажали ✕, в знаменатель не идёт.
  s.total=s.len||(s.answered===null?Math.max(0,s.idx-1):s.idx);
  const st=exStat(E.ex);
  st.plays++;st.lastTs=Date.now();
  s.record=s.correct>st.best;
  if(s.record)st.best=s.correct;
  dbSave();
  E.view="result";render();
}
// ✕ в раунде: если что-то уже отвечено — показываем итог (в режиме «без конца»
// это единственный способ его увидеть), иначе просто уходим в список.
function quitRound(){
  const s=E.sess;
  if(s&&(s.correct||s.wrong.length))finish();
  else{E.sess=null;E.view="hub";render();}
}
// «Назад» устройства: раунд/итог/настройка → список упражнений; из списка — выход из режима.
export function back(){
  if(E.view==="round"||E.view==="result"||E.view==="setup"){
    E.sess=null;E.view="hub";render();return true;
  }
  return false;
}
export function leave(){unbindKeys();E.sess=null;E.view="hub";}

// ============================================================
// ЭКРАНЫ
// ============================================================
export function enterMode(){
  db();E.view="hub";E.sess=null;E.ex=null;
  render();
}
export function render(){
  const el=document.getElementById("erdBody");
  if(!el)return;
  el.innerHTML=E.view==="hub"?hubHTML():E.view==="setup"?setupHTML():
              E.view==="round"?roundHTML():resultHTML();
  bindOnce();
  if(E.view==="round")bindKeys();else unbindKeys();
}

function hubHTML(){
  let h=`<div class="erd-head"><div class="erd-h1">🎓 Эрудит</div>
    <div class="erd-lead">Занимательные упражнения: узнавать суры, аяты и темы Корана. Результат не идёт в зачёт цели чтения — это тренировка.</div></div>`;
  for(const ex of EXERCISES){
    const st=exStat(ex.id);
    const acc=st.attempts?`${pct(st.correct,st.attempts)}% верных`:"ещё не проходили";
    h+=`<div class="erd-card" data-act="open" data-ex="${ex.id}">
      <div class="erd-card-h"><span class="erd-ic">${ex.ic}</span><span class="erd-card-t">${esc(ex.title)}</span><span class="erd-arrow">›</span></div>
      <div class="erd-card-s">${esc(ex.about)}</div>
      <div class="erd-card-m">${st.plays?`рекорд ${st.best} · ${acc} · ${st.plays} ${plural(st.plays,"подход","подхода","подходов")}`:"новое упражнение"}</div>
    </div>`;
  }
  h+=`<div class="erd-soon"><b>Скоро:</b> аят по теме · расставить аяты по порядку · «Лестница знания» (вопросы по Корану и тафсиру).</div>`;
  return h;
}

function setupHTML(){
  const ex=exById(E.ex),c=cfg();
  const bad=c.scope==="custom"?parseSuras(c.custom).bad:[];
  const n=scopeList(c).length;
  let h=`<div class="erd-back" data-act="hub">‹ К упражнениям</div>
    <div class="erd-h1">${ex.ic} ${esc(ex.title)}</div>`;
  h+=`<div class="erd-set"><div class="erd-set-h">Охват</div><div class="erd-chips">`;
  for(const sc of SCOPES)
    h+=`<button class="erd-chip${c.scope===sc.id?" on":""}" data-act="scope" data-v="${sc.id}">${esc(sc.label)}<small>${esc(sc.sub)}</small></button>`;
  h+=`</div>`;
  if(c.scope==="custom")
    h+=`<input class="erd-inp" value="${ctx.escAttr(c.custom)}" placeholder="78-114, 36, 55" data-act="custom">
      ${bad.length?`<div class="erd-bad">Не понял: ${esc(bad.join(", "))}</div>`:""}`;
  h+=`<div class="erd-note">${n} ${plural(n,"сура","суры","сур")} в охвате${ex.suraPool&&n>ex.suraPool?` · в раунде — ${ex.suraPool} случайных из них`:""}</div></div>`;

  h+=`<div class="erd-set"><div class="erd-set-h">Сколько заданий</div><div class="erd-chips">`;
  for(const L of [10,20,40,0])
    h+=`<button class="erd-chip${c.len===L?" on":""}" data-act="len" data-v="${L}">${L||"без конца"}</button>`;
  h+=`</div></div>`;

  if(ex.lang){
    const tid=ctx.transId(),tn=tid?ctx.transName(tid):"";
    h+=`<div class="erd-set"><div class="erd-set-h">Как показывать аят</div><div class="erd-chips">`;
    for(const L of LANGS)
      h+=`<button class="erd-chip${c.lang===L.id?" on":""}" data-act="lang" data-v="${L.id}">${esc(L.label)}</button>`;
    h+=`</div><div class="erd-note">${tn?`Перевод: ${esc(tn)}`:"Перевод не включён — задания будут по оригиналу"}. «Продолжить аят» и «пропущенное слово» всегда по оригиналу.</div></div>`;
  }

  h+=`<div class="erd-set"><div class="erd-set-h">Виды заданий</div>`;
  for(const k of ex.kinds)
    h+=`<label class="erd-kind"><input type="checkbox" data-act="kind" data-v="${k.id}"${c.kinds[k.id]?" checked":""}>
      <span class="erd-kind-t">${k.ic} ${esc(k.label)}</span><span class="erd-kind-h">${esc(k.hint)}</span></label>`;
  h+=`</div>`;
  h+=`<button class="erd-start" data-act="start">Начать ›</button>`;
  return h;
}

function roundHTML(){
  const s=E.sess,q=s.q;
  const total=s.len||0;
  const prog=total?Math.round((s.idx-1)*100/total):0;
  let h=`<div class="erd-top">
      <span class="erd-count">${s.idx}${total?" / "+total:""}</span>
      <span class="erd-score">✓ ${s.correct}</span>
      ${s.streak>1?`<span class="erd-streak">🔥 ${s.streak}</span>`:""}
      <button class="erd-quit" data-act="quit" title="Выйти из раунда">✕</button>
    </div>
    <div class="erd-prog"><i style="width:${prog}%"></i></div>`;
  if(s.loading)return h+`<div class="erd-note" style="padding:26px 0;text-align:center">Готовлю задание…</div>`;
  if(!q)return h+`<div class="erd-note" style="padding:22px 0;text-align:center">Не удалось составить задание по этому охвату.</div>
    <button class="erd-start" data-act="next">Попробовать другое ›</button>
    <button class="erd-start ghost" data-act="setup">Изменить настройки</button>`;

  h+=`<div class="erd-q"><div class="erd-q-sub">${esc(q.sub)}</div><div class="erd-q-ask">${q.ask}</div>${q.body||""}</div>`;

  if(q.type==="sort"){
    h+=`<div class="erd-sortline">`;
    for(let i=0;i<q.items.length;i++){
      const id=s.sort[i];
      h+=`<span class="erd-slot${id?" full":""}">${id?esc(SU(id).ru):i+1}</span>`;
    }
    h+=`</div><div class="erd-opts">`;
    for(const id of q.items){
      const at=s.sort.indexOf(id),done=s.answered!==null;
      const okPos=done&&q.answer[at]===id;
      h+=`<button class="erd-opt${at>=0?" chosen":""}${done?(okPos?" ok":" bad"):""}" data-act="sort" data-v="${id}"${done?" disabled":""}>
        ${at>=0?`<span class="erd-pos">${at+1}</span>`:""}${esc(SU(id).ru)} <span class="erd-ar">${esc(SU(id).name)}</span></button>`;
    }
    h+=`</div>`;
  }else{
    h+=`<div class="erd-opts">`;
    for(let i=0;i<q.opts.length;i++){
      const done=s.answered!==null;
      const cls=done?(i===q.correct?" ok":(i===s.answered?" bad":" dim")):"";
      h+=`<button class="erd-opt${cls}" data-act="ans" data-v="${i}"${done?" disabled":""}>
        <span class="erd-num">${i+1}</span>${q.opts[i].html}</button>`;
    }
    h+=`</div>`;
  }

  if(s.answered!==null){
    const ok=q.type==="sort"?s.answered===0:s.answered===q.correct;
    h+=`<div class="erd-fb ${ok?"ok":"bad"}">
      <div class="erd-fb-t">${ok?"✓ Верно":"✕ Мимо"}</div>
      <div class="erd-fb-x">${q.explain}</div>
      ${q.sura?`<button class="erd-link" data-act="go" data-v="${q.sura}" data-a="${q.ayah||1}">Открыть ${q.sura}${q.ayah?":"+q.ayah:""} ›</button>`:""}
    </div>
    <button class="erd-start" data-act="next">${(s.len&&s.idx>=s.len)?"Итог ›":"Дальше ›"}</button>`;
  }
  return h;
}

function resultHTML(){
  const s=E.sess,st=exStat(E.ex);
  const p=pct(s.correct,s.total||s.idx);
  const mood=p>=90?"🌟":p>=70?"👍":p>=50?"🙂":"📚";
  let h=`<div class="erd-res">
    <div class="erd-res-ic">${mood}</div>
    <div class="erd-res-score">${s.correct} / ${s.total||s.idx}</div>
    <div class="erd-res-sub">${p}% верных · ${mmss(s.ms)} · лучшая серия ${s.bestStreak}</div>
    ${s.record?`<div class="erd-record">Новый личный рекорд!</div>`:`<div class="erd-note">Рекорд: ${st.best}</div>`}
  </div>`;
  if(s.wrong.length){
    h+=`<div class="erd-set"><div class="erd-set-h">Разобрать ошибки (${s.wrong.length})</div>`;
    for(const w of s.wrong)
      h+=`<div class="erd-wrong"><div class="erd-wrong-q">${w.q.ask}</div>
        <div class="erd-wrong-a">${w.q.explain}</div>
        ${w.q.sura?`<button class="erd-link" data-act="go" data-v="${w.q.sura}" data-a="${w.q.ayah||1}">Открыть ${w.q.sura}${w.q.ayah?":"+w.q.ayah:""} ›</button>`:""}</div>`;
    h+=`</div>`;
  }else h+=`<div class="erd-note" style="text-align:center">Ни одной ошибки, ма ша Аллах.</div>`;
  h+=`<button class="erd-start" data-act="again">Ещё раз</button>
    <button class="erd-start ghost" data-act="setup">Изменить настройки</button>
    <button class="erd-back" data-act="hub" style="text-align:center">‹ К упражнениям</button>`;
  return h;
}

// ============================================================
// СОБЫТИЯ (делегирование: у ES-модуля нет доступа к inline-onclick)
// ============================================================
// Обработчики висят на #erdBody. Экран режима пересоздаётся (renderCenter →
// innerHTML), поэтому сверяемся с САМИМ узлом, а не с флагом: иначе после
// перерисовки центра клики уходили бы в никуда.
let _boundHost=null;
function bindOnce(){
  const host=document.getElementById("erdBody");
  if(!host||_boundHost===host)return;
  _boundHost=host;
  host.addEventListener("click",onClick);
  host.addEventListener("change",onChange);
  host.addEventListener("input",onInput);
}
function onClick(e){
  const t=e.target.closest("[data-act]");
  if(!t)return;
  const act=t.dataset.act,v=t.dataset.v;
  if(act==="open"){E.ex=t.dataset.ex;E.view="setup";render();}
  else if(act==="hub"){E.sess=null;E.view="hub";render();}
  else if(act==="setup"){E.view="setup";render();}
  else if(act==="scope"){cfg().scope=v;dbSave();render();}
  else if(act==="len"){cfg().len=+v;dbSave();render();}
  else if(act==="lang"){cfg().lang=v;dbSave();render();}
  else if(act==="start"||act==="again"){startRound();}
  else if(act==="ans"){answer(+v);}
  else if(act==="sort"){sortPick(+v);}
  else if(act==="next"){nextQ();}
  else if(act==="quit"){quitRound();}
  else if(act==="go"){const a=+(t.dataset.a||0);if(a>1&&ctx.goAyah)ctx.goAyah(+v,a);else ctx.goSurah(+v);}
}
function onChange(e){
  const t=e.target.closest("[data-act='kind']");
  if(!t)return;
  cfg().kinds[t.dataset.v]=t.checked;dbSave();
}
// Ввод своих сур: сохраняем без перерисовки — иначе поле теряет фокус на каждом
// символе (та же грабля, что в поиске по корням).
let _customT=null;
function onInput(e){
  const t=e.target.closest("[data-act='custom']");
  if(!t)return;
  cfg().custom=t.value;dbSave();
  clearTimeout(_customT);
  _customT=setTimeout(()=>{const n=scopeList(cfg()).length;
    const note=document.querySelector("#erdBody .erd-note");
    if(note)note.textContent=`${n} ${plural(n,"сура","суры","сур")} в охвате`;},400);
}
// Клавиатура: 1–4 — вариант, Enter/пробел — дальше.
function onKey(e){
  // Из режима можно уйти минуя leave() (goSurah, deep-link, «Назад»): сверяемся
  // с флагом режима, иначе цифры продолжали бы отвечать на невидимый вопрос.
  if(!ctx.ST.eruditMode){unbindKeys();return;}
  const s=E.sess;if(!s||E.view!=="round"||!s.q)return;
  if(e.key==="Enter"||e.key===" "){
    if(s.answered!==null){e.preventDefault();nextQ();}
    return;
  }
  const n=parseInt(e.key,10);
  if(n>=1&&n<=9){
    if(s.answered!==null)return;
    if(s.q.type==="sort"){const id=s.q.items[n-1];if(id)sortPick(id);}
    else if(n<=s.q.opts.length)answer(n-1);
  }
}
let _keysOn=false;
function bindKeys(){if(_keysOn)return;document.addEventListener("keydown",onKey);_keysOn=true;}
function unbindKeys(){if(!_keysOn)return;document.removeEventListener("keydown",onKey);_keysOn=false;}
