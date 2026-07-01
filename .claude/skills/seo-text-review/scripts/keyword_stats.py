#!/usr/bin/env python3
"""
Метрики ключей и полноты для SEO-ревью (русский язык, лемматизация pymorphy3).

Считает по лемматизированным текстам:
  - покрытие целевого запроса в тексте пользователя (доля лемм запроса, найденных в тексте);
  - частотные таблицы по тексту пользователя и по объединённому корпусу конкурентов;
  - "недобранные" ключи: значимые леммы, частые у нескольких конкурентов, но
    отсутствующие/редкие у пользователя;
  - объёмы (в словах): пользователь и медиана топ-конкурентов.

Использование:
  python scripts/keyword_stats.py --target target.txt \
      --competitors competitors/ --query "купить аспирин" --out stats.json

Зависимости: pymorphy3 (pip install pymorphy3). Если не установлен — скрипт
подскажет команду установки.
"""
import argparse
import json
import os
import re
import statistics
import sys
from collections import Counter

try:
    import pymorphy3
except ImportError:
    sys.exit("Нет pymorphy3. Установите: pip install pymorphy3 --break-system-packages")

TOKEN_RE = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)

# Базовый русский стоп-лист (служебные части речи и частотный шум).
STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще",
    "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли",
    "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь",
    "опять", "уж", "вам", "ведь", "там", "потом", "себя", "ничего", "ей",
    "может", "они", "тут", "где", "есть", "надо", "ней", "для", "мы", "тебя",
    "их", "чем", "была", "сам", "чтоб", "без", "будто", "чего", "раз", "тоже",
    "себе", "под", "будет", "ж", "тогда", "кто", "этот", "того", "потому",
    "этого", "какой", "совсем", "ним", "здесь", "этом", "один", "почти", "мой",
    "тем", "чтобы", "нее", "были", "куда", "зачем", "всех", "никогда", "можно",
    "при", "наконец", "два", "об", "другой", "хоть", "после", "над", "больше",
    "тот", "через", "эти", "нас", "про", "всего", "них", "какая", "много",
    "разве", "три", "эту", "моя", "впрочем", "хорошо", "свою", "этой", "перед",
    "иногда", "лучше", "чуть", "том", "нельзя", "такой", "им", "более", "всегда",
    "конечно", "всю", "между", "это", "которые", "которых", "также",
}


def tokens(text: str):
    return [t.lower() for t in TOKEN_RE.findall(text)]


def make_lemmatizer():
    morph = pymorphy3.MorphAnalyzer()
    cache = {}

    def lemma(tok: str) -> str:
        if tok not in cache:
            cache[tok] = morph.parse(tok)[0].normal_form
        return cache[tok]

    return lemma


def lemmatize(text: str, lemma):
    out = []
    for t in tokens(text):
        if t in STOPWORDS or len(t) < 3:
            continue
        l = lemma(t)
        if l in STOPWORDS or len(l) < 3:
            continue
        out.append(l)
    return out


def read_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description="Метрики ключей/полноты (pymorphy3)")
    ap.add_argument("--target", required=True, help="Файл с ОЧИЩЕННОЙ прозой страницы пользователя")
    ap.add_argument("--target-raw", default=None,
                    help="(опц.) Файл с СЫРЫМ извлечением страницы (до очистки). "
                         "Нужен, чтобы отличать 'нет на странице' от 'есть в UI, но не в прозе'.")
    ap.add_argument("--competitors", required=True, help="Папка с .txt конкурентов")
    ap.add_argument("--query", required=True, help="Целевой запрос")
    ap.add_argument("--out", default="stats.json")
    ap.add_argument("--top-terms", type=int, default=40, help="Сколько топ-терминов выводить")
    args = ap.parse_args()

    lemma = make_lemmatizer()

    target_raw = read_text(args.target)
    target_lemmas = lemmatize(target_raw, lemma)
    target_counts = Counter(target_lemmas)
    target_set = set(target_lemmas)
    target_wordcount = len(tokens(target_raw))

    # Леммы со ВСЕЙ страницы (сырое извлечение), чтобы отличать UI от прозы.
    raw_page_set = set()
    if args.target_raw:
        raw_page_set = set(lemmatize(read_text(args.target_raw), lemma))

    # Запрос
    query_lemmas = lemmatize(args.query, lemma)
    query_hit = [q for q in query_lemmas if q in target_set]
    query_miss = [q for q in query_lemmas if q not in target_set]
    query_coverage = round(len(query_hit) / len(query_lemmas), 3) if query_lemmas else 0.0

    # Конкуренты
    comp_files = sorted(
        os.path.join(args.competitors, f)
        for f in os.listdir(args.competitors)
        if f.lower().endswith(".txt")
    )
    if not comp_files:
        sys.exit(f"В папке {args.competitors} нет .txt файлов конкурентов.")

    comp_wordcounts = []
    corpus_counts = Counter()        # суммарная частота по всем конкурентам
    doc_frequency = Counter()        # в скольких документах встречается лемма
    for cf in comp_files:
        raw = read_text(cf)
        comp_wordcounts.append(len(tokens(raw)))
        lemmas = lemmatize(raw, lemma)
        corpus_counts.update(lemmas)
        for l in set(lemmas):
            doc_frequency[l] += 1

    n_comp = len(comp_files)
    median_comp_words = int(statistics.median(comp_wordcounts)) if comp_wordcounts else 0

    # "Недобранные" ключи: встречаются минимум у половины конкурентов,
    # но отсутствуют/редки у пользователя. Сортируем по охвату документов, затем частоте.
    threshold_docs = max(2, (n_comp + 1) // 2)
    missing = []
    for term, dfreq in doc_frequency.most_common():
        if dfreq < threshold_docs:
            continue
        if target_counts.get(term, 0) == 0:
            # где термин: ui_only (есть на странице, но не в прозе) или absent (нет нигде)
            if args.target_raw:
                where = "ui_only" if term in raw_page_set else "absent"
            else:
                where = "unknown"
            missing.append({
                "term": term,
                "competitor_docs": dfreq,
                "competitor_total": corpus_counts[term],
                "in_target": 0,
                "where": where,
            })
        if len(missing) >= args.top_terms:
            break

    payload = {
        "query": args.query,
        "query_lemmas": query_lemmas,
        "query_coverage": query_coverage,
        "query_hit": query_hit,
        "query_miss": query_miss,
        "target_wordcount": target_wordcount,
        "competitor_count": n_comp,
        "competitor_wordcounts": comp_wordcounts,
        "median_competitor_wordcount": median_comp_words,
        "target_top_terms": target_counts.most_common(args.top_terms),
        "corpus_top_terms": corpus_counts.most_common(args.top_terms),
        "missing_keywords": missing,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Покрытие запроса: {query_coverage:.0%} (нет в тексте: {', '.join(query_miss) or '—'})")
    print(f"Объём текста: {target_wordcount} слов | медиана топ-{n_comp}: {median_comp_words}")
    if args.target_raw:
        ui = sum(1 for m in missing if m["where"] == "ui_only")
        ab = sum(1 for m in missing if m["where"] == "absent")
        print(f"Недобранных ключей: {len(missing)} (нет нигде: {ab}, есть в UI но не в прозе: {ui})")
    else:
        print(f"Недобранных ключей (есть у ≥{threshold_docs} конкурентов): {len(missing)}")
    print(f"Подробности записаны в {args.out}")


if __name__ == "__main__":
    main()
