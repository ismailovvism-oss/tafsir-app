#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_fal.py — генерация фонов для режима «Диафильм» через fal.ai.

Параллельный набор к картинкам из ChatGPT. Кладёт результат в
    data/media/filmstrip-fal/<model_key>/<topicid>_<slug>_vN.png
чтобы можно было сравнивать модели между собой.

Промт: стабильный SYSTEM-контракт (из AGENTS.md) + PER-TOPIC из
filmstrip-manifest.json (name / meaning / metaphor / avoid).

Ключ fal.ai — через переменную окружения FAL_KEY (или --key).
    export FAL_KEY="...."
    python3 gen_fal.py --model flux-dev --limit 2          # тест: 2 темы
    python3 gen_fal.py --model flux-pro-ultra --topics 1038,538
    python3 gen_fal.py --model flux-dev --all               # весь манифест

Никакой ключ в файл/репозиторий не пишется.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(ROOT, "data", "media", "filmstrip-manifest.json")
OUTBASE = os.path.join(ROOT, "data", "media", "filmstrip-fal")

# --- Стабильный SYSTEM-контракт (синхронизирован с AGENTS.md) ---------------
SYSTEM = """Generate a contemplative, cinematic background image for a Quran tafsir app, fullscreen "filmstrip" mode on a phone.

PURPOSE
Inspire reflection on the signs (ayat) of Allah in creation, human life, morality, guidance, trials, mercy, accountability, and the Hereafter — WITHOUT literalizing any sacred or unseen reality. The image supports the meaning of the ayah as a sign, never depicts the sacred itself.

FORMAT & COMPOSITION
Horizontal landscape, aspect ratio 16:9, high resolution. This is the primary format (the app opens the filmstrip in landscape by default).
CENTER-SAFE composition (important): the image may also be shown cropped to a vertical/portrait screen, which cuts off the LEFT and RIGHT edges. Therefore keep the key subject and all essential content within the central safe zone (roughly the middle 60% horizontally). Do not place anything important near the left or right edges.
Keep a calm, uncluttered area in the LOWER-CENTER (sky, water, mist, wall, sand, or open ground) as clean empty negative space, centered so it survives both landscape and portrait. This lower area must stay completely bare — no marks, no patterns, no writing of any kind.
Main subject in the upper or central area, off-center but inside the central safe zone; never crowd the bottom-center.

STYLE
Cinematic, naturalistic, atmospheric. Realistic light, depth, quiet grandeur, reflective mood.
Avoid: cartoon, fantasy-game art, horror, kitsch, heavy decoration, generic stock-photo look, HDR over-saturation.
No text, no letters, no numbers, no calligraphy, no script of any language, no symbols, no logo, no watermark, no UI.
CRITICAL — ZERO WRITING: absolutely NO Arabic script and NO Arabic-looking or pseudo-Arabic lettering anywhere, NO calligraphic strokes, NO caption or subtitle bars — especially none along the bottom edge. The frame is a pure photograph with no writing whatsoever.

RELIGIOUS CONSTRAINTS (hard rules)
- Do NOT depict Allah in any form, and do NOT imply that any light, figure, face, hand, throne, eye, cloud, celestial object, or presence is Allah.
- Do NOT depict any prophet or messenger — no face, no body, no identifiable figure, not even from behind.
- Do NOT depict angels — not as persons, wings, luminous beings, or humanoid forms.
- Do NOT depict Paradise or Hell as literal confirmed realities. Use restrained natural imagery only (gardens, distant light, shade, barren land, distant storm, renewal). Avoid dramatic "hellfire"; if fire is needed, keep it mundane/natural (fading embers, a far lightning storm), never an inferno reading as Hell.
- Do NOT depict manuscripts, scrolls, books, or open pages (the model tends to add fake script). Use light, paths, lanterns, rain on dry earth for revelation/guidance instead.
- No idols as devotional objects, no graphic violence, gore, torture, nudity, or erotic content, nothing disrespectful.
- Avoid mosque-interior / calligraphy clichés unless the topic is specifically worship or prayer, and even then keep it subtle and text-free.

DEPICTION OF LIVING BEINGS (strict default)
- By default show NO people and NO animals up close.
- People are a rare exception, allowed ONLY when the topic cannot read without them. When allowed: distant, small in the frame, back-facing or silhouetted, partially obscured, never with a visible face or portrait detail, never a central heroic figure.
- Animals only distant and incidental, never a portrait.

PREFERRED VISUAL LANGUAGE (signs in creation)
Heavens, stars, dawn, the turning of night and day, rain, clouds, mountains, sea, rivers, plants, seeds, distant landscapes, paths, ruins, flowing water, desert, light after darkness, stillness, vastness, balance, growth, decay and renewal.

OUTPUT
One polished horizontal 16:9 image, respectful as a background for Quran recitation and tafsir. No embedded words, letters, script, or signatures anywhere in the frame."""


def per_topic(topic, metaphor):
    return (
        f"TOPIC: {topic['name']}\n\n"
        f"MEANING: {topic.get('meaning','')}\n\n"
        f"SUGGESTED METAPHOR: {metaphor}\n\n"
        f"AVOID FOR THIS TOPIC: {topic.get('avoid','')}"
    )


def full_prompt(topic, metaphor):
    return SYSTEM + "\n\n---\n\n" + per_topic(topic, metaphor)


# --- Реестр моделей fal.ai --------------------------------------------------
# endpoint = путь после https://fal.run/ ; payload(prompt) -> тело запроса.
# Разные модели зовут параметр соотношения сторон по-разному, поэтому билдер
# тела отдельный на каждую модель. Добавить модель = добавить запись сюда.
def _flux_dev(prompt):
    return {
        "prompt": prompt,
        "image_size": "landscape_16_9",
        "num_images": 1,
        "enable_safety_checker": True,
        "num_inference_steps": 28,
    }


def _flux_pro_ultra(prompt):
    # aspect_ratio enum (21:9,16:9,4:3,3:2,1:1,...), num_images, safety_tolerance,
    # output_format. Схема сверена по API fal.ai.
    return {
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "num_images": 1,
        "safety_tolerance": "3",
        "output_format": "png",
    }


def _seedream(prompt):
    # image_size enum (landscape_16_9 и др.) / {width,height}; num_images. Сверено.
    return {
        "prompt": prompt,
        "image_size": "landscape_16_9",
        "num_images": 1,
    }


def _krea_v2(prompt):
    # aspect_ratio enum (16:9 есть), creativity, seed. num_images нет. Сверено.
    return {
        "prompt": prompt,
        "aspect_ratio": "16:9",
    }


def _grok(prompt):
    # aspect_ratio enum (16:9 есть), num_images, resolution 1k/2k, output_format. Сверено.
    return {
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "num_images": 1,
        "resolution": "2k",
        "output_format": "png",
    }


def _flux_2(prompt):
    return {
        "prompt": prompt,
        "image_size": "landscape_16_9",
        "num_images": 1,
        "enable_safety_checker": True,
        "output_format": "png",
    }


def _nano_banana_pro(prompt):
    # Google Nano Banana Pro (fal-ai/nano-banana-pro): aspect_ratio enum
    # (auto,21:9,16:9,3:2,4:3,5:4,1:1,...), num_images. Схема сверена по API-доке.
    return {
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "num_images": 1,
    }


# Схемы flux-2 / flux-dev / flux-pro-ultra / nano-banana-pro сверены по API fal.ai.
# seedream/krea — endpoint предварительный, перед прогоном свериться отдельно.
MODELS = {
    "flux-2":         {"endpoint": "fal-ai/flux-2",                            "payload": _flux_2},
    "flux-dev":       {"endpoint": "fal-ai/flux/dev",                          "payload": _flux_dev},
    "flux-pro-ultra": {"endpoint": "fal-ai/flux-pro/v1.1-ultra",               "payload": _flux_pro_ultra},
    "nano-banana-pro":{"endpoint": "fal-ai/nano-banana-pro",                   "payload": _nano_banana_pro},
    "seedream":       {"endpoint": "bytedance/seedream/v5/pro/text-to-image",  "payload": _seedream},
    "krea":           {"endpoint": "krea/v2/large/text-to-image",             "payload": _krea_v2},
    "grok":           {"endpoint": "xai/grok-imagine-image",                  "payload": _grok},
}


_TR = {
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z",
    "и":"i","й":"y","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r",
    "с":"s","т":"t","у":"u","ф":"f","х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch",
    "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
}


def _key_from_file():
    p = os.path.join(ROOT, ".fal_key")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    return None


def slug(name):
    s = name.strip().lower()
    s = "".join(_TR.get(ch, ch) for ch in s)     # рус -> лат
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")  # остальное -> дефис
    return s or "topic"


def extract_images(data):
    """Достаём список URL картинок из ответа fal (разные модели, разные ключи)."""
    if not isinstance(data, dict):
        return []
    imgs = data.get("images") or data.get("image")
    urls = []
    if isinstance(imgs, dict):
        imgs = [imgs]
    if isinstance(imgs, list):
        for it in imgs:
            if isinstance(it, str):
                urls.append(it)
            elif isinstance(it, dict) and it.get("url"):
                urls.append(it["url"])
    # некоторые модели: {"image":{"url":...}} или {"output":{"images":[...]}}
    if not urls and isinstance(data.get("output"), dict):
        return extract_images(data["output"])
    return urls


def call_fal(endpoint, body, key, timeout=180):
    url = f"https://fal.run/{endpoint}"
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    r = requests.post(url, headers=headers, json=body, timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
    return r.json()


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "tafsir-app/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(path, "wb") as f:
        f.write(resp.read())


def main():
    ap = argparse.ArgumentParser(description="Генерация фонов диафильма через fal.ai")
    ap.add_argument("--model", required=True, choices=list(MODELS.keys()),
                    help="ключ модели из реестра MODELS")
    ap.add_argument("--key", default=os.environ.get("FAL_KEY") or _key_from_file(),
                    help="fal.ai API key (FAL_KEY / файл .fal_key / --key)")
    ap.add_argument("--topics", default="", help="список id тем через запятую")
    ap.add_argument("--all", action="store_true", help="все темы манифеста")
    ap.add_argument("--limit", type=int, default=0, help="взять первые N тем (тест)")
    ap.add_argument("--variants", type=int, default=1,
                    help="сколько метафор-вариантов на тему (по умолчанию 1)")
    ap.add_argument("--risk", default="", help="фильтр по риску: low/medium/high (через запятую)")
    ap.add_argument("--manifest", default=MANIFEST,
                    help="путь к manifest JSON (по умолчанию filmstrip-manifest.json)")
    ap.add_argument("--dry-run", action="store_true", help="не звать API, только показать план")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(line_buffering=True)  # живой прогресс в фоне
    except Exception:
        pass

    if not args.key and not args.dry_run:
        sys.exit("Нет ключа: задай FAL_KEY или --key")

    mpath = args.manifest if os.path.isabs(args.manifest) else os.path.join(ROOT, args.manifest)
    with open(mpath, encoding="utf-8") as f:
        manifest = json.load(f)
    topics = manifest["topics"]

    if args.topics:
        want = {t.strip() for t in args.topics.split(",") if t.strip()}
        topics = [t for t in topics if t["id"] in want]
    if args.risk:
        risks = {r.strip() for r in args.risk.split(",")}
        topics = [t for t in topics if t.get("risk") in risks]
    if args.limit:
        topics = topics[: args.limit]
    if not args.all and not args.topics and not args.limit and not args.risk:
        sys.exit("Укажи что генерить: --all, --topics, --limit или --risk")

    model = MODELS[args.model]
    outdir = os.path.join(OUTBASE, args.model)
    os.makedirs(outdir, exist_ok=True)

    runlog = []
    total = 0
    fails = 0            # подряд идущих ошибок
    MAX_FAILS = 5        # стоп (обычно = кончились кредиты/ключ)
    aborted = False
    for t in topics:
        if aborted:
            break
        metas = t.get("metaphors") or [""]
        metas = metas[: max(1, args.variants)]
        for i, meta in enumerate(metas, 1):
            prompt = full_prompt(t, meta)
            # общий стандарт проекта (совместим с build_visual_pack.py):
            # topic-<id>-<nn>.png — id темы + двузначный номер варианта.
            fname = f"topic-{t['id']}-{i:02d}.png"
            fpath = os.path.join(outdir, fname)
            total += 1
            print(f"[{total}] {args.model}  тема {t['id']} «{t['name']}» v{i}  ->  {fname}")
            if args.dry_run:
                print("    METAPHOR:", meta)
                continue
            if os.path.exists(fpath):
                print("    уже есть, пропуск")
                continue
            try:
                body = model["payload"](prompt)
                data = call_fal(model["endpoint"], body, args.key)
                urls = extract_images(data)
                if not urls:
                    print("    ! нет картинок в ответе:", json.dumps(data)[:300])
                    runlog.append({"id": t["id"], "v": i, "ok": False, "err": "no_images"})
                    continue
                download(urls[0], fpath)
                print("    ok", urls[0][:80])
                runlog.append({"id": t["id"], "v": i, "file": fname, "url": urls[0], "ok": True})
                fails = 0
            except Exception as e:
                print("    ОШИБКА:", e)
                runlog.append({"id": t["id"], "v": i, "ok": False, "err": str(e)[:300]})
                fails += 1
                if fails >= MAX_FAILS:
                    print(f"\n!! {MAX_FAILS} ошибок подряд — останавливаюсь "
                          f"(вероятно кончились кредиты или ключ). Уже готовое сохранено.")
                    aborted = True
                    break
            time.sleep(0.5)

    if not args.dry_run:
        logpath = os.path.join(outdir, "_runlog.json")
        with open(logpath, "w", encoding="utf-8") as f:
            json.dump({"model": args.model, "endpoint": model["endpoint"], "runs": runlog},
                      f, ensure_ascii=False, indent=2)
        ok = sum(1 for r in runlog if r.get("ok"))
        print(f"\nГотово: {ok}/{len(runlog)} успешно. Лог: {logpath}")


if __name__ == "__main__":
    main()
