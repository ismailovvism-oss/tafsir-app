#!/usr/bin/env python3
"""
build_timings.py — аятные тайминги для ПОСУРНЫХ чтецов (config.json → type:"audio_surah").

Что делает: forced alignment (CTC / модель MMS, ONNX-инференс на CPU) арабского
текста Корана к аудиофайлу ЦЕЛОЙ суры. Выравнивание идёт по фонетике, НЕ по паузам,
поэтому корректно работает и на соединённых аятах (васль), где тишины между аятами нет.

Зачем: у посурных чтецов (напр. saegh) один mp3 = вся сура, поаятных таймингов нет,
поэтому диафильм/подсветка не следуют за аятом. Этот скрипт их вычисляет.

ОКРУЖЕНИЕ (система на Python 3.14 — aeneas не ставится; нужен отдельный venv 3.12):
    uv venv --python 3.12 .venv-timings
    uv pip install --python .venv-timings/bin/python \
        torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    uv pip install --python .venv-timings/bin/python ctc-forced-aligner unidecode

ЗАПУСК:
    .venv-timings/bin/python build_timings.py                 # все audio_surah чтецы
    .venv-timings/bin/python build_timings.py --reciter saegh # только один
    .venv-timings/bin/python build_timings.py --sura 114      # одна сура (отладка)
    .venv-timings/bin/python build_timings.py --force         # пересчитать имеющиеся

ВЫХОД: data/audio/timings/<reciter>/<sura>.json = {"<аят>": [start, end], ...} (секунды)
       data/audio/timings/<reciter>/_report.json — QA-отчёт (что подозрительно)
КЭШ:   data/_sources/audio/<reciter>/<NNN>.mp3 (gitignored, для резюма/повтора)
"""
import argparse, json, os, sys, time, urllib.request

ROOT   = os.path.dirname(os.path.abspath(__file__))
CFG    = os.path.join(ROOT, "data", "config.json")
ARABIC = os.path.join(ROOT, "data", "tafsirs", "_arabic.json")
CACHE  = os.path.join(ROOT, "data", "_sources", "audio")
OUTDIR = os.path.join(ROOT, "data", "audio", "timings")

# базы аудио по значению поля reciter.cdn (build-time; в приложении не используется)
AUDIO_BASE = {
    "quranicaudio": "https://download.quranicaudio.com/quran",
}

# ---- тяжёлые импорты и модель загружаются один раз ленью ----
_M = {}
def _model():
    if _M:
        return _M
    import numpy as np, onnxruntime, math
    from ctc_forced_aligner import (
        load_audio, preprocess_text, SAMPLING_FREQ, time_to_frame,
        get_alignments, get_spans, postprocess_results,
        Tokenizer, ensure_onnx_model, MODEL_URL,
    )
    mp = os.path.expanduser("~/.cache/ctc_forced_aligner/model.onnx")
    ensure_onnx_model(mp, MODEL_URL)
    # Экономный режим памяти/CPU: без арены (арена пред-выделяет много памяти),
    # ограниченное число потоков (не занимать все ядра рабочей машины).
    so = onnxruntime.SessionOptions()
    so.enable_cpu_mem_arena = False
    so.enable_mem_pattern = False
    so.intra_op_num_threads = int(os.environ.get("TIMINGS_THREADS", "4"))
    so.inter_op_num_threads = 1
    _M.update(dict(
        np=np, math=math, SAMPLING_FREQ=SAMPLING_FREQ, time_to_frame=time_to_frame,
        load_audio=load_audio, preprocess_text=preprocess_text,
        get_alignments=get_alignments, get_spans=get_spans,
        postprocess_results=postprocess_results,
        session=onnxruntime.InferenceSession(mp, sess_options=so,
                                             providers=["CPUExecutionProvider"]),
        tokenizer=Tokenizer(),
    ))
    return _M

# Стриминговый расчёт эмиссий: окна аудио НЕ материализуются разом (это был пик
# памяти на длинных сурах) — гоним окно за окном, копим только лёгкие логиты.
# Логика идентична generate_emissions из ctc_forced_aligner (те же паддинги/срезы).
def _emissions_stream(m, audio, window_length=30, context_length=2):
    np, math = m["np"], m["math"]
    SF, t2f = m["SAMPLING_FREQ"], m["time_to_frame"]
    session = m["session"]
    context = context_length * SF
    window = window_length * SF
    ext = math.ceil(audio.shape[0] / window) * window - audio.shape[0]
    padded = np.pad(audio, (context, context + ext), mode="constant")
    num = (padded.shape[0] - 2 * context) // window
    outs = []
    for i in range(num):
        seg = padded[i * window: i * window + window + 2 * context].astype(np.float32)[None, :]
        outs.append(session.run(["logits"], {"input_values": seg})[0])
    em = np.concatenate(outs, axis=0)
    del outs, padded
    em = em[:, t2f(context_length): -t2f(context_length) + 1, ]
    em = em.reshape(-1, em.shape[-1])
    if t2f(ext / SF) > 0:
        em = em[: -t2f(ext / SF), :]
    em = np.log(np.exp(em) / np.sum(np.exp(em), axis=-1, keepdims=True))
    em = np.concatenate([em, np.zeros((em.shape[0], 1))], axis=1).astype(np.float32)
    stride = float(audio.shape[0] * 1000 / em.shape[0] / SF)
    return em, math.ceil(stride)

def ayah_list(quran, sura):
    s = quran[str(sura)]
    return [(int(k), s[k]) for k in sorted(s, key=int)]

def align_surah(audio_path, ayat, batch=8):
    """Вернуть ({"<аят>":[start,end]}, diag) для одной суры."""
    m = _model()
    counts = [len(t.split()) for _, t in ayat]
    full_text = " ".join(t for _, t in ayat)

    audio = m["load_audio"](audio_path, ret_type="np")
    dur = round(len(audio) / 16000.0, 2)
    emissions, stride = _emissions_stream(m, audio)     # экономный по памяти проход
    tokens_starred, text_starred = m["preprocess_text"](full_text, romanize=True, language="ara")
    segments, scores, blank = m["get_alignments"](emissions, tokens_starred, m["tokenizer"])
    spans = m["get_spans"](tokens_starred, segments, blank)
    words = m["postprocess_results"](text_starred, spans, stride, scores)

    out, i = {}, 0
    for (n, _), c in zip(ayat, counts):
        chunk = words[i:i+c]; i += c
        if not chunk:
            continue
        out[str(n)] = [round(float(chunk[0]["start"]), 3),
                       round(float(chunk[-1]["end"]),   3)]

    # ---- QA этой суры ----
    starts = [v[0] for v in out.values()]
    warns = []
    if len(words) != sum(counts):
        warns.append(f"слов {len(words)}!={sum(counts)}")
    if len(out) != len(ayat):
        warns.append(f"аятов {len(out)}!={len(ayat)}")
    if starts != sorted(starts):
        warns.append("старты не монотонны")
    last_end = max((v[1] for v in out.values()), default=0)
    if last_end > dur + 0.5:
        warns.append(f"конец {last_end}>длит {dur}")
    diag = {"dur": dur, "ayat": len(ayat), "words_exp": sum(counts),
            "words_got": len(words), "warns": warns}
    return out, diag

def fetch_audio(rec, sura):
    base = AUDIO_BASE.get(rec.get("cdn"))
    if not base:
        raise RuntimeError(f"нет базы аудио для cdn={rec.get('cdn')!r}")
    url = f"{base}/{rec['subdir']}/{sura:03d}.mp3"
    cdir = os.path.join(CACHE, rec["id"]); os.makedirs(cdir, exist_ok=True)
    dst = os.path.join(cdir, f"{sura:03d}.mp3")
    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        urllib.request.urlretrieve(url, dst)
    return dst

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reciter", help="id чтеца (по умолч. все audio_surah)")
    ap.add_argument("--sura", type=int, help="одна сура (1..114)")
    ap.add_argument("--batch", type=int, default=8, help="батч окон ONNX (утилизация ядер)")
    ap.add_argument("--order", choices=["len", "num"], default="len",
                    help="порядок: len=короткие суры первыми (польза раньше), num=1..114")
    ap.add_argument("--shard", help="I/K — обрабатывать только свою долю сур (для параллельных процессов)")
    ap.add_argument("--force", action="store_true", help="пересчитать уже готовые")
    args = ap.parse_args()

    cfg   = json.load(open(CFG, encoding="utf-8"))
    quran = json.load(open(ARABIC, encoding="utf-8"))
    recs  = [r for r in cfg["audio"]["reciters"] if r.get("type") == "audio_surah"]
    if args.reciter:
        recs = [r for r in recs if r["id"] == args.reciter]
    if not recs:
        print("нет посурных чтецов для обработки", file=sys.stderr); return

    if args.sura:
        suras = [args.sura]
    elif args.order == "len":                    # короткие суры первыми
        suras = sorted(range(1, 115),
                       key=lambda s: sum(len(t) for t in quran[str(s)].values()))
    else:
        suras = list(range(1, 115))
    if args.shard:                                # I/K: своя доля по позиции в очереди
        i, k = (int(x) for x in args.shard.split("/"))
        suras = [s for pos, s in enumerate(suras) if pos % k == i]
    for rec in recs:
        odir = os.path.join(OUTDIR, rec["id"]); os.makedirs(odir, exist_ok=True)
        report = {}
        print(f"=== {rec['id']} ({rec.get('name','')}) — {len(suras)} сур ===", flush=True)
        for sura in suras:
            outp = os.path.join(odir, f"{sura}.json")
            if os.path.exists(outp) and not args.force:
                print(f"  {sura:>3}: уже есть, пропуск", flush=True); continue
            t0 = time.time()
            try:
                mp3 = fetch_audio(rec, sura)
                out, diag = align_surah(mp3, ayah_list(quran, sura), batch=args.batch)
                json.dump(out, open(outp, "w", encoding="utf-8"), ensure_ascii=False)
                report[str(sura)] = diag
                flag = ("  ⚠ " + "; ".join(diag["warns"])) if diag["warns"] else ""
                import resource
                rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # МБ (пик)
                print(f"  {sura:>3}: {diag['ayat']} аят, "
                      f"{diag['words_got']}/{diag['words_exp']} слов, "
                      f"{diag['dur']}s, {time.time()-t0:.1f}s счёт, пик {rss:.0f}МБ{flag}", flush=True)
            except Exception as e:
                report[str(sura)] = {"error": str(e)}
                print(f"  {sura:>3}: ОШИБКА {e}", flush=True)
        # объединить с прежним отчётом (при частичных прогонах)
        rp = os.path.join(odir, "_report.json")
        old = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
        old.update(report)
        json.dump(old, open(rp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        bad = [s for s, d in old.items() if d.get("warns") or d.get("error")]
        print(f"--- {rec['id']}: готово {len(old)} сур, с замечаниями: "
              f"{sorted(bad, key=int) if bad else 'нет'}", flush=True)

if __name__ == "__main__":
    main()
