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

      // серверный ревизионный счётчик + метка времени (для строки статуса и
      // будущего разрешения конфликтов; данные сливаются на клиенте объединением)
      let prevRev = 0;
      const prev = await env.SYNC.get(key);
      if (prev) { try { prevRev = (JSON.parse(prev)._rev | 0); } catch {} }
      obj._rev = prevRev + 1;
      obj._updatedAt = new Date().toISOString();

      await env.SYNC.put(key, JSON.stringify(obj));
      return json({ ok: true, rev: obj._rev, updatedAt: obj._updatedAt }, 200);
    }

    return json({ error: "method" }, 405);
  },
};
