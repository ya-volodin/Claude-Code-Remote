#!/usr/bin/env python3
"""
Проверка уникальности новых блоков текста против корпуса конкурентов
(шингловый метод). Защищает от двух вещей сразу: низкой SEO-уникальности и
непреднамеренного копирования чужого текста.

Как считает: режет новый текст на словные шинглы (n-грамма из N слов, по
умолчанию 4) и смотрит, какая доля шинглов нового текста встречается в
объединённом корпусе конкурентов. Уникальность = 1 − доля совпавших шинглов.

Вход:
  --new          файл с новым текстом (блоки разделяются пустой строкой)
  --competitors  папка с .txt конкурентов (корпус для сравнения)
  --threshold    порог уникальности (по умолчанию 0.90)
  --shingle      размер шингла в словах (по умолчанию 4)

Вывод: JSON + сводка. Блоки ниже порога помечаются как FAIL — их надо переписать.

Замечание: сравнение идёт против собранного корпуса конкурентов, а не всего
интернета. Это релевантная проверка (именно эти тексты можно случайно повторить)
и одновременно копирайт-страховка, но она НЕ заменяет полноценный сервис проверки
уникальности (text.ru, Advego и т.п.), если нужна оценка против всей сети.
"""
import argparse
import json
import re
import sys

WORD = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


def words(text: str):
    return [w.lower() for w in WORD.findall(text)]


def shingles(tokens, n: int):
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)} if len(tokens) >= n else set()


def main():
    ap = argparse.ArgumentParser(description="Проверка уникальности новых блоков (шинглы)")
    ap.add_argument("--new", required=True, help="Файл с новым текстом (блоки через пустую строку)")
    ap.add_argument("--competitors", required=True, help="Папка с .txt конкурентов")
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--shingle", type=int, default=4)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import os
    comp_files = [os.path.join(args.competitors, f) for f in os.listdir(args.competitors)
                  if f.lower().endswith(".txt")]
    if not comp_files:
        sys.exit(f"В папке {args.competitors} нет .txt конкурентов.")

    corpus_tokens = []
    for cf in comp_files:
        with open(cf, encoding="utf-8", errors="replace") as f:
            corpus_tokens += words(f.read())
    corpus_shingles = shingles(corpus_tokens, args.shingle)

    with open(args.new, encoding="utf-8", errors="replace") as f:
        raw = f.read()
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]

    results = []
    all_new_sh, all_hit = set(), set()
    for idx, block in enumerate(blocks, 1):
        bt = words(block)
        bsh = shingles(bt, args.shingle)
        hit = bsh & corpus_shingles
        uniq = 1.0 - (len(hit) / len(bsh)) if bsh else 1.0
        all_new_sh |= bsh
        all_hit |= hit
        results.append({
            "block": idx,
            "preview": block[:60].replace("\n", " "),
            "words": len(bt),
            "uniqueness": round(uniq, 3),
            "status": "OK" if uniq >= args.threshold else "FAIL",
            "overlap_shingles": len(hit),
        })

    overall = 1.0 - (len(all_hit) / len(all_new_sh)) if all_new_sh else 1.0
    payload = {
        "shingle_size": args.shingle,
        "threshold": args.threshold,
        "overall_uniqueness": round(overall, 3),
        "blocks": results,
    }
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Общая уникальность новых блоков: {overall:.1%} (порог {args.threshold:.0%}, шингл {args.shingle})")
    for r in results:
        print(f"  блок {r['block']}: {r['uniqueness']:.1%} [{r['status']}] — {r['preview']}…")
    fails = [r for r in results if r["status"] == "FAIL"]
    if fails:
        print(f"НИЖЕ ПОРОГА: {len(fails)} блок(ов) надо переписать оригинальнее.")


if __name__ == "__main__":
    main()
