import re
import unicodedata


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def split_text(text, max_chars=800, overlap=120):
    if max_chars < 100:
        raise ValueError("max_chars 不能小于 100")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap 必须小于 max_chars")

    text = normalize_text(text)
    paragraphs = [
        part.strip()
        for part in text.split("\n\n")
        if part.strip()
    ]
    chunks = []
    current = ""
    step = max_chars - overlap

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""

            for start in range(0, len(paragraph), step):
                piece = paragraph[start:start + max_chars].strip()
                if piece:
                    chunks.append(piece)
                if start + max_chars >= len(paragraph):
                    break
            continue

        candidate = (
            paragraph
            if not current
            else current + "\n\n" + paragraph
        )

        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            current = paragraph

    if current:
        chunks.append(current)

    unique = []
    seen = set()
    for chunk in chunks:
        fingerprint = normalize_text(chunk)
        if fingerprint and fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(chunk)

    return unique
