#!/usr/bin/env python3
"""
Очистка извлечённого текста страницы от навигации и служебного мусора
перед анализом ключей.

Зачем: web_fetch отдаёт markdown, где меню, фильтры, хлебные крошки и карточки
товаров идут сплошным списком ссылок и фронт-лоадят выдачу. Если не вычистить —
частоты и медиана объёма искажаются.

Что делает (механически, безопасно):
  - срезает front-matter блок метаданных (--- ... ---);
  - убирает markdown-картинки, оставляет якорный текст ссылок, удаляет URL;
  - выкидывает строки-«меню» (сплошные ссылки/короткие подписи без предложений);
  - выкидывает хлебные крошки и строки с плотными разделителями (· | /);
  - дедуплицирует повторяющиеся строки.

ВАЖНО: это лишь предочистка. После неё ОБЯЗАТЕЛЬНО просмотри результат глазами и
вручную убери остаточный мусор (мегаменю без переносов строк скрипт не разобьёт).
Сохраняй в .txt только описательную прозу: описание, состав, показания, дозировку,
противопоказания, побочные и т.п.

Использование:
  python scripts/clean_text.py --in raw.txt --out clean.txt
  python scripts/clean_text.py --in raw.txt           # печать в stdout
  python scripts/clean_text.py --in raw.txt --h1       # напечатать H1 (заготовка запроса)
"""
import argparse
import re
import sys

MD_IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL = re.compile(r"https?://\S+")
H1_MD = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
H1_TAG = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")
WORD = re.compile(r"[А-Яа-яЁёA-Za-z]{2,}")
SENT_PUNCT = ".!?:;"
# Явные UI-маркеры карточки товара/корзины — такие строки это интерфейс, не проза.
UI_MARKERS = ("₽", "руб.", "в корзину", "добавить в избранное", "в наличии в",
              "самовывоз", "添加", "купить в 1 клик")


def clean(text: str) -> str:
    # Срезаем front-matter (--- ... ---) в начале
    if text.lstrip().startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2]

    out, seen = [], set()
    for raw in text.splitlines():
        line = MD_IMG.sub("", raw)
        line = MD_LINK.sub(r"\1", line)   # ссылку -> её текст
        line = URL.sub("", line)
        s = line.strip(" \t#*-•|·/>")
        if not s:
            continue

        low = s.lower()
        # Явные элементы интерфейса карточки
        if any(mark in low for mark in UI_MARKERS):
            continue

        words = WORD.findall(s)
        has_sentence = any(p in s for p in SENT_PUNCT) and len(words) >= 6

        # Короткие строки без признаков предложения = подписи/меню
        if len(words) < 4 and not has_sentence:
            continue
        # Хлебные крошки / меню с плотными разделителями
        if (s.count("·") + s.count("|") + s.count("/")) >= 3 and len(words) < 12:
            continue

        key = low
        if key in seen:
            continue
        seen.add(key)
        out.append(s)

    return "\n".join(out)


def extract_h1(text: str) -> str:
    """Первый H1 страницы (markdown '# ...' или <h1>...</h1>)."""
    m = H1_MD.search(text)
    if m:
        return MD_LINK.sub(r"\1", m.group(1)).strip()
    m = H1_TAG.search(text)
    if m:
        return TAG.sub("", m.group(1)).strip()
    return ""


def main():
    ap = argparse.ArgumentParser(description="Очистка текста от навигации/мусора")
    ap.add_argument("--in", dest="inp", required=True, help="Файл с сырым извлечённым текстом")
    ap.add_argument("--out", dest="out", default=None, help="Куда писать (по умолчанию stdout)")
    ap.add_argument("--h1", action="store_true",
                    help="Не чистить, а напечатать H1 страницы (заготовку для запроса)")
    args = ap.parse_args()

    with open(args.inp, encoding="utf-8", errors="replace") as f:
        raw = f.read()

    if args.h1:
        h1 = extract_h1(raw)
        print(h1 if h1 else "(H1 не найден)")
        return

    cleaned = clean(raw)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(cleaned + "\n")
        words = len(WORD.findall(cleaned))
        print(f"Очищено: {words} значимых слов -> {args.out}", file=sys.stderr)
    else:
        print(cleaned)


if __name__ == "__main__":
    main()
