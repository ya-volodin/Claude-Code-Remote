#!/usr/bin/env python3
"""
Получение топа выдачи Яндекса по запросу через SERP API.

Поддерживаемые провайдеры:
  - xmlriver   (по умолчанию)  -> https://xmlriver.com/search_yandex/xml
  - yandex_xml (legacy/Cloud)  -> Yandex XML

Креды берутся из переменных окружения (НЕ передаются в открытом виде в аргументах):
  XMLRiver:
    XMLRIVER_USER, XMLRIVER_KEY
  Yandex XML:
    YANDEX_XML_USER (или YANDEX_FOLDER_ID), YANDEX_XML_KEY

Вывод: JSON-файл со списком результатов [{position, url, title}].

Пример:
  python scripts/fetch_serp.py --query "купить аспирин" --region 213 --top 5 --out serp.json

Замечание про сеть: запросу нужен доступ к домену провайдера. Если песочница его
блокирует (egress-прокси вернёт x-deny-reason), разрешите домен в настройках сети
или используйте ручной фолбэк (вставьте URL выдачи и пропустите этот шаг).
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


def _http_get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "seo-text-review/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_yandex_xml(xml_text: str, top: int):
    """Разбор стандартного формата Yandex XML (его же отдаёт XMLRiver)."""
    results = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise RuntimeError(f"Не удалось разобрать XML ответа: {e}\nОтвет: {xml_text[:500]}")

    # Возможная ошибка от API
    err = root.find(".//error")
    if err is not None and (err.text or "").strip():
        raise RuntimeError(f"API вернул ошибку: {err.text.strip()}")

    pos = 0
    for doc in root.iter("doc"):
        url_el = doc.find("url")
        if url_el is None or not (url_el.text or "").strip():
            continue
        pos += 1
        title_el = doc.find("title")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""
        results.append({"position": pos, "url": url_el.text.strip(), "title": title})
        if pos >= top:
            break
    return results


def fetch_xmlriver(query: str, region: int, top: int, device: str):
    user = os.environ.get("XMLRIVER_USER")
    key = os.environ.get("XMLRIVER_KEY")
    if not user or not key:
        sys.exit(
            "Нет кредов XMLRiver. Задайте переменные окружения XMLRIVER_USER и "
            "XMLRIVER_KEY, либо используйте ручной фолбэк (вставьте топ выдачи)."
        )
    params = {
        "user": user,
        "key": key,
        "query": query,
        "loc": region,        # регион Яндекса (213 = Москва)
        "device": device,
        "groupby": top,
    }
    url = "https://xmlriver.com/search_yandex/xml?" + urllib.parse.urlencode(params)
    xml_text = _http_get(url)
    return _parse_yandex_xml(xml_text, top)


def fetch_yandex_xml(query: str, region: int, top: int):
    user = os.environ.get("YANDEX_XML_USER") or os.environ.get("YANDEX_FOLDER_ID")
    key = os.environ.get("YANDEX_XML_KEY")
    if not user or not key:
        sys.exit(
            "Нет кредов Yandex XML. Задайте YANDEX_XML_USER (или YANDEX_FOLDER_ID) и "
            "YANDEX_XML_KEY, либо используйте ручной фолбэк."
        )
    params = {
        "user": user,
        "key": key,
        "query": query,
        "lr": region,
        "groupby": f"attr=d.mode=deep.groups-on-page={top}.docs-in-group=1",
    }
    base = os.environ.get("YANDEX_XML_ENDPOINT", "https://yandex.ru/search/xml")
    url = base + "?" + urllib.parse.urlencode(params)
    xml_text = _http_get(url)
    return _parse_yandex_xml(xml_text, top)


def main():
    ap = argparse.ArgumentParser(description="Топ выдачи Яндекса через SERP API")
    ap.add_argument("--query", required=True, help="Целевой запрос")
    ap.add_argument("--region", type=int, default=213, help="Регион Яндекса (213=Москва)")
    ap.add_argument("--top", type=int, default=5, help="Сколько результатов вернуть")
    ap.add_argument("--provider", default="xmlriver", choices=["xmlriver", "yandex_xml"])
    ap.add_argument("--device", default="desktop", choices=["desktop", "mobile"])
    ap.add_argument("--out", default="serp.json", help="Файл для записи результата")
    args = ap.parse_args()

    try:
        if args.provider == "xmlriver":
            results = fetch_xmlriver(args.query, args.region, args.top, args.device)
        else:
            results = fetch_yandex_xml(args.query, args.region, args.top)
    except Exception as e:  # noqa: BLE001
        sys.exit(
            f"Ошибка обращения к SERP API: {e}\n"
            "Если это блокировка сети (x-deny-reason) — разрешите домен провайдера "
            "в настройках сети или используйте ручной фолбэк."
        )

    if not results:
        sys.exit("API не вернул результатов. Проверьте запрос/регион/креды.")

    payload = {
        "query": args.query,
        "region": args.region,
        "provider": args.provider,
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Записано {len(results)} результатов в {args.out}:")
    for r in results:
        print(f"  {r['position']}. {r['url']}")


if __name__ == "__main__":
    main()
