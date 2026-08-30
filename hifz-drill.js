// ============================================================
// МОДУЛЬ «📿 СТАНОК ЗАУЧИВАНИЯ» (талькын)
// ============================================================
// ES-модуль. Грузится ЛЕНИВО из index.html (drillMod() → import("./hifz-drill.js")):
// пока пользователь не открыл станок — ни байта этого кода.
// Матчасть, модель и каталог методов — HIFZ_METHODS.md (источник истины).
//
// АРХИТЕКТУРА. Всё различие между двумя десятками методик хифза живёт в СБОРКЕ
// программы и больше нигде. Программа собирается ЗАРАНЕЕ и ЦЕЛИКОМ — плоским
// списком АТОМОВ; плеер после этого тупой: взял атом → показал → тап → следующий.
// Он не знает ни про «джам'», ни про Пимслера, ни про плетение.
//
//   СЕГМЕНТ  {s,a,w0,w1} — слова аята, w1 включительно, индексы КОНКРЕТНЫЕ
//            (разрешаются при сборке, когда текст уже загружен).
//   ПОРЦИЯ   массив сегментов. Через неё выражается ВСЁ: аят целиком, кусок по
//            вакфу, нахлёст [аят N + 3 слова N+1], голый шов, связка четырёх.
//   АТОМ     {chunk, show, i, of} — одна порция, один раз, один режим показа.
//   ПРОГРАММА  плоский список атомов.
//
// КОНВЕЙЕР (§4.3 HIFZ_METHODS.md) — семь чистых функций, каждая берёт список и
// возвращает список:
//   охват → cut → seam → order → reps → link → spacing → passes → программа
// Новый метод = новая строчка в PRESETS, а не новая ветка в плеере.
//
// ПЕРЕКЛЮЧАТЕЛИ ПОВЕРХ (pace/veil/channel) в программу НЕ запекаются: они
// меняют только подачу атома и потому крутятся на ходу, без пересборки.
// Поэтому вуаль вычисляется в showOf() при показе, а не в expand().
//
// Связь с приложением — ТОЛЬКО через ctx из index.html. Разметка рисуется в
// собственный оверлей, клики — ОДИН делегированный обработчик по data-act
// (inline-onclick недоступен: у модуля своя область видимости).

let ctx=null;
export function init(c){ctx=c;}
const esc=s=>ctx.esc(String(s==null?"":s));

// ---------- мелочи ----------
function mulberry32(a){return function(){a|=0;a=a+0x6D2B79F5|0;let t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}
function shuffle(arr,rnd){const x=arr.slice();for(let i=x.length-1;i>0;i--){const j=Math.floor(rnd()*(i+1));const t=x[i];x[i]=x[j];x[j]=t;}return x;}
const SU=id=>ctx.SURAHS[id-1];
function plural(n,one,few,many){const m10=n%10,m100=n%100;if(m10===1&&m100!==11)return one;if(m10>=2&&m10<=4&&(m100<10||m100>=20))return few;return many;}
function mmss(sec){const s=Math.max(0,Math.round(sec));return Math.floor(s/60)+" мин "+(s%60)+" сек";}

// ============================================================
// ТЕКСТ И СЛОВА
// ============================================================
// Знаки вакфа стоят в тексте ОТДЕЛЬНЫМИ токенами (ٱلْقَيُّومُ ۚ لَا) — словами они не
// являются и в нумерацию не идут, иначе индексы разъедутся с корпусом (s:a:w).
// Но их МЕСТА запоминаем: по ним режет unit "wakf".
const PAUSE=/^[ۖ-ۭؕ-ؚ࣢]+$/;

const W={};                                    // vk → {words:[], pause:Set, bas:string|null}
function wordsOf(vk){return W[vk];}

async function loadWords(vks){
  const suras=[...new Set(vks.map(v=>+v.split(":")[0]))];
  for(const s of suras){try{await ctx.ensureText("_arabic",s);}catch(e){}}
  for(const vk of vks){
    if(W[vk])continue;
    const [s,a]=vk.split(":").map(Number);
    let t=ctx.getArabic(s,a)||"";
    // Басмала у первого аята суры ПРИКЛЕЕНА к тексту. Частью аята её не считают
    // ни корпус, ни перевод, ни таджвид — здесь тоже отрезаем: иначе вуаль
    // гасила бы басмалу, а нумерация слов разошлась бы с корпусом. Показываем
    // её отдельной приглушённой строкой (см. renderRun).
    let bas=null;
    const c=ctx.cutBasmala(t,s,a);
    if(c){bas=c.bas;t=c.rest;}
    const toks=String(t).split(/\s+/).filter(Boolean);
    const words=[],pause=new Set();
    for(const tk of toks){
      if(PAUSE.test(tk)){if(words.length)pause.add(words.length-1);continue;}  // пауза ПОСЛЕ слова words.length-1
      words.push(tk);
    }
    W[vk]={words,pause,bas};
  }
}

// ============================================================
// ПОРЦИИ
// ============================================================
const seg=(s,a,w0,w1)=>({s,a,w0,w1});
const vkOf=g=>g.s+":"+g.a;
function segWords(g){const w=wordsOf(vkOf(g));return w?w.words.slice(g.w0,g.w1+1):[];}
function chunkLen(ch){return ch.reduce((n,g)=>n+(g.w1-g.w0+1),0);}
function chunkKey(ch){return ch.map(g=>g.s+":"+g.a+":"+g.w0+"-"+g.w1).join("|");}
function isWhole(g){const w=wordsOf(vkOf(g));return w&&g.w0===0&&g.w1===w.words.length-1;}

// Человеческий адрес порции: «78:1», «78:1–4», «78:1 → 2» (шов), «78:1 +2 сл.»
function chunkLabel(ch){
  if(!ch.length)return "";
  const first=ch[0],last=ch[ch.length-1];
  if(ch.length===1)return isWhole(first)?first.s+":"+first.a:first.s+":"+first.a+" (часть)";
  const ayahs=[...new Set(ch.map(g=>g.a))];
  const allWhole=ch.every(isWhole);
  if(allWhole)return first.s+":"+ayahs[0]+"–"+ayahs[ayahs.length-1];
  if(ch.length===2&&!isWhole(first)&&!isWhole(last))return first.s+":"+first.a+" → "+last.a+" (шов)";
  if(isWhole(first)&&!isWhole(last))return first.s+":"+first.a+" +"+chunkLen([last])+" сл.";
  return first.s+":"+ayahs[0]+"–"+ayahs[ayahs.length-1];
}

// ============================================================
// КОНВЕЙЕР — 1. РЕЗКА
// ============================================================
// Соседние отрезки одного аята сливаем: строка может резать аят посередине, а
// на полустранице его половинки снова оказываются рядом — двумя кусками они
// произносились бы с разрывом там, где разрыва нет.
function joinSegs(segs){
  const out=[];
  for(const g of segs){
    const p=out[out.length-1];
    if(p&&p.s===g.s&&p.a===g.a&&p.w1+1===g.w0)p.w1=g.w1;
    else out.push({s:g.s,a:g.a,w0:g.w0,w1:g.w1});
  }
  return out;
}
function cut(vks,unit){
  const out=[];
  // Страница мусхафа как порция. Границы берём у общего отображения аят→страница
  // (то же, что у карты покрытия), поэтому «страница» здесь — ровно та бумага,
  // что человек видит в режиме «Мусхаф», а не выдуманное окно в N аятов.
  if(unit.kind==="page"&&ctx.pageOf){
    let cur=null,grp=[];
    for(const vk of vks){
      const [s,a]=vk.split(":").map(Number);
      const w=wordsOf(vk);if(!w||!w.words.length)continue;
      let pg=null;try{pg=ctx.pageOf(s,a);}catch(e){}
      if(pg!==cur&&grp.length){out.push(grp);grp=[];}
      cur=pg;grp.push(seg(s,a,0,w.words.length-1));
    }
    if(grp.length)out.push(grp);
    return out.length?out:cut(vks,{kind:"ayah"});   // мета не загрузилась — не падаем
  }
  // Строка мусхафа как порция. Прямой связи «строка → аят» в данных QPC нет —
  // она выведена сопоставлением глифов (build_qpc_lines.py). Здесь остаётся
  // только пересечь строки с охватом: чужие аяты со строки выбрасываем.
  if((unit.kind==="line"||unit.kind==="halfpage")&&ctx.pageLines&&ctx.pageOf){
    const want=new Set(vks),pages=[];
    for(const vk of vks){
      const [sn,an]=vk.split(":").map(Number);
      let pg=null;try{pg=ctx.pageOf(sn,an);}catch(e){}
      if(pg&&pages[pages.length-1]!==pg)pages.push(pg);
    }
    const res=[];
    for(const pg of pages){
      const L=ctx.pageLines(pg);if(!L)continue;
      const chunks=[];
      for(const ln of Object.keys(L).sort((x,y)=>x-y)){
        const segs=[];
        for(const it of L[ln]){
          const vk=it[0]+":"+it[1];
          if(!want.has(vk))continue;
          const w=wordsOf(vk);if(!w||!w.words.length)continue;
          const last=w.words.length-1;
          segs.push(seg(it[0],it[1],Math.min(it[2],last),Math.min(it[3],last)));
        }
        if(segs.length)chunks.push(joinSegs(segs));
      }
      if(unit.kind==="halfpage"&&chunks.length>1){
        const mid=Math.ceil(chunks.length/2);
        const flat=arr=>joinSegs(arr.reduce((acc,c)=>acc.concat(c),[]));
        res.push(flat(chunks.slice(0,mid)));
        const rest=chunks.slice(mid);
        if(rest.length)res.push(flat(rest));
      }else res.push(...chunks);
    }
    return res.length?res:cut(vks,{kind:"ayah"});   // данные не загрузились — не падаем
  }
  if(unit.kind==="block"){                     // весь охват одной порцией (для проходов)
    out.push(vks.map(vk=>{const [s,a]=vk.split(":").map(Number);const w=wordsOf(vk);return seg(s,a,0,w.words.length-1);}));
    return out;
  }
  for(const vk of vks){
    const [s,a]=vk.split(":").map(Number);
    const w=wordsOf(vk);if(!w||!w.words.length)continue;
    const n=w.words.length;
    if(unit.kind==="wakf"&&n>(unit.maxWords||25)&&w.pause.size){
      // Режем по знакам остановки, но НЕ мельче maxWords/3: иначе длинный аят
      // рассыпается на огрызки по два слова, которые нечего заучивать.
      const min=Math.max(3,Math.round((unit.maxWords||25)/3));
      let from=0;
      for(let i=0;i<n;i++){
        if(!w.pause.has(i))continue;
        if(i-from+1<min)continue;
        out.push([seg(s,a,from,i)]);from=i+1;
      }
      if(from<n)out.push([seg(s,a,from,n-1)]);
    }else out.push([seg(s,a,0,n-1)]);
  }
  return out;
}

// ============================================================
// КОНВЕЙЕР — 2. СТЫКОВКА (швы, §5 HIFZ_METHODS.md)
// ============================================================
// Работает ПОСЛЕ резки и меняет границы уже нарезанных порций — поэтому
// нахлёст сочетается с любой резкой. Порции здесь ещё в порядке текста, значит
// соседи по массиву — соседи по тексту, отдельная проверка смежности не нужна.
function head(ch,k){const g=ch[0];return seg(g.s,g.a,g.w0,Math.min(g.w1,g.w0+k-1));}
function tail(ch,k){const g=ch[ch.length-1];return seg(g.s,g.a,Math.max(g.w0,g.w1-k+1),g.w1);}

function applySeam(chunks,seam){
  const k=Math.max(1,seam.k||3);
  if(!seam.kind||seam.kind==="none")return chunks;
  if(seam.kind==="only"){                      // голые швы: хвост N + голова N+1
    const out=[];
    for(let i=0;i+1<chunks.length;i++)out.push([tail(chunks[i],k),head(chunks[i+1],k)]);
    return out;
  }
  return chunks.map((ch,i)=>{
    let out=ch.slice();
    if((seam.kind==="back"||seam.kind==="both")&&i>0)out=[tail(chunks[i-1],k),...out];
    if((seam.kind==="fwd"||seam.kind==="both")&&i+1<chunks.length)out=[...out,head(chunks[i+1],k)];
    return out;
  });
}

// ============================================================
// КОНВЕЙЕР — 3. ПОРЯДОК
// ============================================================
function applyOrder(chunks,order,rnd){
  if(!order||order.kind==="forward")return chunks;
  if(order.kind==="reverse")return chunks.slice().reverse();
  if(order.kind==="shuffle")return shuffle(chunks,rnd);
  return chunks;                               // bottomup/ottoman — нужны данные страниц, см. §7.5
}

// ============================================================
// КОНВЕЙЕР — 4. ПОВТОРЫ
// ============================================================
// show: "text" (виден) | "blind" (по памяти) | число 0..1 (доля скрытых слов).
// Схема задаётся либо явным узором (6446), либо однородно ({n,show}).
function repShows(reps){
  if(reps.pattern)return reps.pattern.slice();
  const n=Math.max(1,reps.n||5);
  if(reps.show==="fade"){                      // ровная лесенка: текст → … → память
    const out=[];
    for(let i=0;i<n;i++)out.push(i===0?"text":(i===n-1?"blind":(i/(n-1))));
    return out;
  }
  return Array.from({length:n},()=>reps.show||"text");
}
function makeSteps(chunks,reps){
  return chunks.map(ch=>({chunk:ch,shows:repShows(reps),link:false}));
}

// ============================================================
// КОНВЕЙЕР — 5. СВЯЗЫВАНИЕ
// ============================================================
// Вставляет ДОПОЛНИТЕЛЬНЫЕ шаги-связки, исходные не трогает. Снежный ком,
// крама (скользящие пары) и джата (вперёд-назад-вперёд) отличаются только тем,
// какие связки вставлены и в каком порядке.
// ИНВАРИАНТ КАНОНИЧЕСКОГО ПОРЯДКА (обожглись 2026-08-29): внутри ОДНОЙ
// произносимой порции сегменты обязаны идти в порядке текста. Ведическая джата
// гоняет текст вперёд-назад-вперёд, и я перенёс это буквально — получилась
// цепочка «аят 2 → аят 1» как единое произнесение. Для Корана это недопустимо:
// порядок аята — часть текста, а не приём тренировки.
// Что от джаты остаётся законно: с КАКОГО куска начать (обратная сборка) и
// сколько раз вернуться к шву. Что нельзя: произнести кусок задом наперёд.
function mergeChunks(list){
  const out=[];for(const ch of list)for(const g of ch)out.push(g);
  for(let i=1;i<out.length;i++){
    const p=out[i-1],c=out[i];
    if(c.s<p.s||(c.s===p.s&&(c.a<p.a||(c.a===p.a&&c.w0<p.w0))))
      throw new Error("порция вне канонического порядка: "+p.s+":"+p.a+" → "+c.s+":"+c.a);
  }
  return out;
}

// Связка ПРОИЗНОСИТСЯ по тексту, даже если порции изучаются в другом порядке
// (обожглись 2026-08-29): пресет «с конца блока» ставит order:reverse, снежный
// ком склеивал соседей по УЖЕ ПЕРЕВЁРНУТОМУ массиву и выдавал «78:5 → 78:4»
// одним произнесением — инвариант канонического порядка отловил это на сборке.
// Порядок ИЗУЧЕНИЯ и порядок ПРОИЗНЕСЕНИЯ — разные вещи; здесь второй.
function ordKey(ch){const g=ch[0];return g.s*1e6+g.a*1e3+g.w0;}
function orderedMerge(list){return mergeChunks(list.slice().sort((a,b)=>ordKey(a)-ordKey(b)));}

function applyLink(steps,link){
  if(!link||link.kind==="none"||steps.length<2)return steps;
  const R=Math.max(1,link.reps||3);
  const mk=chunk=>({chunk,shows:Array.from({length:R},()=>"text"),link:true});
  const out=[];

  if(link.kind==="snowball"){
    const every=Math.max(2,link.every||4);
    for(let i=0;i<steps.length;i++){
      out.push(steps[i]);
      const done=i+1;
      if(done%every===0||i===steps.length-1){
        const from=link.cum?0:Math.max(0,done-every);
        const grp=steps.slice(from,done).map(s=>s.chunk);
        if(grp.length>1)out.push(mk(orderedMerge(grp)));
      }
    }
    // Финальная связка всего блока — если она не совпала с последней групповой.
    if(steps.length>2){
      const all=orderedMerge(steps.map(s=>s.chunk));
      const lastCh=out[out.length-1];
      if(!lastCh.link||chunkKey(lastCh.chunk)!==chunkKey(all))out.push(mk(all));
    }
    return out;
  }

  if(link.kind==="krama"){                     // скользящие пары: 12 · 23 · 34
    for(let i=0;i<steps.length;i++){
      out.push(steps[i]);
      if(i+1<steps.length)out.push(mk(orderedMerge([steps[i].chunk,steps[i+1].chunk])));
    }
    return out;
  }

  if(link.kind==="weave"){                     // возврат к шву: 12 · 23 · 12 · 34 · 23 …
    // От ведической джаты берём то, что переносится: к каждому шву возвращаются
    // НЕСКОЛЬКО раз, вперемешку с соседними. Разворот последовательности не
    // берём — см. инвариант у mergeChunks.
    for(let i=0;i<steps.length;i++){
      out.push(steps[i]);
      if(i+1<steps.length)out.push(mk(orderedMerge([steps[i].chunk,steps[i+1].chunk])));
      if(i>0&&i+1<steps.length)out.push(mk(orderedMerge([steps[i-1].chunk,steps[i].chunk])));
    }
    return out;
  }

  if(link.kind==="backward"){                  // обратная сборка: D · CD · BCD · ABCD
    // Каждое произнесение — канонический порядок; меняется лишь то, С ЧЕГО
    // начинают собирать. Хвост блока получает больше всего повторов и перестаёт
    // быть слабым местом («начало помню, конец плаваю»). Приём актёров
    // (backward chaining) и профиль «сборка с конца» у Codex.
    for(let i=steps.length-1;i>=0;i--){
      out.push(steps[i]);
      if(i<steps.length-1)out.push(mk(orderedMerge(steps.slice(i).map(s2=>s2.chunk))));
    }
    return out;
  }
  return steps;
}

// ============================================================
// КОНВЕЙЕР — 6. РАСПИСАНИЕ
// ============================================================
// Единственное место, где повторы могут разъехаться. massed — всё подряд;
// expanding — повторы порции раскидываются с растущими промежутками, а в
// промежутки попадают атомы ДРУГИХ порций (шкала Пимслера, но в атомах, а не в
// секундах: секунды в станке не измеряются, темп задаёт человек).
function expand(steps,spacing){
  const atoms=[];
  // Поля ШАГА переносим в атом поимённо. Раньше здесь терялся fix («ремонт шва»
  // не подписывался на экране, хотя стадия работала); на нём же споткнулась и
  // пара муташабихат. Добавляешь поле шагу — добавь его и сюда.
  const mkAtom=(st,j,id)=>({chunk:st.chunk,show:st.shows[j],i:j,of:st.shows.length,
    link:!!st.link,step:id,fix:!!st.fix,tw:st.tw||null});
  if(!spacing||spacing.kind!=="expanding"){
    steps.forEach((st,id)=>{for(let j=0;j<st.shows.length;j++)atoms.push(mkAtom(st,j,id));});
    return atoms;
  }
  const gaps=(spacing.gaps&&spacing.gaps.length?spacing.gaps:[1,2,4,8,16]);
  const slot=[];                               // разреженный массив позиций
  const put=(p,at)=>{let i=Math.max(0,Math.round(p));while(slot[i])i++;slot[i]=at;return i;};
  steps.forEach((st,id)=>{
    let pos=id;                                // первый повтор — на своём месте в очереди
    for(let j=0;j<st.shows.length;j++){
      if(j>0)pos+=gaps[Math.min(j-1,gaps.length-1)];
      pos=put(pos,mkAtom(st,j,id));
    }
  });
  for(let i=0;i<slot.length;i++)if(slot[i])atoms.push(slot[i]);
  return atoms;
}

// ============================================================
// КОНВЕЙЕР — 0. ДИАГНОСТИКА
// ============================================================
// Швы, которые человек уже проваливал на проверке 🎯, лечатся ДО урока, а не
// после. Данные о них копятся в hifz.junctions с 2026-07 и до сих пор никем не
// читались — это их первый потребитель.
// Стадия именно НУЛЕВАЯ: она не меняет основную программу, а приставляет к ней
// короткий ремонтный блок спереди. Метод при этом любой — лечение не зависит
// от того, каким пресетом пойдёт основной урок.
function weakJunctions(vks,diag){
  if(!diag||diag.inject===false||!ctx.junctions)return [];
  let J=null;try{J=ctx.junctions();}catch(e){}
  if(!J)return [];
  const inScope=new Set(vks),out=[];
  for(const jk in J){
    const r=J[jk];if(!r||r.last==null||r.last>1)continue;   // 0 «не помню» и 1 «с трудом»
    const [a,b]=jk.split(">");
    if(!inScope.has(a)||!inScope.has(b))continue;
    out.push({a,b,grade:r.last,up:r.up||""});
  }
  // Сначала самые провальные, при равенстве — те, что дольше не трогали.
  out.sort((x,y)=>x.grade-y.grade||String(x.up).localeCompare(String(y.up)));
  return out.slice(0,Math.max(1,diag.max||3));
}
function diagnosticSteps(vks,cfg){
  const weak=weakJunctions(vks,cfg.diagnostics);
  if(!weak.length)return [];
  const k=Math.max(1,(cfg.seam&&cfg.seam.k)||3);
  const steps=[];
  for(const w of weak){
    const [s1,a1]=w.a.split(":").map(Number),[s2,a2]=w.b.split(":").map(Number);
    const w1=wordsOf(w.a),w2=wordsOf(w.b);
    if(!w1||!w2)continue;
    const chunk=[seg(s1,a1,Math.max(0,w1.words.length-k),w1.words.length-1),
                 seg(s2,a2,0,Math.min(k-1,w2.words.length-1))];
    steps.push({chunk,shows:["text","text","blind"],link:false,fix:true});
  }
  return expand(steps,{kind:"massed"});
}

// ── МУТАШАБИХАТ: ПАРНЫЙ ШАГ ──────────────────────────────────────────────
// Место, на котором сбивается заучивший, — не сам аят, а РАЗВИЛКА между ним и
// его двойником из другой суры. Поэтому близнецов ставим рядом и заставляем
// назвать различие вслух, а не перечитывать аят ещё раз.
// Данные общие с 🎓 Эрудитом (build_erudit_pool.py, 72 группы).

// Сравнивать надо по костяку: у близнецов расходятся слова, а не огласовки,
// и лишний фатх не должен подсвечиваться как различие.
const DIAC=/[\u064B-\u0652\u0670\u0640\u0656-\u065F\u06D6-\u06ED\u08F0-\u08FF]/g;
const normW=w=>String(w).replace(DIAC,"");
// Наибольшая общая подпоследовательность: помечаем ТОЛЬКО то, что не совпало.
// Позиционного сравнения мало — у близнецов бывает вставлено или выпало слово,
// и дальше всё поехало бы, подсветив аят целиком.
function diffFlags(a,b){
  const A=a.map(normW),B=b.map(normW),n=A.length,m=B.length;
  const dp=[];for(let i=0;i<=n;i++)dp.push(new Uint16Array(m+1));
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)
    dp[i][j]=A[i]===B[j]?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);
  const fa=new Array(n).fill(true),fb=new Array(m).fill(true);
  let i=0,j=0;
  while(i<n&&j<m){
    if(A[i]===B[j]){fa[i]=false;fb[j]=false;i++;j++;}
    else if(dp[i+1][j]>=dp[i][j+1])i++;else j++;
  }
  return [fa,fb];
}
// Пары «твой аят + двойник». За каждой парой сразу идёт заход ПО ПАМЯТИ:
// инвариант 2 — последовательность не имеет права кончиться на подсказке.
// Двойник из ДРУГОЙ суры ценнее: путают именно «из какой суры этот аят».
// Внутри одной суры («وَيْلٌ يَوْمَئِذٍ لِّلْمُكَذِّبِينَ» в 77-й десять раз) развилка
// не в словах, а в месте — такую пару берём только если другой нет.
const prevVk=vk=>{const [sn,an]=vk.split(":").map(Number);return an>1?sn+":"+(an-1):null;};
function twinOrder(vk){
  const sn=+vk.split(":")[0];
  let tw=[];try{tw=ctx.mutTwins(vk)||[];}catch(e){}
  return tw.slice().sort((a,b)=>(+a.split(":")[0]===sn?1:0)-(+b.split(":")[0]===sn?1:0));
}
function twinSteps(vks,cfg){
  const t=cfg.twins;
  if(!t||!ctx.mutTwins)return [];
  const steps=[];
  for(const vk of vks){
    const other=twinOrder(vk).find(x=>wordsOf(x));
    const w=wordsOf(vk);
    if(!other||!w)continue;
    const [sn,an]=vk.split(":").map(Number);
    const chunk=[seg(sn,an,0,w.words.length-1)];
    steps.push({chunk,shows:["text"],link:false,tw:other});
    steps.push({chunk,shows:["blind"],link:false});
    if(steps.length>=2*(t.max||4))break;
  }
  return expand(steps,{kind:"massed"});
}
function hasTwins(vks){
  if(!ctx.mutTwins)return false;
  for(const vk of vks){try{if((ctx.mutTwins(vk)||[]).length)return true;}catch(e){}}
  return false;
}

// ============================================================
// СБОРКА
// ============================================================
function buildPass(vks,cfg,rnd){
  let chunks=cut(vks,cfg.unit||{kind:"ayah"});
  chunks=applySeam(chunks,cfg.seam||{kind:"none"});
  if(!chunks.length)return [];
  chunks=applyOrder(chunks,cfg.order||{kind:"forward"},rnd);
  let steps=makeSteps(chunks,cfg.reps||{n:5,show:"text"});
  steps=applyLink(steps,cfg.link||{kind:"none"});
  return expand(steps,cfg.spacing||{kind:"massed"});
}
// Разогрев: послушать весь блок целиком, водя пальцем, и только потом долбить.
// Вход мадинской программы «Такрар» — сперва слух, потом повтор.
function warmupSteps(vks,cfg){
  const w=cfg.warmup;if(!w||!w.n)return [];
  const chunk=vks.map(vk=>{const [s,a]=vk.split(":").map(Number);const ww=wordsOf(vk);
    return seg(s,a,0,ww.words.length-1);});
  return expand([{chunk,shows:Array.from({length:w.n},()=>"text"),link:false,role:"listen"}],
                {kind:"massed"}).map(at=>Object.assign(at,{role:"listen",warm:true}));
}
function build(vks,cfg,seed){
  const rnd=mulberry32(seed>>>0||1);
  const warm=warmupSteps(vks,cfg);
  const fix=diagnosticSteps(vks,cfg);            // стадия 0 — ремонт слабых швов
  let main;
  if(cfg.twins&&cfg.twins.only)main=[];          // пресет «Близнецы»: только пары
  else if(cfg.passes&&cfg.passes.length){
    main=[];
    for(const p of cfg.passes)main.push(...buildPass(vks,Object.assign({},cfg,p),rnd));
  }else main=buildPass(vks,cfg,rnd);
  // Номера шагов ремонтного блока не должны совпадать с основными: критерий
  // остановки работает по step-id и иначе схлопнул бы разные шаги в один.
  const w0=warm.length?Math.max(...warm.map(a=>a.step))+1:0;
  const fx=fix.map(a=>Object.assign({},a,{step:a.step+w0}));
  const shift=w0+(fix.length?Math.max(...fix.map(a=>a.step))+1:0);
  // Ось role: пресет может задать роль всем ОСНОВНЫМ атомам («синхронно с
  // чтецом»). Разогрев и ремонт швов свои роли уже несут — их не перебиваем.
  const stamp=cfg.role?a=>Object.assign({},a,{step:a.step+shift,role:cfg.role})
                      :a=>Object.assign({},a,{step:a.step+shift});
  const body=main.map(stamp);
  // Пары муташабихат — В КОНЦЕ: развилка имеет смысл, когда аят уже сидит.
  const tw=twinSteps(vks,cfg);
  if(!tw.length)return warm.concat(fx,body);
  const shift2=shift+(main.length?Math.max(...main.map(a=>a.step))+1:0);
  return warm.concat(fx,body,tw.map(a=>Object.assign({},a,{step:a.step+shift2})));
}

// ============================================================
// КАТАЛОГ ПРЕСЕТОВ (§6 HIFZ_METHODS.md)
// ============================================================
// Пресет — именованный набор значений осей, как «метод расчёта» в приложении
// времён намаза. Добавить методику = дописать сюда строчку.
// Названия РАБОЧИЕ (см. §6 — переименование отложено).
// need:"audio"|"page" — чего пресету не хватает в этой версии станка; такие
// показываются в списке серыми, чтобы каталог не врал о готовности.
const BASE={unit:{kind:"ayah"},seam:{kind:"none",k:3},order:{kind:"forward"},
  reps:{n:5,show:"text"},link:{kind:"none"},spacing:{kind:"massed"},
  stop:{kind:"fixed"},                          // ворот нет; научные пресеты включают criterion
  diagnostics:{inject:true,max:3}};             // слабые швы лечим перед уроком

const PRESETS=[
 {grp:"Традиционные",id:"talqin",name:"Повторяй за чтецом",sub:"Аят три раза, спокойный темп. С чего начать. Включи «звук + пауза» — и станок поведёт сам.",
  cfg:{reps:{pattern:["text","text","text","blind"]}}},
 {grp:"Традиционные",id:"takrar_madina",name:"Сперва послушать",sub:"Программа «Такрар» Медины: сначала блок целиком три раза на слух, водя пальцем, и только потом повторы.",
  cfg:{warmup:{n:3},reps:{pattern:["text","text","text","text","text","blind","blind"]},link:{kind:"snowball",every:4,reps:3}}},
 {grp:"Традиционные",id:"takrar20",name:"Повтор двадцать",sub:"Классика: один аят двадцать раз подряд.",
  cfg:{reps:{n:20,show:"text"}}},
 {grp:"Традиционные",id:"jam",name:"Связка по четыре",sub:"20 раз аят, после каждых четырёх — все четыре вместе. Самая ходовая схема у хафизов.",
  cfg:{reps:{n:20,show:"text"},link:{kind:"snowball",every:4,reps:3}}},
 {grp:"Традиционные",id:"khamsan",name:"По пять",sub:"То же, но связка каждые пять аятов.",
  cfg:{reps:{n:20,show:"text"},link:{kind:"snowball",every:5,reps:3}}},
 {grp:"Традиционные",id:"t33",name:"Три на три",sub:"Каждый аят три раза, потом с соседом три раза.",
  cfg:{reps:{n:3,show:"text"},link:{kind:"krama",reps:3}}},
 {grp:"Традиционные",id:"t73",name:"Семь и три",sub:"Семь раз с текстом, три по памяти, потом связка.",
  cfg:{reps:{pattern:["text","text","text","text","text","text","text","blind","blind","blind"]},link:{kind:"snowball",every:4,reps:3}}},
 {grp:"Традиционные",id:"t1010",name:"Десять и десять",sub:"Десять раз аят, десять раз пара. Для коротких рифмующихся сур.",
  cfg:{reps:{n:10,show:"text"},link:{kind:"snowball",every:2,reps:10}}},
 {grp:"Традиционные",id:"t310",name:"Десять-три, потом всё",sub:"Десять с текстом, три по памяти; в конце — весь блок целиком.",
  cfg:{reps:{pattern:["text","text","text","text","text","text","text","text","text","text","blind","blind","blind"]},
       passes:[{unit:{kind:"ayah"}},{unit:{kind:"block"},reps:{pattern:["text","text","text","blind","blind","blind"]}}]}},
 {grp:"Традиционные",id:"t6446",name:"Шесть-четыре-четыре-шесть",sub:"6 с текстом, 4 по памяти, 4 с текстом, 6 по памяти. Схема для детей.",
  cfg:{reps:{pattern:["text","text","text","text","text","text","blind","blind","blind","blind","text","text","text","text","blind","blind","blind","blind","blind","blind"]}}},

 {grp:"Швы между аятами",id:"overlap",name:"Внахлёст",sub:"Аят плюс первые три слова следующего: шов попадает в середину порции, а не на её край.",
  cfg:{seam:{kind:"fwd",k:3},reps:{n:7,show:"text"},link:{kind:"snowball",every:4,reps:3}}},
 {grp:"Швы между аятами",id:"overlap2",name:"Внахлёст в обе стороны",sub:"Хвост предыдущего + аят + голова следующего. Помогает и начинать с середины.",
  cfg:{seam:{kind:"both",k:3},reps:{n:7,show:"text"}}},
 {grp:"Швы между аятами",id:"seams",name:"Только швы",sub:"Голые стыки: конец аята и начало следующего. Для выученного, которое сыпется на переходах.",
  cfg:{seam:{kind:"only",k:3},reps:{pattern:["text","text","blind","blind"]}}},
 {grp:"Швы между аятами",id:"weave",name:"Возвратное плетение",sub:"К каждому шву возвращаются несколько раз вперемешку с соседними — стык не успевает остыть.",
  cfg:{seam:{kind:"only",k:4},reps:{n:2,show:"text"},link:{kind:"weave",reps:2}}},
 {grp:"Швы между аятами",id:"twins",name:"Близнецы",sub:"Аяты, которые почти дословно повторяются в других сурах, ставятся рядом с двойником: надо назвать развилку. Сбиваются не на аяте, а на различии между ним и близнецом.",
  cfg:{twins:{only:true,max:4}}},
 {grp:"Швы между аятами",id:"backward",name:"Сборка с конца",sub:"Учится последний аят, потом предпоследний вместе с ним, и так до начала. Хвост блока перестаёт быть слабым. Читается всегда по порядку.",
  cfg:{reps:{pattern:["text","text","text","blind"]},link:{kind:"backward",reps:3},stop:{kind:"criterion",maxExtra:6}}},

 {grp:"Научные",id:"vanishing",name:"Гаснущая подсказка",sub:"Текст пропадает по словам от повтора к повтору, последний — по памяти.",
  cfg:{stop:{kind:"criterion",maxExtra:6},reps:{n:6,show:"fade"},link:{kind:"snowball",every:4,reps:3}}},
 {grp:"Научные",id:"retrieval",name:"Через вспоминание",sub:"Один раз прочитал — пять раз вспомнил. Меньше чтения, больше усилия.",
  cfg:{stop:{kind:"criterion",maxExtra:6},reps:{pattern:["text","blind","blind","blind","blind","blind"]},link:{kind:"snowball",every:4,reps:3}}},
 {grp:"Научные",id:"spaced",name:"Разнесённый повтор",sub:"Повторы одного аята не идут подряд: между ними вклиниваются другие. Тяжелее, держится дольше.",
  cfg:{stop:{kind:"criterion",maxExtra:6},reps:{n:6,show:"fade"},spacing:{kind:"expanding",gaps:[1,2,4,8,16]}}},
 {grp:"Научные",id:"lawh",name:"Цифровой лоух",sub:"На повторах по памяти набираешь первую букву каждого слова — верная проявляет слово. Рука участвует в извлечении, как на суданской доске, но без каллиграфии.",
  cfg:{reps:{pattern:["text","text","blind","blind"]},link:{kind:"snowball",every:4,reps:3},stop:{kind:"criterion",maxExtra:4}},chan:"letters"},
 {grp:"Научные",id:"hard",name:"Полезная трудность",sub:"Разнесённый повтор + перемешанный порядок + минимум чтения. Самый неудобный и самый стойкий.",
  cfg:{stop:{kind:"criterion",maxExtra:6},order:{kind:"shuffle"},reps:{pattern:["text","blind","blind","blind","blind"]},spacing:{kind:"expanding",gaps:[1,2,4,8,16]}}},
 {grp:"Научные",id:"wholepage",name:"Страница целиком",sub:"Порция — не аят, а страница мусхафа целиком: двенадцать прочтений, последние по памяти. Так учат там, где счёт идёт страницами, а не аятами.",
  cfg:{unit:{kind:"page"},reps:{pattern:["text","text","text","text","text","text","text","text","text","blind","blind","blind"]},stop:{kind:"criterion",maxExtra:4}}},
 {grp:"Научные",id:"shadow",name:"Синхронно с чтецом",sub:"Читать ВМЕСТЕ с чтецом, не после него: голос ведёт темп, протяжки и таджвид. Пауз нет, поэтому проходит быстро — берут для разгона перед повторами. Требует звука, он включится сам.",
  cfg:{role:"shadow",reps:{n:5,show:"text"},link:{kind:"snowball",every:4,reps:3}},needsAudio:true},
 {grp:"Научные",id:"bottomup",name:"Снизу вверх",sub:"Строки страницы мусхафа с ПОСЛЕДНЕЙ к первой, потом страница целиком. Порядок ломает опору на «что было выше» — держит только сам текст.",
  cfg:{unit:{kind:"line"},order:{kind:"reverse"},reps:{pattern:["text","text","blind"]},
       passes:[{unit:{kind:"line"},order:{kind:"reverse"}},{unit:{kind:"page"},order:{kind:"forward"},reps:{pattern:["text","text","blind","blind"]}}]}},
 {grp:"Научные",id:"halfpage",name:"Полстраницы",sub:"Порция — половина страницы мусхафа: строки делятся пополам. Середина между аятом и целой страницей.",
  cfg:{unit:{kind:"halfpage"},reps:{n:10,show:"text"},stop:{kind:"criterion",maxExtra:4}}},
 {grp:"Научные",id:"reverse",name:"С конца блока",sub:"Аяты в обратном порядке: лечит «начало помню, конец плаваю».",
  cfg:{order:{kind:"reverse"},reps:{n:7,show:"text"},link:{kind:"snowball",every:4,reps:3}}},

 {grp:"Пока недоступны",id:"ottoman",name:"Концы джузов",sub:"Османский метод: последние страницы каждого джуза, по спирали. Это не заучивание, а обход для повторения — такому место в слое удержания (🎯), не в станке.",cfg:{},need:"juz"},

];
const NEED_WHY={juz:"это схема повторения — её место в 🎯, а не в станке",
  write:"нужен слой рукописи"};
const presetById=id=>PRESETS.find(p=>p.id===id);
function cfgOf(p){return Object.assign({},BASE,p.cfg||{});}

// ============================================================
// СОСТОЯНИЕ
// ============================================================
const D={open:false,view:"setup",el:null,
  s:78,from:1,to:5,method:"talqin",
  veil:"none",                                 // none | fade | hide  — переключатель поверх
  prog:null,i:0,revealed:false,seed:1,vks:[],
  stop:null,extra:{},grades:{},graded:false,   // ворота самооценки (см. gateOn)
  pace:"tap",aud:0,playing:false,warned:false,timer:null, // звук: tap | audio (см. runAudio)
  channel:"voice",lw:0,lwBad:0,lastKey:"",     // voice | letters — цифровой лоух
  wake:null,want:false};

export function isOpen(){return D.open;}

// ============================================================
// ВУАЛЬ (переключатель поверх — в программу не запечён)
// ============================================================
// Гашение НАРАСТАЮЩЕЕ: набор скрытых слов при большем p включает набор при
// меньшем, иначе слово то пропадает, то возвращается, и это читается как сбой.
// Порядок гашения — устойчивый псевдослучайный ранг по слову (scatter).
function hideRank(chKey,idx){
  let h=2166136261;const s=chKey+"#"+idx;
  for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}
  return (h>>>0)/4294967296;
}
// Итоговый режим показа атома с учётом переключателя вуали.
function showOf(at){
  if(D.veil==="hide")return at.i===0&&at.show==="text"?{p:0}:{p:1};
  if(at.show==="blind")return {p:1};
  if(typeof at.show==="number")return {p:at.show};
  if(D.veil==="fade"){                         // ровная лесенка по повторам шага
    if(at.of<2)return {p:0};
    return {p:Math.min(0.85,at.i/(at.of-1))};
  }
  return {p:0};
}

// ============================================================
// ЗВУК: РОЛИ АТОМА
// ============================================================
// Первая редакция имела одну ось «темп» (аудио | шэдоуинг | тап). Её мало:
// «послушай → повтори за → скажи ДО чтеца» одной осью не выражается. Роль
// выводится из режима показа, и это даёт правильное поведение само собой:
//   виден текст → ECHO      : чтец читает, потом тишина той же длины — повтори;
//   по памяти   → ANTICIPATE: сперва тишина (говоришь ты), потом чтец — сверка.
// Приём «скажи до чтеца» взят у Al Muhaffiz; вторая половина — классический
// талькын. Роль listen (только слушать, без паузы) ставится разогреву.
function roleOf(at){
  if(at.role)return at.role;
  return showOf(at).p>=1?"anticipate":"echo";
}
// Паузой распоряжается СТАНОК, а не playSegment (обожглись 2026-08-29): пауза
// принадлежит ПОРЦИИ, а не сегменту. Связка из четырёх аятов — это четыре
// сегмента (у 52 чтецов из 53 файл отдельный на каждый аят), и пауза после
// каждого разрывала связку на четыре огрызка, хотя её смысл — прочесть слитно.
// Поэтому playSegment зовётся без пауз, а тишину отмеряем здесь, зная порцию.
function sleep(ms,my){return new Promise(r=>{D.timer=setTimeout(()=>{if(my===D.aud)r();},ms);});}
async function runAudio(){
  if(D.pace!=="audio"||D.view!=="run"||!ctx.playSegment)return;
  const at=D.prog[D.i];if(!at)return;
  const my=++D.aud;
  D.playing=true;render();
  const role=roleOf(at);
  // Оценка длительности для паузы ДО чтения: заранее её взять неоткуда — файл
  // ещё не загружен. ~0.45 с на слово, та же прикидка, что на экране плана.
  const est=Math.max(1200,chunkLen(at.chunk)*450);
  // shadow — шэдоуинг: читаешь ОДНОВРЕМЕННО с чтецом. Тишины нет ни до, ни
  // после: пауза превратила бы синхронное чтение в обычное «повтори следом».
  if(role==="anticipate"){                     // сперва говоришь ты, потом сверка
    await sleep(est,my);
    if(my!==D.aud||!D.open)return;
  }
  let inexact=false,total=0;
  for(const g of at.chunk){
    if(my!==D.aud||!D.open)return;
    const w=wordsOf(vkOf(g));
    const r=await ctx.playSegment({s:g.s,a:g.a,w0:g.w0,w1:g.w1,words:w?w.words:null},{});
    if(!r||!r.ok)return;                       // прервали тапом, закрыли или нет звука
    total+=r.ms||0;
    if(r.exact===false)inexact=true;
  }
  if(my!==D.aud||!D.open||D.view!=="run")return;
  if(role==="echo"){                           // тишина ровно такой же длины — повтори
    await sleep(total||est,my);
    if(my!==D.aud||!D.open||D.view!=="run")return;
  }
  D.playing=false;
  if(inexact&&!D.warned){D.warned=true;}       // пометка «часть аята — на слух приблизительно»
  if(gateOn()){render();return;}               // ворота: дальше только ответом
  step(1);                                     // станок ведёт сам
}
function stopAudio(){
  D.aud++;D.playing=false;
  if(D.timer){clearTimeout(D.timer);D.timer=null;}
  if(ctx.stopSegment)ctx.stopSegment();
}

// ============================================================
// РАЗМЕТКА
// ============================================================
// force=true — раскрытие по тапу: показать целиком, минуя вуаль. Через showOf
// этого не выразить (при veil="fade" он считает долю от номера повтора и вернул
// бы ту же вуаль обратно), поэтому раскрытие — отдельный флаг.
// Плоский список слов порции: [{сегмент, индекс в аяте, слово}]. Нужен и вуали
// (какие гасить), и лоуху (какое слово следующее по счёту).
function flatWords(chunk){
  const out=[];
  for(let si=0;si<chunk.length;si++){
    const g=chunk[si],w=wordsOf(vkOf(g));if(!w)continue;
    for(let i=g.w0;i<=g.w1;i++)out.push({si,g,i,word:w.words[i]});
  }
  return out;
}
function arabicHTML(at,force,revealN){
  const p=force?0:showOf(at).p;
  const key=chunkKey(at.chunk);
  const flat=flatWords(at.chunk);
  const parts=[];let cur=-1,buf=[];
  flat.forEach((it,n)=>{
    if(it.si!==cur){if(buf.length)parts.push(buf.join(" "));buf=[];cur=it.si;}
    let hidden=p>=1||(p>0&&hideRank(key,it.g.s+":"+it.g.a+":"+it.i)<p);
    if(revealN!=null&&n<revealN)hidden=false;      // лоух: набранное уже открыто
    else if(revealN!=null)hidden=true;
    // Скрытое слово НЕ подменяется прочерком: оно остаётся на месте и лишь
    // красится прозрачным (см. .hfd-gap). Прочерк фиксированной длины
    // переверстывал строку на каждом повторе — а место слова на странице
    // само по себе опора памяти, её нельзя дёргать.
    const cls=(revealN!=null&&n===revealN)?"hfd-gap hfd-next":"hfd-gap";
    buf.push(hidden?`<span class="${cls}">${esc(it.word)}</span>`:esc(it.word));
  });
  if(buf.length)parts.push(buf.join(" "));
  return parts.join(' <span class="hfd-sep">۝</span> ');
}

// ═══ ЦИФРОВОЙ ЛОУХ: ПЕРВЫЕ БУКВЫ ═══
// Суданская и мавританская доска работают за счёт generation effect: рука
// участвует в извлечении. Рисовать вязь пальцем на телефоне неудобно, а
// распознавание рукописи сбоит — поэтому набирается только ПЕРВАЯ БУКВА каждого
// слова по порядку; верная буква проявляет слово целиком. Моторное извлечение
// есть, каллиграфии нет. Тот же приём — first-letter script у актёров.
// Клавиатура своя, экранная: системная арабская есть не у всех, а на телефоне
// её ещё и переключать.
const AR_KEYS="ا ب ت ث ج ح خ د ذ ر ز س ش ص ض ط ظ ع غ ف ق ك ل م ن ه و ي".split(" ");
const HARAKAT=/[\u064B-\u0653\u0670\u06D6-\u06ED\u0640]/g;
function firstLetter(word){
  const bare=String(word||"").replace(HARAKAT,"");
  const c=bare[0]||"";
  // Все варианты алифа — одна клавиша. Отдельно: в османском начертании слова
  // на آ/أ пишутся с ВЕДУЩЕЙ одиночной хамзой (ءَامَنُوا۟, ءَأَنذَرْتَهُمْ) — таких
  // 890 на весь Коран, и все до одной суть алиф. Хафиз назовёт букву алифом,
  // а не хамзой, поэтому в начале слова хамза приравнена к алифу (проверено
  // прогоном по всем 77 881 слову: иных начальных хамз в тексте нет).
  if("أإآٱاء".indexOf(c)>=0)return "ا";
  if(c==="ى")return "ي";
  return c;
}
function lawhOn(){
  const at=D.prog&&D.prog[D.i];
  return !!(at&&D.channel==="letters"&&D.view==="run"&&showOf(at).p>=1&&!D.revealed);
}
function lawhKey(ch){
  const at=D.prog[D.i];if(!at)return;
  const flat=flatWords(at.chunk);
  const want=firstLetter((flat[D.lw]||{}).word);
  if(ch===want){
    D.lw++;D.lwBad=0;
    if(D.lw>=flat.length){                       // порция набрана целиком
      D.lw=0;D.revealed=true;render();
      if(!gateOn())setTimeout(()=>{if(D.open&&D.view==="run")step(1);},700);
      return;
    }
  }else{D.lwBad++;}
  render();
}
function lawhHTML(){
  const at=D.prog[D.i];if(!at)return "";
  const flat=flatWords(at.chunk);
  return `<div class="hfd-lawh">
    <div class="hfd-lw-hint">${D.lw+1} из ${flat.length} · набери первую букву слова${D.lwBad?` <b class="hfd-lw-bad">не та буква</b>`:""}</div>
    <div class="hfd-keys">${AR_KEYS.map(k=>
      `<button class="hfd-k${D.lwBad&&k===D.lastKey?" bad":""}" data-act="lawh" data-k="${k}">${k}</button>`).join("")}</div>
  </div>`;
}

// ═══ ОХВАТ СМЫСЛОВЫМ ОТРЕЗКОМ (рукуʿ) ═══
// Аяты руками («с 1 по 5») режут тему посередине: конец блока приходится на
// середину мысли, и шов между блоками оказывается там, где связь как раз самая
// сильная. Рукуʿ — каноническое деление ПО СМЫСЛУ, 556 отрезков, в среднем по
// 11 аятов. Здесь он задаёт ОХВАТ (что берём в работу), а не порцию: одиннадцать
// аятов за один повтор не проговоришь.
function rukuSegs(){const f=ctx.rukuSegs;return (f&&f(D.s))||null;}
function rukuAt(a){                              // отрезок, в который попал аят
  const segs=rukuSegs();if(!segs)return null;
  for(let i=0;i<segs.length;i++)if(a>=segs[i][0]&&a<=segs[i][1])return {i,seg:segs[i],of:segs.length};
  return null;
}
function rukuTake(d){
  const segs=rukuSegs();if(!segs)return;
  const cur=rukuAt(D.from);
  let i=cur?cur.i+(d||0):0;
  i=Math.max(0,Math.min(segs.length-1,i));
  D.from=segs[i][0];D.to=segs[i][1];
  render();
}
function rukuRowHTML(){
  const segs=rukuSegs();
  if(!segs)return `<div class="hfd-row"><label>Отрезок</label><span class="hfd-note">данные о смысловых отрезках не загрузились</span></div>`;
  const cur=rukuAt(D.from);
  const exact=cur&&D.from===cur.seg[0]&&D.to===cur.seg[1];
  const ti=cur?(ctx.rukuTitle?ctx.rukuTitle(cur.seg[2]):""):"";
  const lab=cur?`${cur.i+1} из ${segs.length} в суре · аяты ${cur.seg[0]}–${cur.seg[1]}`:"—";
  return `<div class="hfd-row">
    <label>Отрезок</label>
    <button class="hfd-chip" data-act="ruku" data-d="-1" title="Предыдущий смысловой отрезок">‹</button>
    <button class="hfd-chip ${exact?"on":""}" data-act="ruku" data-d="0" title="Взять этот отрезок целиком: границы проведены по смыслу, а не по счёту аятов">ع взять целиком</button>
    <button class="hfd-chip" data-act="ruku" data-d="1" title="Следующий смысловой отрезок">›</button>
    <span class="hfd-note">${esc(lab)}${ti?" · "+esc(ti):""}</span>
  </div>`;
}

// Кто читает и насколько точно режется. Чтец берётся ОБЩИЙ с 🎧 намеренно:
// специфичность кодирования — заученное под один голос под другим вспоминается
// хуже, и менять его посреди блока значит частично учить заново.
// Страница мусхафа как охват. Страница часто ЛЕЖИТ НА ДВУХ СУРАХ, а охват у
// станка — сура плюс аяты; поэтому берём ту часть страницы, что попала в суру,
// и говорим об этом прямо, а не молча отдаём огрызок.
function pageTake(d){
  if(!ctx.pageOf||!ctx.pageVks)return;
  let pg=null;try{pg=ctx.pageOf(D.s,D.from);}catch(e){}
  if(!pg)return;
  const total=(ctx.pagesTotal&&ctx.pagesTotal())||604;
  pg=Math.max(1,Math.min(total,pg+(d||0)));
  const vks=ctx.pageVks(pg)||[];
  if(!vks.length)return;
  const bySura={};
  for(const vk of vks){const [sn,an]=vk.split(":").map(Number);(bySura[sn]=bySura[sn]||[]).push(an);}
  // Своя сура в приоритете; если страница целиком чужая — переходим в ту, где её больше.
  const keys=Object.keys(bySura).map(Number);
  const pick=keys.includes(D.s)?D.s:keys.sort((a,b)=>bySura[b].length-bySura[a].length)[0];
  const ans=bySura[pick];
  D.s=pick;D.from=Math.min(...ans);D.to=Math.max(...ans);
  render();
}
function pageRowHTML(){
  if(!ctx.pageOf)return "";
  let pg=null;try{pg=ctx.pageOf(D.s,D.from);}catch(e){}
  if(!pg)return `<div class="hfd-row"><label>Страница</label><span class="hfd-note">данные страниц мусхафа не загрузились</span></div>`;
  const vks=(ctx.pageVks&&ctx.pageVks(pg))||[];
  const mine=vks.filter(v=>+v.split(":")[0]===D.s).map(v=>+v.split(":")[1]);
  const exact=mine.length&&D.from===Math.min(...mine)&&D.to===Math.max(...mine);
  const split=vks.length&&mine.length&&mine.length<vks.length;
  const lab=mine.length?`страница ${pg} · аяты ${Math.min(...mine)}–${Math.max(...mine)}`:`страница ${pg}`;
  return `<div class="hfd-row">
    <label>Страница</label>
    <button class="hfd-chip" data-act="page" data-d="-1" title="Предыдущая страница мусхафа">‹</button>
    <button class="hfd-chip ${exact?"on":""}" data-act="page" data-d="0" title="Взять страницу мусхафа целиком — ту самую бумагу, что видно в режиме «Мусхаф»">▤ взять страницу</button>
    <button class="hfd-chip" data-act="page" data-d="1" title="Следующая страница мусхафа">›</button>
    <span class="hfd-note">${esc(lab)}${split?" · часть страницы в соседней суре":""}</span>
  </div>`;
}

function paceNote(){
  const pm=presetById(D.method);
  if(D.pace!=="audio")return pm&&pm.needsAudio?"без звука шэдоуинга не выйдет — включи «звук + пауза»":"листаешь сам";
  const r=ctx.reciter&&ctx.reciter();
  if(!r)return "со звуком станок ведёт сам";
  return "читает "+r.name+" (общий с 🎧) · станок ведёт сам";
}

function setupHTML(){
  const su=SU(D.s)||{n:1,ru:""};
  const grps=[...new Set(PRESETS.map(p=>p.grp))];
  const list=grps.map(g=>`<div class="hfd-grp">${esc(g)}</div>`+
    PRESETS.filter(p=>p.grp===g).map(p=>{
      const off=!!p.need;
      return `<button class="hfd-m ${D.method===p.id&&!off?"on":""} ${off?"off":""}" data-act="${off?"noop":"method"}" data-id="${p.id}">
        <b>${esc(p.name)}${p.warn?' <span class="hfd-warn">необычный порядок</span>':''}</b>
        <i>${esc(p.sub)}${off?" · "+esc(NEED_WHY[p.need]||""):""}</i></button>`;
    }).join("")).join("");
  return `<div class="hfd-setup">
    <div class="hfd-h">📿 Станок заучивания</div>
    <div class="hfd-sub">Приложение ведёт заучивание по программе: показывает порцию нужное число раз в нужном виде, ты повторяешь вслух.</div>
    <div class="hfd-row">
      <label>Сура</label>
      <select class="hfd-in" data-act="sura">${ctx.SURAHS.map(x=>`<option value="${x.id}"${x.id===D.s?" selected":""}>${x.id}. ${esc(x.ru)}</option>`).join("")}</select>
    </div>
    <div class="hfd-row">
      <label>Аяты</label>
      <input class="hfd-in hfd-n" type="number" inputmode="numeric" min="1" max="${su.n}" value="${D.from}" data-act="from"> —
      <input class="hfd-in hfd-n" type="number" inputmode="numeric" min="1" max="${su.n}" value="${D.to}" data-act="to">
      <span class="hfd-note">всего в суре ${su.n}</span>
    </div>
    ${rukuRowHTML()}
    ${pageRowHTML()}
    <div class="hfd-row">
      <label>Темп</label>
      <button class="hfd-chip ${D.pace==="tap"?"on":""}" data-act="pace" data-v="tap" title="Листаешь сам">тап</button>
      <button class="hfd-chip ${D.pace==="audio"?"on":""}" data-act="pace" data-v="audio" title="Чтец читает, потом тишина той же длины — повторяешь вслух. На повторах «по памяти» тишина идёт ПЕРВОЙ: говоришь ты, потом сверяешься с чтецом">звук + пауза</button>
      <span class="hfd-note">${paceNote()}</span>
    </div>
    <div class="hfd-row">
      <label>Отклик</label>
      <button class="hfd-chip ${D.channel==="voice"?"on":""}" data-act="chan" data-v="voice" title="Читаешь вслух, оцениваешь себя сам">голосом</button>
      <button class="hfd-chip ${D.channel==="letters"?"on":""}" data-act="chan" data-v="letters" title="На повторах «по памяти» набираешь первую букву каждого слова — рука участвует в извлечении, как на суданской доске">первые буквы</button>
      <span class="hfd-note">${D.channel==="letters"?"клавиатура появится на повторах по памяти":"как в мактабе — вслух"}</span>
    </div>
    <div class="hfd-row">
      <label>Показ</label>
      <button class="hfd-chip ${D.veil==="none"?"on":""}" data-act="veil" data-v="none">текст виден</button>
      <button class="hfd-chip ${D.veil==="fade"?"on":""}" data-act="veil" data-v="fade">гаснет</button>
      <button class="hfd-chip ${D.veil==="hide"?"on":""}" data-act="veil" data-v="hide">по памяти</button>
    </div>
    <div class="hfd-methods">${list}</div>
    <div class="hfd-go"><button class="hfd-start" data-act="start">Собрать программу и начать</button></div>
  </div>`;
}

function planHTML(){
  const n=D.prog.length;
  // Пресет «Близнецы» на блоке без муташабихат собрал бы пустую программу.
  // Честнее сказать это прямо, чем показать «0 повторов».
  if(!n){
    const p0=presetById(D.method);
    return `<div class="hfd-plan">
      <div class="hfd-h">${esc(p0?p0.name:"")}</div>
      <div class="hfd-sub">${esc(D.s)}:${D.from}–${D.to}</div>
      <div class="hfd-note2">В этом отрезке нет аятов, которые почти дословно
      повторяются в других сурах, — паре не из чего собраться. Возьми охват шире
      или выбери другой метод.</div>
      <div class="hfd-go"><button class="hfd-back" data-act="setup">← К настройке</button></div>
    </div>`;
  }
  const sec=D.prog.reduce((t,a)=>t+chunkLen(a.chunk)*0.45+1.2,0);
  const p=presetById(D.method);
  const links=D.prog.filter(a=>a.link).length;
  return `<div class="hfd-plan">
    <div class="hfd-h">${esc(p?p.name:"")}</div>
    <div class="hfd-sub">${esc(D.s)}:${D.from}–${D.to} · ${D.vks.length} ${plural(D.vks.length,"аят","аята","аятов")}</div>
    <div class="hfd-nums">
      <div><b>${n}</b><i>${plural(n,"повтор","повтора","повторов")}</i></div>
      <div><b>${links}</b><i>из них связки</i></div>
      <div><b>${mmss(sec)}</b><i>примерно</i></div>
    </div>
    <div class="hfd-go">
      <button class="hfd-start" data-act="run">Начать</button>
      <button class="hfd-back" data-act="setup">← Изменить</button>
    </div>
  </div>`;
}

// Пара близнецов на экране. Сперва — только твой аят и АДРЕС двойника: развилку
// надо назвать по памяти, а не узнать в готовом виде. Тап открывает двойника с
// подсвеченным различием.
function twinHTML(at){
  const vk=vkOf(at.chunk[0]),other=at.tw;
  const w1=wordsOf(vk),w2=wordsOf(other);
  const [s1,a1]=vk.split(":").map(Number),[s2,a2]=other.split(":").map(Number);
  const n1=SU(s1)||{ru:""},n2=SU(s2)||{ru:""};
  if(!w1||!w2)return `<div class="hfd-ar arabic-main">${arabicHTML(at,false,null)}</div>`;
  const [f1,f2]=diffFlags(w1.words,w2.words);
  const same=!f1.some(Boolean)&&!f2.some(Boolean);   // дословный повтор
  const rev=D.revealed;
  const line=(ws,fl)=>ws.map((x,i)=>rev&&fl[i]?`<span class="hfd-dif">${esc(x)}</span>`:esc(x)).join(" ");
  // Хвост предыдущего аята — приглушённой строкой сверху: у дословных близнецов
  // это единственное, чем они различаются, и держаться надо именно за него.
  const lead=vkk=>{
    const pv=prevVk(vkk),w=pv&&wordsOf(pv);
    if(!w||!w.words.length)return `<div class="hfd-tw-lead none">начало суры</div>`;
    const tail=w.words.slice(-4).join(" ");
    return `<div class="hfd-tw-lead"><span class="hfd-tw-adr2">${esc(pv)}</span>
      <span class="arabic-main">…${esc(tail)}</span></div>`;
  };
  const one=(sn,an,ru,ws,fl,mine,vkk)=>`<div class="hfd-tw-one${mine?" mine":""}">
      <div class="hfd-tw-adr">${sn}:${an} · ${esc(ru)}${mine?" · твой":""}</div>
      ${same?lead(vkk):""}
      <div class="hfd-ar arabic-main">${line(ws,fl)}</div>
    </div>`;
  return `<div class="hfd-tw">
    ${one(s1,a1,n1.ru,w1.words,f1,true,vk)}
    ${rev?one(s2,a2,n2.ru,w2.words,f2,false,other)
        :`<div class="hfd-tw-ask">Двойник — <b>${s2}:${a2}</b>, ${esc(n2.ru)}.<br>${
            same?"Слово в слово. Развилка здесь не в тексте: чем отличается МЕСТО — что стоит до и после?"
                :"Чем он отличается? Назови вслух, потом тап."}</div>`}
    ${rev&&same?`<div class="hfd-tw-ask">Слово в слово — в самом аяте различий нет.
      Развилка выше, в приглушённой строке: за неё и держись, а не за сам аят.</div>`:""}
  </div>`;
}

function runHTML(){
  const at=D.prog[D.i];
  if(!at)return doneHTML();
  const {p}=showOf(at);
  const veiled=p>0;
  const bas=at.chunk.length===1&&at.chunk[0].w0===0&&(wordsOf(vkOf(at.chunk[0]))||{}).bas;
  const mode=p>=1?"по памяти":(p>0?"подсказка тает":"с текстом");
  return `<div class="hfd-run">
    <div class="hfd-top">
      <span class="hfd-key">${esc(chunkLabel(at.chunk))}${at.link?' · <b>связка</b>':''}${
        D.pace==="audio"&&ctx.reciter&&ctx.reciter()?' · <i class="hfd-rec">'+esc(ctx.reciter().name)+'</i>':''}</span>
      <div class="hfd-tools">
        <button class="hfd-b ${D.pace==="audio"?"on":""}" data-act="pace" data-v="${D.pace==="audio"?"tap":"audio"}" title="Звук чтеца с паузой на твой повтор">♪</button>
        <button class="hfd-b ${D.veil==="fade"?"on":""}" data-act="veil" data-v="${D.veil==="fade"?"none":"fade"}" title="Гасить текст по ходу повторов">вуаль</button>
        <button class="hfd-b" data-act="prev" title="Предыдущий повтор">‹</button>
        <button class="hfd-x" data-act="close" title="Закрыть">✕</button>
      </div>
    </div>
    <div class="hfd-bar"><div class="hfd-fill" style="width:${Math.round(D.i*100/D.prog.length)}%"></div></div>
    <div class="hfd-count">${D.i+1} из ${D.prog.length} · повтор ${at.i+1}/${at.of} · ${mode}${
      at.warm?" · разогрев":at.fix?" · ремонт шва":at.tw?" · развилка":""}</div>
    <div class="hfd-main">
      <div class="hfd-body">
        ${at.tw?twinHTML(at):
          (bas?`<div class="hfd-bas arabic-main">${esc(bas)}</div>`:"")+
          `<div class="hfd-ar arabic-main">${arabicHTML(at,D.revealed&&veiled,lawhOn()?D.lw:null)}</div>`}
      </div>
    </div>
    ${lawhOn()?lawhHTML():""}
    <div class="hfd-bottom">${D.playing
      ? `<span class="hfd-live">${roleOf(at)==="anticipate"?"Читай по памяти — чтец проверит следом"
          :roleOf(at)==="listen"?"Слушай и веди пальцем"
          :roleOf(at)==="shadow"?"Читай ВМЕСТЕ с чтецом, не после него"
          :"Слушай, потом повтори в тишину"}</span>`
      : gateOn()
      ? `<span class="hfd-ask">Вспомнил?</span>
         <button class="hfd-g g0" data-act="grade" data-g="0">не помню</button>
         <button class="hfd-g g1" data-act="grade" data-g="1">с трудом</button>
         <button class="hfd-g g2" data-act="grade" data-g="2">уверенно</button>`
      : at.tw
      ? (D.revealed?`Развилка перед глазами — запомни её. Тап — дальше.`
                   :`Назови вслух, чем отличается двойник. Тап — проверить.`)
      : veiled&&!D.revealed
      ? `Прочитай вслух по памяти. Тап — показать, ещё тап — дальше.`
      : `Прочитай вслух. Тап в любом месте — дальше.`}</div>
  </div>`;
}

function doneHTML(){
  const su=SU(D.s)||{ru:""};
  return `<div class="hfd-done">
    <div class="hfd-h">Программа пройдена</div>
    <div class="hfd-sub">${esc(su.ru)} ${D.from}–${D.to} · ${D.prog.length} ${plural(D.prog.length,"повтор","повтора","повторов")}</div>
    <div class="hfd-note2">Отметить эти аяты заученными — они появятся на карте 🗺 и встанут в очередь проверки 🎯.</div>
    <div class="hfd-go">
      <button class="hfd-start" data-act="declare">Отметить заученными</button>
      <button class="hfd-back" data-act="again">Ещё раз</button>
      <button class="hfd-back" data-act="setup">← К настройке</button>
    </div>
  </div>`;
}

function render(){
  if(!D.el)return;
  const box=D.el.querySelector(".hfd-box");if(!box)return;
  box.innerHTML=D.view==="setup"?setupHTML():D.view==="plan"?planHTML():D.view==="done"?doneHTML():runHTML();
  D.el.classList.toggle("running",D.view==="run");
}

// ============================================================
// ДЕЙСТВИЯ
// ============================================================
// ═══ ВОРОТА САМООЦЕНКИ (критерий вместо счётчика) ═══
// Традиционные схемы считают повторы («двадцать раз»), и это их суть — их мы
// не трогаем. Но наука о памяти меряет иначе: занятие кончается не на N-м
// прослушивании, а на успешном воспроизведении БЕЗ подсказки (successive
// relearning). Поэтому у метода есть ось stop:
//   fixed     — программа как собрана, ворот нет (все традиционные схемы);
//   criterion — на каждом повторе «по памяти» спрашиваем, как пошло:
//               «не помню» → добавляем ещё один заход по памяти (до maxExtra),
//               «уверенно» → остаток повторов этого шага снимается.
// Программа при этом остаётся планом: ворота её правят, а не заменяют.
function gateOn(){
  const at=D.prog&&D.prog[D.i];
  if(!at||!D.stop||D.stop.kind!=="criterion")return false;
  if(D.graded)return false;                      // на этом атоме уже ответили
  return showOf(at).p>=1&&at.i>0;                // спрашиваем только «вслепую» и не на первом
}
function stepAtoms(id){let k=0;for(const a of D.prog)if(a.step===id)k++;return k;}
function gate(grade){
  const at=D.prog[D.i];if(!at)return;
  // Шов — записываем наблюдение станка (в своё поле, не в поле экзамена).
  if(ctx.noteJunction&&at.chunk.length>1){
    const f=at.chunk[0],l=at.chunk[at.chunk.length-1];
    if(f.a!==l.a)try{ctx.noteJunction(f.s+":"+f.a,l.s+":"+l.a,grade);}catch(e){}
  }
  D.grades[grade]=(D.grades[grade]||0)+1;
  if(grade===0){
    const extra=(D.extra[at.step]||0);
    if(extra<(D.stop.maxExtra||6)){              // не помню — ещё один заход
      D.extra[at.step]=extra+1;
      D.prog.splice(D.i+1,0,Object.assign({},at,{i:at.of,of:at.of+1,extra:true}));
    }
  }else if(grade===2){                           // уверенно — остаток шага снимаем
    for(let j=D.prog.length-1;j>D.i;j--)if(D.prog[j].step===at.step)D.prog.splice(j,1);
  }
  D.graded=true;stopAudio();step(1);
}

function step(d){
  if(d>0&&D.i>=D.prog.length-1){D.view="done";render();return;}
  D.i=Math.max(0,Math.min(D.prog.length-1,D.i+d));
  D.revealed=false;D.graded=false;D.lw=0;D.lwBad=0;render();
  if(D.pace==="audio")runAudio();               // станок ведёт сам: следующий отрезок
}

async function assemble(){
  const su=SU(D.s)||{n:1};
  let a=Math.max(1,Math.min(su.n,D.from)),b=Math.max(1,Math.min(su.n,D.to));
  if(a>b){const t=a;a=b;b=t;}
  D.from=a;D.to=b;
  D.vks=[];for(let i=a;i<=b;i++)D.vks.push(D.s+":"+i);
  const p=presetById(D.method)||PRESETS[0];
  D.seed=(D.s*1000+a*31+b)>>>0;
  const cfg=cfgOf(p);
  const needPg=cfg.unit&&["page","line","halfpage"].includes(cfg.unit.kind);
  if(needPg&&ctx.loadPages){try{await ctx.loadPages();}catch(e){}}
  if(cfg.unit&&(cfg.unit.kind==="line"||cfg.unit.kind==="halfpage")&&ctx.loadLines){
    try{await ctx.loadLines();}catch(e){}
  }
  await loadWords(D.vks);
  // Близнецы живут в ДРУГИХ сурах — их текст надо подтянуть отдельно, иначе
  // пара соберётся из аята и пустоты.
  if(cfg.twins&&ctx.loadMut){
    try{
      await ctx.loadMut();
      const extra=[];
      for(const vk of D.vks){
        const o=twinOrder(vk)[0];
        if(!o)continue;
        extra.push(o);
        // У дословных близнецов (а в этих данных они ВСЕ дословные) развилка —
        // не в аяте, а в том, что стоит перед ним. Значит нужен и сосед слева.
        const p1=prevVk(vk),p2=prevVk(o);
        if(p1)extra.push(p1);
        if(p2)extra.push(p2);
      }
      if(extra.length)await loadWords([...new Set(extra)]);
    }catch(e){}
  }
  if(p.chan)D.channel=p.chan;                  // пресет может задать отклик (лоух)
  D.stop=cfg.stop||{kind:"fixed"};
  D.prog=build(D.vks,cfg,D.seed);
  D.i=0;D.revealed=false;D.graded=false;D.extra={};D.grades={};
}

function declare(){
  // Уровень декларации — "know": человек НАЖАЛ кнопку, это его свидетельство.
  // Подтверждением оно не становится: подтверждает только проверка 🎯 (слой verified).
  try{ctx.declareRange(D.s,D.from,D.to,"know");}catch(e){}
  D.view="done";
  const box=D.el&&D.el.querySelector(".hfd-done .hfd-note2");
  if(box)box.textContent="Готово: аяты отмечены. Проверка подхватит их по расписанию.";
  const btn=D.el&&D.el.querySelector('[data-act="declare"]');
  if(btn){btn.disabled=true;btn.textContent="Отмечено ✓";}
}

async function onAct(act,el){
  if(act==="method"){
    D.method=el.dataset.id;
    // Шэдоуинг без звука — просто чтение глазами: включаем темп сам, молча,
    // чтобы человек не гадал, почему «синхронно с чтецом» ничего не читает.
    const pm=presetById(D.method);
    if(pm&&pm.needsAudio)D.pace="audio";
    render();return;
  }
  if(act==="veil"){D.veil=el.dataset.v;D.revealed=false;render();return;}
  if(act==="ruku"){rukuTake(+el.dataset.d||0);return;}
  if(act==="page"){pageTake(+el.dataset.d||0);return;}
  if(act==="grade"){gate(+el.dataset.g);return;}
  if(act==="lawh"){D.lastKey=el.dataset.k;lawhKey(el.dataset.k);return;}
  if(act==="chan"){D.channel=el.dataset.v;D.lw=0;D.lwBad=0;render();return;}
  if(act==="setup"){D.view="setup";render();return;}
  if(act==="start"){
    const box=D.el.querySelector(".hfd-box");
    if(box)box.innerHTML=`<div class="hfd-setup"><div class="hfd-sub">Собираю программу…</div></div>`;
    await assemble();D.view="plan";render();return;
  }
  if(act==="run"){D.view="run";render();wake(true);if(D.pace==="audio")runAudio();return;}
  if(act==="again"){D.i=0;D.revealed=false;D.graded=false;D.view="run";render();if(D.pace==="audio")runAudio();return;}
  if(act==="pace"){
    stopAudio();D.pace=el.dataset.v;render();
    if(D.pace==="audio"&&D.view==="run")runAudio();
    return;
  }
  if(act==="declare"){declare();return;}
  if(act==="prev"){step(-1);return;}
  if(act==="close"){close();return;}
}

// ============================================================
// ЖИЗНЕННЫЙ ЦИКЛ
// ============================================================
async function wake(on){
  try{
    D.want=!!on;
    if(on){if(("wakeLock"in navigator)&&!D.wake){D.wake=await navigator.wakeLock.request("screen");
      if(D.wake&&D.wake.addEventListener)D.wake.addEventListener("release",()=>{D.wake=null;});}}
    else if(D.wake){await D.wake.release();D.wake=null;}
  }catch(e){D.wake=null;}
}
document.addEventListener("visibilitychange",()=>{
  if(D.want&&document.visibilityState==="visible"){D.wake=null;wake(true);}
});

export function open(start){
  if(D.open)return;
  if(start&&start.surah){D.s=start.surah;D.from=start.ayah||1;D.to=Math.min((SU(D.s)||{n:1}).n,(start.ayah||1)+4);}
  const st=(ctx.getSettings&&ctx.getSettings())||{};
  if(st.drill&&st.drill.method&&presetById(st.drill.method))D.method=st.drill.method;
  if(st.drill&&st.drill.veil)D.veil=st.drill.veil;
  if(st.drill&&st.drill.pace)D.pace=st.drill.pace;
  if(st.drill&&st.drill.channel)D.channel=st.drill.channel;
  D.open=true;D.view="setup";
  // Отрезки грузим сразу: строка охвата должна быть живой уже на первом экране.
  if(ctx.loadRuku)ctx.loadRuku().then(()=>{if(D.open&&D.view==="setup")render();});
  // Страницы — туда же: строка «Страница» без меты показывала бы прочерк.
  if(ctx.loadPages)ctx.loadPages().then(()=>{if(D.open&&D.view==="setup")render();});
  const el=document.createElement("div");
  el.id="hifzDrill";el.className="hfd";
  el.innerHTML=`<div class="hfd-box"></div>`;
  document.body.appendChild(el);D.el=el;
  document.body.classList.add("hfd-open");

  el.addEventListener("click",e=>{
    const b=e.target.closest("[data-act]");
    if(b){const act=b.dataset.act;if(act!=="noop"&&act!=="sura"&&act!=="from"&&act!=="to"){e.stopPropagation();onAct(act,b);}return;}
    if(D.view!=="run")return;
    if(D.playing){stopAudio();render();return;}             // тап во время звука — оборвать
    if(lawhOn())return;                                     // лоух: листаем набором, не тапом
    const cur=D.prog[D.i];
    if(cur&&cur.tw&&!D.revealed){D.revealed=true;render();return;}  // пара: тап открывает двойника
    const {p}=showOf(cur||{show:"text",i:0,of:1});
    if(p>0&&!D.revealed){D.revealed=true;render();return;}  // вуаль: первый тап раскрывает
    if(gateOn())return;                                     // ворота: листаем только ответом
    step(1);
  });
  el.addEventListener("change",e=>{
    const t=e.target;if(!t.dataset)return;
    if(t.dataset.act==="sura"){D.s=+t.value;D.from=1;D.to=Math.min((SU(D.s)||{n:1}).n,5);render();}
    else if(t.dataset.act==="from")D.from=+t.value||1;
    else if(t.dataset.act==="to")D.to=+t.value||1;
  });
  render();
}

export function close(viaBack){
  if(!D.open)return;
  D.open=false;wake(false);stopAudio();
  try{if(ctx.setSettings)ctx.setSettings({drill:{method:D.method,veil:D.veil,pace:D.pace,channel:D.channel}});}catch(e){}
  document.body.classList.remove("hfd-open");
  if(D.el){D.el.remove();D.el=null;}
  if(!viaBack&&ctx.consumeOverlay)ctx.consumeOverlay();
}

// Клавиши: пробел/→/Enter — дальше, ← — назад, Esc — выход.
export function onKey(e){
  if(!D.open)return false;
  if(e.key==="Escape"){close();return true;}
  if(D.view!=="run")return false;
  if(gateOn()&&(e.key==="1"||e.key==="2"||e.key==="3")){
    e.preventDefault();gate(+e.key-1);return true;          // 1/2/3 — не помню / с трудом / уверенно
  }
  if(e.key===" "||e.key==="Enter"||e.key==="ArrowLeft"){
    e.preventDefault();
    const cur=D.prog[D.i];
    if(cur&&cur.tw&&!D.revealed){D.revealed=true;render();return true;}
    const {p}=showOf(cur||{show:"text",i:0,of:1});
    if(p>0&&!D.revealed){D.revealed=true;render();return true;}
    if(gateOn())return true;
    step(1);
    return true;
  }
  if(e.key==="ArrowRight"){e.preventDefault();step(-1);return true;}
  return false;
}

// Только для отладки в консоли: собрать программу и посмотреть её списком.
export async function debugBuild(s,from,to,methodId){
  const vks=[];for(let i=from;i<=to;i++)vks.push(s+":"+i);
  const p=presetById(methodId)||PRESETS[0];
  const cfg=cfgOf(p);
  await loadWords(vks);
  // Подготовку повторяем ЗА assemble: без неё «Близнецы» отсюда собирались
  // пустыми (двойники живут в других сурах, их текст не загружен), и отладка
  // врала бы на ровном месте. Меняешь подготовку в assemble — поправь и здесь.
  if(cfg.twins&&ctx.loadMut){
    try{
      await ctx.loadMut();
      const extra=[];
      for(const vk of vks){
        const o=twinOrder(vk)[0];
        if(!o)continue;
        extra.push(o);
        const p1=prevVk(vk),p2=prevVk(o);
        if(p1)extra.push(p1);
        if(p2)extra.push(p2);
      }
      if(extra.length)await loadWords([...new Set(extra)]);
    }catch(e){}
  }
  if(cfg.unit&&["page","line","halfpage"].includes(cfg.unit.kind)){
    if(ctx.loadPages){try{await ctx.loadPages();}catch(e){}}
    if(ctx.loadLines&&cfg.unit.kind!=="page"){try{await ctx.loadLines();}catch(e){}}
  }
  const prog=build(vks,cfg,1);
  return prog.map((a,i)=>i+" "+chunkLabel(a.chunk)+" ["+a.show+"] "+(a.link?"связка":"")+(a.tw?" пара↔"+a.tw:""));
}
