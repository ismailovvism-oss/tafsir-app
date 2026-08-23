#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_erudit_pool.py — служебные данные модуля «🎓 Эрудит» (упражнение «Аяты»).

Зачем. Упражнение спрашивает «из какой это суры?». Но 169 аятов дословно
повторяются В РАЗНЫХ сурах (муката'ат «حم» в 40–46, «فَبِأَيِّ آلَاءِ رَبِّكُمَا»
и т. п.) — у такого вопроса нет одного честного ответа, и предъявлять его нельзя.
Повторы ВНУТРИ одной суры безобидны: ответ всё равно один.

Определить это можно только глядя на весь Коран сразу, а модуль грузит суры
чанками по требованию — поэтому список считается заранее, здесь.

Результат 1: data/erudit/pool.json — для упражнения «Аяты»
    {"ambiguous": ["2:1", ...],            # плоский список — для быстрой проверки
     "groups": [["40:1","41:1",...], ...]} # группы ДОСЛОВНО одинаковых текстов
                                           # (упражнение «Узнать суру», вид «лишняя сура»)

Результат 2: data/erudit/suras.json — для упражнения «Узнать суру»
    {"uniq":   [{"r":корень,"s":сура,"n":вхождений,"g":глосс,"f":форма,"a":аят}, ...],
     "topics": [{"t":название,"s":сура,"n":аятов,"a":аят}, ...],
     "mut":    [[{"s":сура,"a":аят,"d":[отличающиеся слова]}, ...], ...],
     "phrases":[{"p":оборот,"a":[{"s":сура,"a":аят,"t":концовка}, ...]}, ...]}

  uniq   — корни, ВСЕ вхождения которых лежат в одной суре (كهف «пещера» → 18):
           считается из конкорданса data/wbw/roots.json (build_concordance.py).
  topics — темы фихриста, сосредоточенные в одной суре: data/topics (build_topics.py).
  mut    — МУТАШАБИХАТ: почти одинаковые аяты из РАЗНЫХ сур (2:39 «أصحاب النار» и
           5:10 «أصحاب الجحيم»). Дословные повторы сюда не идут — они в pool.json.
           "d" — слова, которыми аят отличается от остальных в группе; из них
           строится разбор («вот чем они и различаются»).
  phrases— ПОВТОРЯЮЩИЙСЯ ОБОРОТ: одинаковое начало, разные концовки. وَمَآ أَدْرَىٰكَ مَا
           стоит в 12 местах, и путаются не в обороте, а в том, чем каждое место
           кончается. Ось отдельная: детектор mut сравнивает аяты ЦЕЛИКОМ и такие
           группы либо дробит, либо теряет.

Сети не требует, идемпотентен. Зависит от сборок: build_concordance.py,
build_topics.py. Арабские имена сур берутся из литерала SURAHS в index.html
(единственное место, где они есть) — только чтобы отсеять вопросы-подсказки.
"""
import json, os, re, collections, difflib

SRC = "data/tafsirs/_arabic.json"
ROOTS = "data/wbw/roots.json"
TOPIC_V = "data/topics/verses.json"
TOPIC_T = "data/topics/tree.json"
TOPIC_RU = "data/topics/names_ru.json"
INDEX_HTML = "index.html"
OUT_DIR = "data/erudit"
OUT = os.path.join(OUT_DIR, "pool.json")
OUT2 = os.path.join(OUT_DIR, "suras.json")

# Сравниваем БЕЗ огласовок и с унификацией алифов/йа/та-марбуты: иначе
# «حم» в разных сурах разошлись бы по мелким различиям записи и остались бы
# в пуле как якобы уникальные.
DIAC = re.compile(r"[ً-ْٰٓ-ٕـۖ-ۭ]")


def norm(t: str) -> str:
    t = DIAC.sub("", t)
    t = re.sub(r"[آأإٱ]", "ا", t).replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------
# Имена сур. Живут только в литерале SURAHS в index.html; нужны здесь,
# чтобы выбросить вопросы, где ответ написан в самом вопросе (корень كهف
# при ответе «Аль-Кахф», тема «Юсуф» при ответе «Юсуф»).
# ------------------------------------------------------------------
SU_RE = re.compile(r'\{id:(\d+),name:"([^"]+)",ru:"([^"]+)",n:(\d+)\}')
RU_ART = re.compile(r"^(аль|ан|ас|ат|аз|ар|аш|ад)[-\s]", re.I)


def load_surahs():
    with open(INDEX_HTML, encoding="utf-8") as f:
        html = f.read()
    out = {}
    for m in SU_RE.finditer(html):
        out[int(m.group(1))] = {"ar": norm(m.group(2)), "ru": m.group(3)}
    if len(out) != 114:
        raise SystemExit(f"SURAHS в {INDEX_HTML}: разобрано {len(out)} из 114")
    return out


def ru_key(s: str) -> str:
    s = str(s or "").lower().replace("ё", "е")
    s = RU_ART.sub("", s)
    return re.sub(r"[-\s'’]", "", s)


# ------------------------------------------------------------------
# uniq — корни, все вхождения которых в одной суре
# ------------------------------------------------------------------
def build_uniq(surahs):
    with open(ROOTS, encoding="utf-8") as f:
        roots = json.load(f)
    out = []
    for root, d in roots.items():
        suras, first = set(), None
        for form, addr in d["f"]:
            for a in addr.split():
                s = int(a.split(":")[0])
                suras.add(s)
                if first is None:
                    first = a
            if len(suras) > 1:
                break
        if len(suras) != 1:
            continue
        sid = suras.pop()
        gloss = (d.get("g") or [None])[0]
        if not gloss:                                     # без русского смысла вопрос не задать
            continue
        # Корень внутри арабского имени суры — ответ подсказан вопросом.
        if norm(root) and norm(root) in surahs[sid]["ar"]:
            continue
        out.append({"r": root, "s": sid, "n": d["n"], "g": gloss,
                    "f": d["f"][0][0], "a": int(first.split(":")[1])})
    out.sort(key=lambda x: (-x["n"], x["s"]))
    return out


# ------------------------------------------------------------------
# topics — темы фихриста, сосредоточенные в одной суре
# ------------------------------------------------------------------
MIN_AYAHS = 4          # тема из 2–3 аятов случайна: попасть в неё может любая сура
MIN_SHARE = 0.75       # ниже — тема размазана по Корану, честного ответа нет


def topic_labels():
    """id → «Родитель › Тема»: одни листья («со своим народом») без ветки немы."""
    with open(TOPIC_T, encoding="utf-8") as f:
        tree = json.load(f)
    lab = {}

    def walk(nodes, parent):
        for nd in nodes:
            name = nd.get("name") or ""
            lab[str(nd["id"])] = f"{parent} › {name}" if parent else name
            walk(nd.get("children") or [], name)

    walk(tree, "")
    return lab


def build_topics(surahs):
    with open(TOPIC_V, encoding="utf-8") as f:
        verses = json.load(f)
    lab = topic_labels()
    out = []
    for tid, ayahs in verses.items():
        if len(ayahs) < MIN_AYAHS:
            continue
        cnt = collections.Counter(int(a.split(":")[0]) for a in ayahs)
        sid, n = cnt.most_common(1)[0]
        if n / len(ayahs) < MIN_SHARE:
            continue
        name = lab.get(tid) or ""
        if not name:
            continue
        # Имя суры внутри названия темы — ответ подсказан вопросом.
        if ru_key(surahs[sid]["ru"]) in ru_key(name):
            continue
        first = min((a for a in ayahs if int(a.split(":")[0]) == sid),
                    key=lambda a: int(a.split(":")[1]))
        out.append({"t": name, "s": sid, "n": n, "a": int(first.split(":")[1])})
    out.sort(key=lambda x: (-x["n"], x["s"]))
    return out


# ------------------------------------------------------------------
# mut — муташабихат: почти одинаковые аяты из разных сур
# ------------------------------------------------------------------
BASMALA = norm("بسم الله الرحمن الرحيم")
MIN_W, MAX_W = 3, 45   # 3 слова — предел: «وجوه يومئذ ناضرة» и «…خاشعة» это уже муташабих
DF_MAX = 250           # слово в 250+ аятах ничего не сужает, в кандидаты по нему не ходим
SHARE = 0.40           # доля общих редких слов, чтобы вообще считать похожесть
MIN_RARE = 1           # ...но у КОРОТКОГО аята общим редким может быть одно слово: в
                       # «وما أدرىك ما الطارق» редко только «أدرىك», остальное — ما/وما,
                       # они частотны и в кандидаты не ведут. Прежний пол в 3 слова
                       # выбрасывал весь этот пласт — самый ходовой в джузе 30.
MIN_SHARED = 2         # зато общих слов ЛЮБЫХ должно быть минимум два: иначе пара из
                       # трёхсловных аятов проходит по одному совпадению
RATIO = 0.62           # ниже — уже не «похожие аяты», а общая тема


def ayah_tokens(text):
    """Токены аята: (нормализованный, как в мусхафе). Знаки вакфа отбрасываются
    — они не слова, но стоят в тексте отдельно и сбивали бы выравнивание."""
    toks = []
    for w in str(text).split():
        n = norm(w)
        if n:
            toks.append((n, w))
    return toks


def build_mut(quran, ambiguous):
    amb = set(ambiguous)
    items = []                                            # (ключ, сура, [норм], [ориг])
    for sura, ayahs in quran.items():
        for ayah, text in ayahs.items():
            toks = ayah_tokens(text)
            nw = [t[0] for t in toks]
            # У первого аята суры басмала входит в текст: без её отсечения ВСЕ
            # первые аяты оказались бы «похожими» друг на друга.
            bas = BASMALA.split()
            if nw[:len(bas)] == bas:
                toks = toks[len(bas):]
            items.append((f"{sura}:{ayah}", int(sura),
                          [t[0] for t in toks], [t[1] for t in toks]))

    inv = collections.defaultdict(list)
    for i, (k, s, nw, ow) in enumerate(items):
        for w in set(nw):
            inv[w].append(i)
    df = {w: len(v) for w, v in inv.items()}

    pairs = []
    for i, (k, s, nw, ow) in enumerate(items):
        if k in amb or not (MIN_W <= len(nw) <= MAX_W):
            continue
        cnt = collections.Counter()
        for w in set(nw):
            if df[w] > DF_MAX:
                continue
            for j in inv[w]:
                if j > i:
                    cnt[j] += 1
        need = max(MIN_RARE, int(SHARE * len(nw)))
        for j, c in cnt.items():
            if c < need:
                continue
            k2, s2, nw2, ow2 = items[j]
            if s2 == s or k2 in amb or not (MIN_W <= len(nw2) <= MAX_W):
                continue
            if abs(len(nw) - len(nw2)) > max(4, 0.4 * len(nw)):
                continue
            if len(set(nw) & set(nw2)) < MIN_SHARED:
                continue
            if difflib.SequenceMatcher(None, nw, nw2).ratio() >= RATIO:
                pairs.append((k, k2))

    # Похожесть транзитивна не строго (A~B, B~C, A≁C), но для вопроса «из какой
    # суры» это и не нужно: все члены группы — честные соперники по варианту.
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_root = collections.defaultdict(list)
    for x in parent:
        by_root[find(x)].append(x)

    def akey(k):
        s, a = k.split(":")
        return (int(s), int(a))

    tok = {it[0]: (it[2], it[3]) for it in items}
    groups = []
    for members in by_root.values():
        members = sorted(members, key=akey)
        if len({k.split(":")[0] for k in members}) < 2:
            continue
        common = set.intersection(*[set(tok[k][0]) for k in members])
        g = []
        for k in members:
            s, a = k.split(":")
            nw, ow = tok[k]
            seen, diff = set(), []
            for n, o in zip(nw, ow):
                if n in common or n in seen:
                    continue
                seen.add(n)
                diff.append(o)
            g.append({"s": int(s), "a": int(a), "d": diff[:6]})
        groups.append(g)
    groups.sort(key=lambda g: (-len(g), g[0]["s"], g[0]["a"]))
    return groups


# ------------------------------------------------------------------
# phrases — ПОВТОРЯЮЩИЙСЯ ОБОРОТ: одинаковое начало, разные концовки
# ------------------------------------------------------------------
# Ось, которой муташабихат-детектор не берёт. Он сравнивает аяты ЦЕЛИКОМ, а тут
# важно другое: оборот وَمَآ أَدْرَىٰكَ مَا стоит в 12 местах, и заучивший помнит
# сам оборот — путается он в том, ЧЕМ КОНЧАЕТСЯ каждое место (سِجِّينٌ? عِلِّيُّونَ?
# ٱلطَّارِقُ?). Поэтому храним не «похожие аяты», а оборот + хвост каждого места.
TAIL_MAX = 4           # хвост длиннее — вопрос уже не «чем кончается», а «вспомни аят»
HEAD_SHARE = 0.45      # оборот должен быть ОСНОВОЙ аята, иначе это просто частая связка
MIN_PLACES = 3         # два места — это пара, а не оборот


def build_phrases(quran):
    tok = {}
    bas = BASMALA.split()
    for sura, ayahs in quran.items():
        for ayah, text in ayahs.items():
            t = ayah_tokens(text)
            if [x[0] for x in t][:len(bas)] == bas:
                t = t[len(bas):]
            tok[f"{sura}:{ayah}"] = t

    heads = collections.defaultdict(set)
    for k, t in tok.items():
        nw = [x[0] for x in t]
        for n in range(2, len(nw)):                       # хвост непустой
            if len(nw) - n > TAIL_MAX or n < HEAD_SHARE * len(nw):
                continue
            heads[" ".join(nw[:n])].add(k)

    def akey(k):
        s, a = k.split(":")
        return (int(s), int(a))

    found = {}
    for head, places in heads.items():
        n = len(head.split())
        tails = {k: " ".join(x[0] for x in tok[k][n:]) for k in places}
        # Одинаковые хвосты — это дословный повтор, он живёт в pool.json; здесь
        # нужен РАЗНОБОЙ концовок, иначе выбирать не из чего.
        if len(tails) < MIN_PLACES or len(set(tails.values())) < MIN_PLACES:
            continue
        if len({k.split(":")[0] for k in tails}) < 2:
            continue
        found[head] = tails

    # Оставляем самый ДЛИННЫЙ оборот: короткий, дающий те же места, ничего не
    # добавляет («وما أدرىك» при наличии «وما أدرىك ما»).
    out = []
    for head, tails in sorted(found.items(), key=lambda x: -len(x[0].split())):
        if any(h.startswith(head + " ") and set(tails) <= set(t) for h, t in out):
            continue
        out.append((head, tails))

    res = []
    for head, tails in out:
        n = len(head.split())
        keys = sorted(tails, key=akey)
        first = tok[keys[0]]
        res.append({
            "p": " ".join(x[1] for x in first[:n]),       # оборот как в мусхафе
            "a": [{"s": int(k.split(":")[0]), "a": int(k.split(":")[1]),
                   "t": " ".join(x[1] for x in tok[k][n:])} for k in keys],
        })
    res.sort(key=lambda x: (-len(x["a"]), x["a"][0]["s"]))
    return res


def main():
    with open(SRC, encoding="utf-8") as f:
        quran = json.load(f)

    by_text = collections.defaultdict(list)
    for sura, ayahs in quran.items():
        for ayah, text in ayahs.items():
            by_text[norm(text)].append((int(sura), int(ayah)))

    groups = []
    for keys in by_text.values():
        if len({s for s, _ in keys}) > 1:                 # межсурный повтор
            groups.append([f"{s}:{a}" for s, a in sorted(keys)])
    groups.sort(key=lambda g: (-len(g), g[0]))

    ambiguous = sorted({k for g in groups for k in g},
                       key=lambda k: (int(k.split(":")[0]), int(k.split(":")[1])))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"ambiguous": ambiguous, "groups": groups}, f,
                  ensure_ascii=False, separators=(",", ":"))

    print(f"групп межсурных повторов: {len(groups)}")
    print(f"аятов исключено из «какая сура»: {len(ambiguous)}")
    print(f"→ {OUT} ({os.path.getsize(OUT)} байт)")

    # ---- данные упражнения «Узнать суру» ----
    surahs = load_surahs()
    uniq = build_uniq(surahs)
    topics = build_topics(surahs)
    mut = build_mut(quran, ambiguous)
    phrases = build_phrases(quran)
    with open(OUT2, "w", encoding="utf-8") as f:
        json.dump({"uniq": uniq, "topics": topics, "mut": mut, "phrases": phrases}, f,
                  ensure_ascii=False, separators=(",", ":"))

    print(f"корней ровно в одной суре: {len(uniq)} "
          f"(сур: {len({x['s'] for x in uniq})})")
    print(f"тем, сосредоточенных в одной суре: {len(topics)} "
          f"(сур: {len({x['s'] for x in topics})})")
    print(f"групп муташабихат: {len(mut)}, аятов в них: {sum(len(g) for g in mut)}")
    print(f"повторяющихся оборотов: {len(phrases)}, "
          f"мест в них: {sum(len(p['a']) for p in phrases)}")
    print(f"→ {OUT2} ({os.path.getsize(OUT2)} байт)")


if __name__ == "__main__":
    main()
