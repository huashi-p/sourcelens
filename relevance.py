import re


def normalize_text(value):
    value = (value or "").casefold()
    return re.sub(r"\s+", " ", value).strip()


def split_paragraphs(text):
    return [
        paragraph.strip()
        for paragraph in text.split("\n\n")
        if paragraph.strip()
    ]

def query_terms(question):
    normalized = normalize_text(question)
    english = re.findall(r"[a-z0-9_]{2,}", normalized)
    chinese = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    return set(english + chinese)


def select_relevant_segments(question, text, limit=8, max_chars=800):
    paragraphs = split_paragraphs(text)
    terms = query_terms(question)
    scored = []

    for index, paragraph in enumerate(paragraphs):
        searchable = normalize_text(paragraph)
        score = sum(searchable.count(term) for term in terms)
        scored.append(
            {
                "index": index,
                "text": paragraph[:max_chars],
                "score": score,
            }
        )

    if any(item["score"] > 0 for item in scored):
        scored = [
            item
            for item in scored
            if item["score"] > 0
        ]

    scored.sort(
        key=lambda item: (item["score"], -item["index"]),
        reverse=True,
    )

    selected = []
    seen = set()

    for item in scored:
        fingerprint = normalize_text(item["text"])

        if fingerprint in seen:
            continue

        seen.add(fingerprint)
        selected.append(item)

        if len(selected) >= limit:
            break

    selected.sort(key=lambda item: item["index"])
    return [item["text"] for item in selected]