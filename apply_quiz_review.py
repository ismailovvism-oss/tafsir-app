#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_quiz_review.py — перенести отметки вычитки в банк вопросов.

Зачем. Вычитывать банк удобнее всего проходя само упражнение «Кто хочет стать
учёным» в черновом режиме: после каждой ошибки видно вопрос, обоснование и поле
src. Там же стоят кнопки «✓ верно» / «✕ спорно». Браузер писать в репозиторий не
может, поэтому отметки копятся локально и выгружаются файлом — а этот скрипт
переносит их в data/quiz/*.json.

Что делает:
  «ok»  → reviewed: true   (вопрос допущен к показу)
  «bad» → reviewed: false + flag: "спорно"  (остаётся в банке, но виден как
          требующий правки; снять флаг — вручную, после исправления вопроса)

Запуск:  python3 apply_quiz_review.py quiz-review.json
         python3 apply_quiz_review.py quiz-review.json --dry   (только показать)

Идемпотентен: повторный запуск с тем же файлом ничего не меняет.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
QUIZ = os.path.join(ROOT, "data", "quiz")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry" in sys.argv
    if not args:
        print(__doc__)
        return 1
    with open(args[0], encoding="utf-8") as f:
        marks = json.load(f).get("marks", {})
    if not marks:
        print("В файле нет отметок.")
        return 1

    with open(os.path.join(QUIZ, "index.json"), encoding="utf-8") as f:
        files = json.load(f).get("files", [])

    applied = collected = 0
    unknown = set(marks)
    for fname in files:
        path = os.path.join(QUIZ, fname)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        changed = 0
        for q in data.get("questions", []):
            mark = marks.get(q["id"])
            if mark is None:
                continue
            unknown.discard(q["id"])
            collected += 1
            if mark == "ok":
                new = {"reviewed": True}
                if "flag" in q:
                    new["flag"] = None
            elif mark == "bad":
                new = {"reviewed": False, "flag": "спорно"}
            else:
                print(f"  ? {q['id']}: непонятная отметка «{mark}» — пропущена")
                continue
            for k, v in new.items():
                if v is None:
                    q.pop(k, None)
                elif q.get(k) != v:
                    q[k] = v
                    changed += 1
        if changed and not dry:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
        applied += changed
        print(f"{fname}: изменено полей — {changed}{' (пробный прогон)' if dry else ''}")

    print(f"\nОтметок в файле: {len(marks)} | найдено в банке: {collected} | изменено полей: {applied}")
    if unknown:
        print(f"Не найдены в банке ({len(unknown)}): {', '.join(sorted(unknown))}")
    if not dry:
        print("\nТеперь стоит прогнать: python3 validate_quiz.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
