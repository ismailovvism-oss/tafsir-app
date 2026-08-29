/* ============================================================
   БИБЛИОТЕКА ТАФСИРОВ — service worker (офлайн-слой)
   ============================================================
   ДВА КЕША С РАЗНЫМИ СТРАТЕГИЯМИ — это главное, что нужно понимать:

   1) tl-shell-N   — ОБОЛОЧКА приложения (код, иконки, «загрузочные» данные:
      config/coverage/warnings/классификации сур). Стратегия NETWORK-FIRST:
      сеть всегда в приоритете, кеш отдаётся ТОЛЬКО когда сети нет.
      Поэтому обновления доезжают мгновенно, ровно как без воркера, и
      приложение физически не может «залипнуть» на старой версии — классическая
      болезнь PWA растёт из cache-first на index.html, которого здесь нет.

   2) tl-offline-N — то, что пользователь СКАЧАЛ ЯВНО (экран «📥 Офлайн»).
      Стратегия CACHE-FIRST: аяты неизменяемы, перепроверять нечего.
      Наполняет его СТРАНИЦА через Cache API (index.html: offlineDownload),
      воркер отсюда только читает. При смене версии воркера этот кеш НЕ
      трогается — иначе обновление кода стирало бы скачанные мегабайты.

   Ничего не кешируется «само по факту чтения»: расход памяти остаётся
   предсказуемым и целиком в руках пользователя.

   Аварийный выключатель — открыть сайт с «?nosw=1»: страница снимет
   регистрацию и вычистит оба кеша (см. swInit в index.html).
============================================================ */
const SHELL   = "tl-shell-1";     // поднять при смене СТРАТЕГИЙ (кеш оболочки пересоздастся)
const OFFLINE = "tl-offline-1";   // менять только при несовместимой смене формата (стирает скачанное)

// База = каталог самого sw.js (на GitHub Pages это /tafsir-app/), поэтому
// подкаталог публикации никак не зашит.
const BASE = new URL("./", self.location).href;
const DOC  = BASE + "index.html";   // канонический ключ документа в кеше

// Минимальный набор: остальное (версионные media.js/erudit.js, шрифты Google)
// докладывает страница — она одна знает MEDIA_VER/ERUDIT_VER (offlineWarm).
const PRECACHE = [
  "./", "./index.html", "./manifest.webmanifest",
  "./icons/app-icon.svg", "./icons/app-icon-192.png", "./icons/app-icon-512.png",
  "./data/config.json", "./data/coverage.json",
  "./data/warnings.json", "./data/surah-classifications.json",
  "./data/news.json",
  "./HELP.md",                // справка внутри приложения — экран ❓ читает этот файл
];

// «Загрузочные» данные: без них приложение офлайн открывается пустым, поэтому
// они живут в оболочке, а не в скачиваемых наборах.
const BOOT_DATA = new Set([
  "data/config.json", "data/coverage.json",
  "data/warnings.json", "data/surah-classifications.json",
  "data/news.json",
]);

self.addEventListener("install", e => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL).catch(() => null);
    // addAll падает целиком, если хоть один файл не отдался; кладём поштучно.
    if (c) await Promise.all(PRECACHE.map(u => c.add(u).catch(() => {})));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    for (const n of await caches.keys()) {
      if (n.startsWith("tl-shell-") && n !== SHELL) await caches.delete(n);
    }
    await self.clients.claim();
  })());
});

// Кеши открываем один раз, а не на каждый запрос. `.catch(()=>null)` обязателен:
// в инкогнито или при исчерпанном месте caches.open отвергается, и без этого
// воркер ронял бы ОБЫЧНЫЕ сетевые запросы — то есть ломал бы сайт там, где без
// него всё работало. Кеша нет → просто идём в сеть.
let _shell = null, _offline = null;
const shellCache   = () => (_shell   || (_shell   = caches.open(SHELL).catch(()   => null)));
const offlineCache = () => (_offline || (_offline = caches.open(OFFLINE).catch(() => null)));

// Оболочка: код и иконки в своём каталоге, самохостимые шрифты (кроме
// постраничных мусхафных — те тяжёлые и качаются явно) и загрузочные данные.
// Шрифты Google — тоже оболочка: без них офлайн ломается вид текста.
function isShell(url) {
  if (url.host === "fonts.googleapis.com" || url.host === "fonts.gstatic.com") return true;
  if (url.origin !== self.location.origin) return false;
  if (!url.href.startsWith(BASE)) return false;
  const p = url.href.slice(BASE.length).split("?")[0];
  if (p === "" || p === "index.html" || p === "manifest.webmanifest") return true;
  if (p === "HELP.md") return true;   // справка: сеть вперёд (правки видны сразу), кеш — запасной
  if (BOOT_DATA.has(p)) return true;
  if (p.startsWith("icons/")) return true;
  if (p.startsWith("fonts/") && !p.startsWith("fonts/qpc-")) return true;
  return p.indexOf("/") === -1 && p.endsWith(".js");   // media.js, erudit.js в корне
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.protocol !== "http:" && url.protocol !== "https:") return;
  // Медиа отдаём браузеру напрямую: перехват ломает Range-запросы (перемотку
  // и стриминг mp3), а выигрыша не даёт — аудио мы не кешируем.
  if (req.headers.get("range") || req.destination === "audio" || req.destination === "video") return;

  if (req.mode === "navigate") { e.respondWith(netFirstDoc(req)); return; }
  if (isShell(url))            { e.respondWith(netFirst(req));    return; }
  e.respondWith(offlineFirst(req));
});

// Документ: кладём ВСЕГДА под каноническим ключом, иначе «?cb=…», «?dev=1»,
// «?r2local=1» наплодили бы копий index.html на каждый набор параметров.
async function netFirstDoc(req) {
  const c = await shellCache();
  try {
    const r = await fetch(req);
    if (c && r && r.ok) c.put(DOC, r.clone()).catch(() => {});
    return r;
  } catch (e) {
    if (!c) throw e;
    const hit = (await c.match(DOC)) || (await c.match("./", { ignoreSearch: true }));
    if (hit) return hit;
    throw e;
  }
}

// Сеть вперёд, кеш — запасной. Сверка по ТОЧНОМУ URL: у media.js/erudit.js
// версия в «?v=», и ignoreSearch подсунул бы офлайн старый модуль к новому коду.
async function netFirst(req) {
  const c = await shellCache();
  try {
    const r = await fetch(req);
    if (c && r && r.ok && r.type !== "opaque") c.put(req, r.clone()).catch(() => {});
    return r;
  } catch (e) {
    const hit = c && await c.match(req);
    if (hit) return hit;
    throw e;
  }
}

// Скачанное пользователем: кеш вперёд. Промаха НЕ кешируем — наполнение только
// явное, чтобы «занято» на экране офлайна совпадало с тем, что человек выбрал.
async function offlineFirst(req) {
  const c = await offlineCache();
  if (!c) return fetch(req);
  const hit = await c.match(req);
  if (hit) return hit;
  try {
    return await fetch(req);
  } catch (e) {
    const alt = await c.match(req, { ignoreSearch: true });
    if (alt) return alt;
    throw e;
  }
}
