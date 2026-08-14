#!/usr/bin/env python3
"""
Скелет «краткого тафсира» ат-Табари — сырьё для русского tabari_ru.

Зачем: полный «Джами' аль-баян» — ~36 МБ (≈18M токенов), переводить его целиком
незачем. Нам нужно ровно то, что говорит САМ Табари: его перифраза аята
(«يقول تعالى ذكره: …» — по сути его перевод Корана на арабский) и его тарджих
(«وأولى الأقوال في ذلك بالصواب عندنا…»). Предания с иснадами, шавахид-поэзия,
грамматическая полемика и такхридж редактора в скелет НЕ идут — это ~86% объёма.

Как отделяется речь Табари (два независимых признака, оба нужны):
  1) МАРКЕР ИЗДАНИЯ «قال أبو جعفر:» — в томах Шакира каждая авторская реплика
     помечена явно. Признак железный, но покрывает не весь мусхаф (в поздних
     томах другое издание) — поэтому не единственный.
  2) ФОРМУЛЫ. Перифраза: يقول تعالى ذكره / يعني بذلك / وتأويل ذلك / فمعنى الكلام.
     Тарджих: وأولى الأقوال / والصواب من القول / وإذ كان ذلك كذلك.
  Отсев: иснад (حدثنا/حدثني/⁕/номер), «ذكر من قال ذلك», такхридж редактора
  (وذكره السيوطي / ورواه أحمد), примечания [[…]].

Сегментация по фрагментам аята: заголовок «القول في تأويل قوله …: ﴿…﴾» либо
«وقوله: ﴿…﴾» начинает новый фрагмент, к нему привязываются перифраза и тарджих.

Флаги (что переводчику придётся смотреть в полном tabari_ar):
  no_para   — у аята не нашлось ни перифразы, ни итоговой формулы;
  ikhtilaf_no_tarjih — заявлено разногласие (اختلف أهل التأويل), а тарджих не найден;
  empty     — в кеше нет текста.

Вход:  data/_sources/tabari_ar/<sura>/<ayah>.json (build_tabari_ar.py --fetch)
Выход: data/_sources/tabari_ru/skeleton/<sura>.json = {"<ayah>": {frags, flags}}

Использование:
  python3 build_tabari_skeleton.py --dump 5:38 2:2      # скелет аята целиком (для перевода)
  python3 build_tabari_skeleton.py --dump 2:1-10       # диапазон
  python3 build_tabari_skeleton.py --report             # статистика по корпусу
  python3 build_tabari_skeleton.py --build [1 2 3]      # записать скелет (все суры/список)
"""
import os, re, sys, json

ROOT = os.path.dirname(os.path.abspath(__file__))
ARABIC_DIR = os.path.join(ROOT, "data", "tafsirs", "_arabic")
CACHE = os.path.join(ROOT, "data", "_sources", "tabari_ar")
OUT = os.path.join(ROOT, "data", "_sources", "tabari_ru", "skeleton")

SELF = "قال أبو جعفر"                       # маркер авторской речи (издание Шакира)

# Диакритика: текст Табари частично огласован («والصَّوابُ»), поэтому и абзацы,
# и сами формулы приводятся к одной орфографии — иначе «تأويل» никогда не совпадёт
# с нормализованным «تاويل», и половина перифраз уходит в «прочее».
DIACR = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")


def norm(s):
    s = DIACR.sub("", s)
    return (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
             .replace("ٱ", "ا").replace("ى", "ي").replace("ة", "ه"))


def RX(pattern):
    """Регэксп по арабским формулам — компилируется в нормализованной орфографии."""
    return re.compile(norm(pattern))


ISNAD = RX(r"^\s*(?:[⁕*•]|[٠-٩\d]+\s*[-‐‑–]|حدثنا|حدثني|ثنا |ثني |أخبرنا|أخبرني|"
                   r"ذكر من قال|وذكر من قال|ذكر الرواية|وبنحو (?:الذي|ما) قلنا|وبمثل الذي قلنا|"
                   r"وبما قلنا|وقد روي عن|وروي عن)")
TAKHRIJ = RX(r"^\s*(?:وذكره|ونقله|ورواه|فرواه|وأخرجه|والحديث|وهذا الحديث|وانظر)")
# Чужая речь: «сказал такой-то…» — мнение, а не голос Табари.
OTHERS = RX(r"^\s*(?:و?قال (?:بعضهم|آخرون|بعض|أبو|ابن|مجاهد|قتادة)|و?كان (?:ابن|مجاهد|"
                    r"بعض|أبو)|فقال (?:بعضهم|آخرون)|و?زعم)")
# Полемика: вопрос воображаемого оппонента и ответ на него. Формула толкования
# внутри такого абзаца — часть спора, а не перифраза аята.
DISCUSS = RX(r"^\s*(?:فإن قال|وإن قال|فإن قيل|قيل\s*:|قيل له|وقد ظن|وقد زعم|فقال قائل|"
             r"وقد دللنا|وقد بينا|والشواهد|كما قال الشاعر|وأما نحويو|وكان بعض نحويي)")
PARA = RX(r"(يقول تعالى ذكره|يعني (?:تعالى ذكره|بذلك جل ثناؤه|بذلك|جل ثناؤه|بقوله|به)|"
                  r"وهذا خبر من|فإنه يعني|فإن معناه|"
                  r"تأويل (?:ذلك|قول|قوله)|معنى (?:ذلك|قوله|قول|الكلام|الايه)|"
                  r"يقول (?:جل ثناؤه|عز وجل|تعالى)|فتاويل ذلك)")
TARJIH = RX(r"(اولى (?:هذه |هذين |تلك |هذا )?(?:الاقوال|التاويلين|التاويلات|القولين|القراءتين|ذلك|الامرين|بالصواب|"
                    r"بتاويل)|الصواب (?:من القول|في ذلك|عندنا|عندي)|"
                    r"واذ كان ذلك كذلك|فتاويل (?:الكلام|الايه) اذا?|اشبه (?:القولين|بتاويل)|"
                    r"والذي هو اولى|ونحن نختار|واولى بالصواب)")
# Итоговая формула Табари: «فتأويل الكلام إذًا: …» — по сути его перевод аята.
FINAL = RX(r"^\s*(?:ف?يكون )?(?:ف|و)?(?:تاويل|معني) (?:الكلام|الايه|ذلك|هذه الايه)"
                   r"(?: اذا| اذ| حينئذ)?\s*[:،]")
IKHTILAF = RX(r"(اختلف (?:اهل التاويل|القراه|القرءه|اهل العربيه)|اختلفت (?:القراه|تراجمه))")
HEAD = RX(r"^\s*(?:و?القول في تأويل قول[^«\"﴿]{0,60}|"
          r"(?:وقوله|وأما قوله|فأما قوله|ثم قال)(?: تعالى| جل ثناؤه| عز وجل)?\s*:?)\s*[«\"﴿]")
QUOTE = re.compile(r"[﴿\"«]([^﴾\"»]{1,400})[﴾\"»]")
NOTE = re.compile(r"\[\[.+?\]\]", re.S)
def ayah_counts():
    c = {}
    for su in range(1, 115):
        with open(os.path.join(ARABIC_DIR, f"{su}.json"), encoding="utf-8") as f:
            c[su] = max(int(k) for k in json.load(f))
    return c


def raw(su, ay):
    p = os.path.join(CACHE, str(su), f"{ay}.json")
    if not (os.path.isfile(p) and os.path.getsize(p) > 2):
        return None
    try:
        return (json.load(open(p, encoding="utf-8")).get("text") or "").strip() or None
    except Exception:
        return None


def paragraphs(text):
    """Абзацы без редакторских [[…]] и строк-разделителей."""
    out = []
    for p in NOTE.sub("", text).split("\n\n"):
        p = re.sub(r"\s+", " ", p).strip(" \t*_-–—")
        if len(p) > 1:
            out.append(p)
    return out


def classify(p):
    """→ ('head'|'para'|'tarjih'|'skip'|'other', текст без маркера автора)."""
    body = p
    mine = body.startswith(SELF)
    if mine:                                   # снять «قال أبو جعفر:»
        body = re.sub(r"^قال أبو جعفر\s*:?\s*", "", body)
    n = norm(body)
    if HEAD.match(n):
        return "head", body
    if not mine and (ISNAD.match(n) or TAKHRIJ.match(n)):
        return "skip", body
    # окно зачина: цитаты ﴿…﴾ схлопнуты, иначе длинный аят выталкивает формулу
    probe = QUOTE.sub("◆", body)
    probe = norm(re.sub(r"\s+", " ", probe))[:110]
    head = n[:260]
    if FINAL.match(n):
        return "final", body
    if TARJIH.search(head):
        return "tarjih", body
    if OTHERS.match(head) or DISCUSS.match(head):   # чужое мнение / полемика
        return "other", body
    if PARA.search(probe):                          # формула — в зачине абзаца
        return "para", body
    return "other", body


def extract(su, ay):
    text = raw(su, ay)
    if not text:
        return {"frags": [], "flags": ["empty"]}
    frags, cur = [], None
    ikhtilaf = False
    pending = False        # последнее слово Табари оборвано на «كما:-» → дальше асар
    for p in paragraphs(text):
        kind, body = classify(p)
        if IKHTILAF.search(norm(body)[:260]):
            ikhtilaf = True
        if kind == "skip" and pending and cur is not None:
            # Табари сказал «и толкование этого — как у Ибн Аббаса, а именно:-»
            # и передал слово преданию: без него его собственная мысль обрывается.
            if len(cur.get("athar", [])) < 2:
                cur.setdefault("athar", []).append(body[:900])
            pending = False
            continue
        if kind == "head":
            m = QUOTE.search(body)
            cur = {"q": (m.group(1).strip() if m else ""), "para": [], "final": [], "tarjih": []}
            frags.append(cur)
            pending = False
            # «وقوله: ﴿…﴾ يقول: …» — заголовок и перифраза в одном абзаце
            tail = body[m.end():].strip(" :.،") if m else ""
            if tail and PARA.search(tail[:220]):
                cur["para"].append(tail)
            continue
        if kind in ("para", "final", "tarjih"):
            if cur is None:
                cur = {"q": "", "para": [], "final": [], "tarjih": []}
                frags.append(cur)
            cur[kind].append(body)
            pending = bool(re.search(r"[:：]\s*[-‐‑–]?\s*$", body))
    frags = [f for f in frags if f["para"] or f["final"] or f["tarjih"] or f["q"]]
    # gap — у фрагмента есть цитата, но толкование Табари формулами не поймалось
    # (он изложил его повествовательно). Переводчик дочитывает полный tabari_ar.
    for f in frags:
        if not (f["para"] or f["final"] or f["tarjih"]):
            f["gap"] = True
    flags = []
    if not any(f["para"] or f["final"] for f in frags):
        flags.append("no_para")
    if ikhtilaf and not any(f["tarjih"] for f in frags):
        flags.append("ikhtilaf_no_tarjih")
    return {"frags": frags, "flags": flags}


def build(suras):
    os.makedirs(OUT, exist_ok=True)
    counts = ayah_counts()
    stat = {"ayat": 0, "no_para": 0, "ikhtilaf_no_tarjih": 0, "empty": 0, "chars": 0, "full": 0}
    for su in suras:
        chunk = {}
        for ay in range(1, counts[su] + 1):
            r = extract(su, ay)
            r["full"] = len(raw(su, ay) or "")     # объём полного тафсира аята
            chunk[str(ay)] = r
            stat["ayat"] += 1
            for f in r["flags"]:
                stat[f] = stat.get(f, 0) + 1
            stat["chars"] += sum(len(x) for fr in r["frags"]
                                 for x in fr["para"] + fr["final"] + fr["tarjih"]
                                 + fr.get("athar", []))
            stat["full"] += r["full"]
            stat["gaps"] = stat.get("gaps", 0) + sum(1 for f in r["frags"] if f.get("gap"))
        with open(os.path.join(OUT, f"{su}.json"), "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, separators=(",", ":"))
    pct = 100 * stat["chars"] / stat["full"] if stat["full"] else 0
    print(f"сур: {len(suras)}, аятов: {stat['ayat']}, скелет {stat['chars']/1e6:.2f} МБ "
          f"из {stat['full']/1e6:.2f} МБ ({pct:.0f}%)")
    print(f"  без перифразы: {stat['no_para']}   разногласие без тарджиха: "
          f"{stat['ikhtilaf_no_tarjih']}   пусто в кеше: {stat['empty']}")
    print(f"  фрагментов с пробелом (дочитать полный текст): {stat.get('gaps', 0)}")


def expand(refs):
    """«2:1-10» → 2:1 … 2:10."""
    out = []
    for ref in refs:
        su, _, ays = ref.partition(":")
        if "-" in ays:
            a, b = ays.split("-")
            out += [f"{su}:{i}" for i in range(int(a), int(b) + 1)]
        else:
            out.append(ref)
    return out


def dump(refs):
    for ref in expand(refs):
        su, ay = (int(x) for x in ref.split(":"))
        r = extract(su, ay)
        print(f"\n{'='*60}\n{su}:{ay}  флаги={r['flags'] or '—'}  фрагментов={len(r['frags'])}")
        for i, f in enumerate(r["frags"], 1):
            print(f"\n [{i}] ﴿{f['q']}﴾")
            for x in f["para"]:
                print(f"   ПЕРИФРАЗА: {x}")
            for x in f["final"]:
                print(f"   ИТОГ:      {x}")
            for x in f["tarjih"]:
                print(f"   ТАРДЖИХ:   {x}")
            for x in f.get("athar", []):
                print(f"   АСАР:      {x}")


def main():
    a = sys.argv[1:]
    if a and a[0] == "--dump":
        dump(a[1:]); return
    if a and a[0] == "--build":
        rest = [int(x) for x in a[1:]]
        build(rest or list(range(1, 115))); return
    if a and a[0] == "--report":
        counts = ayah_counts()
        have = [su for su in range(1, 115)
                if os.path.isdir(os.path.join(CACHE, str(su)))
                and len(os.listdir(os.path.join(CACHE, str(su)))) >= counts[su]]
        print(f"полностью в кеше сур: {len(have)}")
        build(have); return
    print(__doc__)


if __name__ == "__main__":
    main()
