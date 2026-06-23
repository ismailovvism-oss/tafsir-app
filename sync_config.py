#!/usr/bin/env python3
"""
Единый источник правды для конфигурации источников.

Правится ТОЛЬКО data/config.json. Этот скрипт генерирует из него
оффлайн-зеркало data/config.js (window.TL_CONFIG=...;), которое приложение
использует, когда открыто без сервера. Запускай после любой ручной правки
config.json, чтобы зеркало не разъехалось.

Запуск:  python3 sync_config.py
"""
import json, os

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    cfg_json = os.path.join(ROOT, "data", "config.json")
    cfg_js = os.path.join(ROOT, "data", "config.js")

    cfg = json.load(open(cfg_json, encoding="utf-8"))
    open(cfg_js, "w", encoding="utf-8").write(
        "window.TL_CONFIG=" + json.dumps(cfg, ensure_ascii=False) + ";\n")

    print(f"config.js синхронизирован с config.json ({len(cfg['tafsirs'])} источников).")


if __name__ == "__main__":
    main()
