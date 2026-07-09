// Cloudflare Worker — облачная синхронизация личных данных приложения
// «Библиотека тафсиров» (заметки · закладки · теги · прогресс).
//
// Модель: доступ по СЛУЧАЙНОМУ КОДУ (он же ключ и секрет). Кто знает код —
// читает и пишет данные под ним. Ни email, ни паролей. Хранилище — KV.
//
// Маршруты:
//   GET  /v1/<code>  → отдать JSON-блоб (или {empty:true}, если пусто)
//   PUT  /v1/<code>  → сохранить JSON-блоб (проставляет _rev, _updatedAt)
//   OPTIONS          → CORS-preflight
//
// Код: 16–80 символов [A–Za–z0–9-]. Тело PUT ≤ 2 МБ. CORS: * (код — секрет,
// origin не ограничиваем; при желании сузьте ALLOW_ORIGIN до адреса Pages).

const ALLOW_ORIGIN = "*";
const MAX_BODY = 2_000_000; // 2 МБ
const CODE_RE = /^\/v1\/([A-Za-z0-9-]{16,80})$/;

function cors() {
  return {
    "Access-Control-Allow-Origin": ALLOW_ORIGIN,
    "Access-Control-Allow-Methods": "GET,PUT,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}
function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...cors(), "Content-Type": "application/json" },
  });
}

// ── Серверное слияние блоба на PUT ─────────────────────────────────────────
// Чтобы фоновый/beacon-пуш (без предварительного pull) НЕ затирал свежее чужое:
// заметки сводятся по меткам времени (LWW, obj._meta["notes:<s:a>"]=мс), а
// закладки/теги — объединяются. Клиент на pull досводит теми же правилами.
function mergeTagTree(a, b) {
  const out = (a || []).map(n => ({ name: n.name, children: mergeTagTree(n.children || [], []) }));
  for (const bn of (b || [])) {
    const ex = out.find(n => n.name === bn.name);
    if (ex) ex.children = mergeTagTree(ex.children, bn.children || []);
    else out.push({ name: bn.name, children: mergeTagTree(bn.children || [], []) });
  }
  return out;
}
function mergeBlob(prev, inc) {
  if (!prev || typeof prev !== "object") return inc;   // первое сохранение под кодом
  const out = { ...inc };
  const pm = prev._meta || {}, im = inc._meta || {}, meta = { ...pm, ...im };
  // заметки: LWW по меткам (нет метки → считаем старым)
  const notes = { ...(prev.notes || {}) };
  for (const k in (inc.notes || {})) {
    const rt = im["notes:" + k] || 0, lt = pm["notes:" + k] || 0;
    if (!(k in notes) || rt >= lt) notes[k] = inc.notes[k];   // входящее новее/равно или новое — берём
    meta["notes:" + k] = Math.max(rt, lt);
  }
  out.notes = notes;
  // закладки: объединение, существующие имена не трогаем
  out.bookmarks = { ...(inc.bookmarks || {}), ...(prev.bookmarks || {}) };
  // теги аятов: объединение списков путей
  const at = { ...(prev.ayahTags || {}) };
  for (const k in (inc.ayahTags || {})) {
    const s = new Set(at[k] || []);
    (inc.ayahTags[k] || []).forEach(p => s.add(p));
    at[k] = [...s];
  }
  out.ayahTags = at;
  // дерево тегов: глубокое слияние по именам
  out.tagTree = mergeTagTree(prev.tagTree || [], inc.tagTree || []);
  // прогресс: монотонно накапливается; оставляем тот, где больше дней активности
  // (клиент на pull сольёт по датам корректно — здесь лишь бы не «усохло»).
  const pd = ((prev.progress && prev.progress.activityDays) || []).length;
  const id = ((inc.progress && inc.progress.activityDays) || []).length;
  if (pd > id) out.progress = prev.progress;
  out._meta = meta;
  return out;
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { headers: cors() });

    const url = new URL(req.url);
    const m = url.pathname.match(CODE_RE);
    if (!m) return json({ error: "bad-code" }, 400);
    const key = "sync:" + m[1];

    if (req.method === "GET") {
      const val = await env.SYNC.get(key);
      if (!val) return json({ empty: true }, 200);
      return new Response(val, {
        status: 200,
        headers: { ...cors(), "Content-Type": "application/json" },
      });
    }

    if (req.method === "PUT") {
      const body = await req.text();
      if (body.length > MAX_BODY) return json({ error: "too-large" }, 413);
      let obj;
      try { obj = JSON.parse(body); } catch { return json({ error: "bad-json" }, 400); }
      if (!obj || typeof obj !== "object") return json({ error: "bad-json" }, 400);

      // серверное слияние с хранимым (LWW заметок + объединение) — чтобы фоновый
      // пуш без предварительного pull не затирал свежее с другого устройства.
      let prevRev = 0, prevObj = null;
      const prev = await env.SYNC.get(key);
      if (prev) { try { prevObj = JSON.parse(prev); prevRev = (prevObj._rev | 0); } catch {} }
      obj = mergeBlob(prevObj, obj);
      obj._rev = prevRev + 1;
      obj._updatedAt = new Date().toISOString();

      await env.SYNC.put(key, JSON.stringify(obj));
      return json({ ok: true, rev: obj._rev, updatedAt: obj._updatedAt }, 200);
    }

    return json({ error: "method" }, 405);
  },
};
