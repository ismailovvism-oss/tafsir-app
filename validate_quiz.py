#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_quiz.py — проверка банка вопросов «Лестницы знания» (data/quiz/*.json).

Что проверяет:
  • структура записи: обязательные поля, ровно 4 варианта, индекс ответа в границах;
  • уникальность id по всему банку;
  • категория вопроса объявлена в meta-списке категорий файла;
  • уровень 1..5;
  • ссылка ref («сура:аят» или «сура:аят-аят») существует в Коране — сверяется с
    data/tafsirs/_arabic.json, а не с формальным диапазоном;
  • варианты ответа не повторяются внутри вопроса (иначе есть два верных);
  • пустые why/src — банк без обоснования вычитывать нельзя.

Отдельно печатает СВОДКУ по вычитке: сколько записей с reviewed:true в каждой
категории. Именно reviewed:true — единственное, что приложению разрешено
показывать; сгенерированный, но не вычитанный вопрос по тафсиру или фикху в
выдачу попадать не должен.

Идемпотентен, сети не требует. Запуск: python3 validate_quiz.py
"""
import json, os, re, sys, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
QUIZ = os.path.join(ROOT, "data", "quiz")
QURAN = os.path.join(ROOT, "data", "tafsirs", "_arabic.json")

REF_RE = re.compile(r"^(\d{1,3}):(\d{1,3})(?:-(\d{1,3}))?$")
REQUIRED = ("id", "cat", "level", "q", "opts", "a", "why", "ref", "src", "reviewed")


def load_quran():
    with open(QURAN, encoding="utf-8") as f:
        q = json.load(f)
    return {int(s): {int(a) for a in ayahs} for s, ayahs in q.items()}


def check_ref(ref, quran, errs, qid):
    if not ref:
        return                                  # ссылка не обязательна: часть вопросов не привязана к аяту
    m = REF_RE.match(ref)
    if not m:
        errs.append(f"{qid}: ref «{ref}» не разобран (ожидается «2:255» или «2:1-5»)")
        return
    s, a1 = int(m.group(1)), int(m.group(2))
    a2 = int(m.group(3)) if m.group(3) else a1
    if s not in quran:
        errs.append(f"{qid}: в ref «{ref}» нет суры {s}")
        return
    for a in (a1, a2):
        if a not in quran[s]:
            errs.append(f"{qid}: в ref «{ref}» нет аята {s}:{a}")
    if a2 < a1:
        errs.append(f"{qid}: в ref «{ref}» конец диапазона меньше начала")


def main():
    if not os.path.isdir(QUIZ):
        print("Каталога data/quiz нет — банк ещё не создан.")
        return 0
    quran = load_quran()
    files = sorted(f for f in os.listdir(QUIZ) if f.endswith(".json"))
    if not files:
        print("В data/quiz нет json-файлов.")
        return 0

    errs, seen_ids = [], {}
    total = reviewed_total = disputed_total = 0
    per_file = []

    for fname in files:
        path = os.path.join(QUIZ, fname)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        cats = {c["id"]: c["name"] for c in data.get("categories", [])}
        qs = data.get("questions", [])
        by_cat = collections.Counter()
        by_cat_reviewed = collections.Counter()
        by_level = collections.Counter()
        rev = disp = 0

        for q in qs:
            qid = q.get("id", "<без id>")
            for field in REQUIRED:
                if field not in q:
                    errs.append(f"{fname} / {qid}: нет поля «{field}»")
            if qid in seen_ids:
                errs.append(f"{qid}: повтор id (уже есть в {seen_ids[qid]})")
            seen_ids[qid] = fname

            opts = q.get("opts") or []
            if len(opts) != 4:
                errs.append(f"{qid}: вариантов {len(opts)}, ожидается 4")
            if len(set(opts)) != len(opts):
                errs.append(f"{qid}: варианты повторяются — верных ответов больше одного")
            a = q.get("a")
            if not isinstance(a, int) or not (0 <= a < len(opts)):
                errs.append(f"{qid}: индекс ответа a={a} вне списка вариантов")
            lvl = q.get("level")
            if lvl not in (1, 2, 3, 4, 5):
                errs.append(f"{qid}: level={lvl} вне 1..5")
            cat = q.get("cat")
            if cat not in cats:
                errs.append(f"{qid}: категория «{cat}» не объявлена в meta")
            for field in ("q", "why", "src"):
                if not str(q.get(field, "")).strip():
                    errs.append(f"{qid}: поле «{field}» пустое")
            check_ref(q.get("ref", ""), quran, errs, qid)

            by_cat[cat] += 1
            by_level[lvl] += 1
            if q.get("reviewed") is True:
                rev += 1
                by_cat_reviewed[cat] += 1
            if q.get("disputed") is True:
                disp += 1

        total += len(qs)
        reviewed_total += rev
        disputed_total += disp
        per_file.append((fname, data.get("meta", {}).get("title", ""), qs, cats,
                         by_cat, by_cat_reviewed, by_level, rev, disp))

    for fname, title, qs, cats, by_cat, by_cat_rev, by_level, rev, disp in per_file:
        print(f"\n=== {fname} — {title}")
        print(f"    вопросов: {len(qs)} | вычитано: {rev} | со спорным ответом (disputed): {disp}")
        print(f"    по уровням: " + ", ".join(f"{l}: {by_level[l]}" for l in sorted(by_level)))
        for cid, cname in cats.items():
            print(f"      {cname:<36} {by_cat[cid]:>3}  (вычитано {by_cat_rev[cid]})")

    print(f"\nВсего в банке: {total} | вычитано: {reviewed_total} | спорных: {disputed_total}")
    if reviewed_total == 0:
        print("ВНИМАНИЕ: вычитанных записей нет — показывать в приложении нечего "
              "(в выдачу допускаются только reviewed:true).")

    if errs:
        print(f"\nОШИБКИ ({len(errs)}):")
        for e in errs:
            print("  •", e)
        return 1
    print("\n✓ Структура банка в порядке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
