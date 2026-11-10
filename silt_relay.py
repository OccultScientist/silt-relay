"""Offline retrieval and evidence-bound answers for the fictional Silt Relay archive."""

import argparse
import base64
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import unicodedata

DATA = Path(__file__).resolve().parent / "data"
MODES = ("bm25", "semantic", "hybrid")
DEFAULT_MODE = "bm25"
TOP_K = 5
MAX_QUESTION = 400
FIELDS = {
    "date": r"\b(?:when|dates?|came out|come out|released earlier)\b",
    "format": r"\b(?:formats?|physical|digital|cassette|vinyl|wax|12[ -]inch|media)\b",
    "tracks": r"\b(?:tracks?|tracklists?|track listings?|songs?|b[ -]side)\b",
    "credits": r"\b(?:credits?|credited|artists?|who (?:made|is behind|recorded)|by whom)\b",
    "sound": r"\b(?:sound(?:s|ing)?|sounded|sounding like|style|describe|drums|bassline|percussion)\b",
    "edition": r"\b(?:recut|reissue|edition|propos(?:ed|al)|planned|pressing)\b",
}
UNSUPPORTED = re.compile(
    r"\b(?:sales?|sold|sell|price|cost|streams?|chart(?:ed|s)?|shipment|shipp?ed|ship|dispatch(?:ed)?|"
    r"manufactur\w*|pressing size|how many copies|who (?:mixed|mastered|produced)|"
    r"bpm|tempo|key signature|isrc|barcode|spotify|bandcamp|rights|owns?|ownership|licen[cs]\w*|royalt\w*|review\w*|"
    r"why|best|recommend\w*|first ever|release time|time zone|label owner)\b"
)
STOP = frozenset("""
a an and are as at be been but by can could did do does for from had has have how i in is it its
me of on or our s so than that the their them there these they this to was were what when where
which who will with would you your tell about show please
""".split())


def words(text):
    folded = unicodedata.normalize("NFKD", text.casefold())
    return re.findall(r"[a-z0-9]+", folded.encode("ascii", "ignore").decode("ascii"))


def keywords(text):
    return list(dict.fromkeys(word for word in words(text) if word not in STOP))


def question_text(question):
    question = question.strip()
    if not question or len(question) > MAX_QUESTION:
        raise ValueError(f"Enter a question of 1–{MAX_QUESTION} characters.")
    return question


@dataclass(frozen=True)
class Passage:
    id: str
    code: str
    title: str
    field: str
    text: str


class Embeddings:
    def __init__(self, path):
        self.vectors = {}
        with path.open(encoding="utf-8") as handle:
            for row in handle:
                word, encoded = row.rstrip("\n").split("\t")
                self.vectors[word] = struct.unpack("50b", base64.b64decode(encoded))

    def lookup(self, word):
        vector = self.vectors.get(word)
        if vector is None and len(word) > 4 and word.endswith("s"):
            vector = self.vectors.get(word[:-1])
            if vector is None and word.endswith("es"):
                vector = self.vectors.get(word[:-2])
        return vector

    def encode(self, text):
        vectors = [vector for word in keywords(text) if (vector := self.lookup(word)) is not None]
        if not vectors:
            return ()
        mean = tuple(map(sum, zip(*vectors)))
        norm = math.sqrt(sum(value * value for value in mean))
        return tuple(value / norm for value in mean) if norm else ()


class Archive:
    def __init__(self, releases, embeddings):
        self.releases = {release["code"]: release for release in releases}
        self.passages = {}
        self.title_index = {}
        for release in releases:
            code = release["code"]
            for title in [release["title"], *release["aliases"]]:
                key = " ".join(words(title))
                self.title_index.setdefault(key, set()).add(code)
            for field, text in release["notes"].items():
                source_id = f"{code}:{field}"
                self.passages[source_id] = Passage(source_id, code, release["title"], field, text)
        self.embeddings = embeddings
        self.vectors = {p.id: embeddings.encode(p.text) for p in self.passages.values()}

        self.db = sqlite3.connect(":memory:")
        try:
            self.db.execute(
                "CREATE VIRTUAL TABLE archive USING fts5(id UNINDEXED, code, title, field, text, "
                "tokenize='porter unicode61')"
            )
            self.db.executemany(
                "INSERT INTO archive VALUES (?, ?, ?, ?, ?)",
                ((p.id, p.code, p.title, p.field, p.text) for p in self.passages.values()),
            )
        except sqlite3.OperationalError as error:
            self.db.close()
            raise RuntimeError("Silt Relay needs a Python build with SQLite FTS5 enabled.") from error

    @classmethod
    def from_directory(cls, directory):
        directory = Path(directory)
        releases = json.loads((directory / "releases.json").read_text(encoding="utf-8"))
        return cls(releases, Embeddings(directory / "vectors.tsv"))

    def close(self):
        self.db.close()

    def search(self, query, mode=DEFAULT_MODE, *, limit=TOP_K, code=None, field=None):
        if mode not in MODES:
            raise ValueError(f"Choose one of {', '.join(MODES)}.")
        query = question_text(query)
        terms = keywords(query)
        if not terms:
            return []
        allowed = {
            p.id for p in self.passages.values()
            if (code is None or p.code == code) and (field is None or p.field == field)
        }

        lexical = []
        if mode in ("bm25", "hybrid"):
            match = " OR ".join(f'"{term}"' for term in terms)
            lexical = [
                source_id for source_id, in self.db.execute(
                    "SELECT id FROM archive WHERE archive MATCH ? "
                    "ORDER BY bm25(archive, 0, 3, 2, 1, 1), id",
                    (match,),
                ) if source_id in allowed
            ]

        dense = []
        if mode in ("semantic", "hybrid"):
            query_vector = self.embeddings.encode(query)
            if query_vector:
                similarities = {
                    source_id: sum(a * b for a, b in zip(query_vector, self.vectors[source_id]))
                    for source_id in allowed if self.vectors[source_id]
                }
                dense = sorted(similarities, key=lambda item: (-similarities[item], item))

        bm25_rank = {source_id: rank for rank, source_id in enumerate(lexical, 1)}
        semantic_rank = {source_id: rank for rank, source_id in enumerate(dense, 1)}
        if mode == "hybrid":
            ranked = sorted(bm25_rank.keys() | semantic_rank.keys(), key=lambda item: (
                -sum(1 / (10 + ranks[item]) for ranks in (bm25_rank, semantic_rank) if item in ranks),
                item,
            ))
        else:
            ranked = lexical if mode == "bm25" else dense
        return [
            {
                "id": p.id, "code": p.code, "title": p.title, "field": p.field, "text": p.text,
                "bm25_rank": bm25_rank.get(p.id), "semantic_rank": semantic_rank.get(p.id),
            }
            for p in (self.passages[source_id] for source_id in ranked[:limit])
        ]

    def resolve(self, text):
        tokens = words(text)
        explicit = list(dict.fromkeys(word.upper() for word in tokens if re.fullmatch(r"sr\d{3}", word)))
        qualifiers = {code.upper() for code in re.findall(r"\((sr\d{3})\)", text, re.IGNORECASE)}
        matches = []
        for start in range(len(tokens)):
            for end in range(len(tokens), start, -1):
                codes = self.title_index.get(" ".join(tokens[start:end]))
                if codes:
                    matches.append((start, end, codes))
                    break
        groups = [{code} if code in self.releases else set() for code in explicit]
        for start, end, codes in matches:
            if any(other_start <= start and end <= other_end and (start, end) != (other_start, other_end)
                   for other_start, other_end, _ in matches):
                continue
            if not codes.intersection(qualifiers) and codes not in groups:
                groups.append(codes)
        return groups

    def answer(self, question, mode=DEFAULT_MODE):
        question = question_text(question)
        diagnostic_hits = self.search(question, mode)
        targets = self.resolve(question)
        result = {
            "outcome": "insufficient_evidence", "mode": mode, "claims": [],
            "unanswered": [], "choices": [], "retrieved": [], "search_hits": diagnostic_hits,
        }
        ambiguous = set().union(*(group for group in targets if len(group) > 1))
        if ambiguous:
            result["outcome"] = "needs_clarification"
            result["choices"] = [
                {key: self.releases[code][key] for key in ("code", "title", "artist")}
                for code in sorted(ambiguous)
            ]
            return result
        if not targets:
            result["unanswered"].append(
                "I couldn't identify a release. Try its exact title or catalogue number."
            )
            return result

        parts = re.split(
            r"\s*[;?]\s*|,?\s+and\s+(?=(?:did|does|was|were|who|what|which|when|how|where|"
            r"whether|in what)\b)|\s+(?:and|with)\s+(?=(?:the )?(?:dates?|formats?|tracklists?|"
            r"credits?|sound|edition)\s+of\b)",
            question, flags=re.IGNORECASE,
        )
        evidence = {}
        for part in filter(None, parts):
            groups = self.resolve(part)
            if not groups and len(targets) == 1 and re.search(
                r"\b(?:it|its|that release)\b|^did the vinyl\b", part, re.IGNORECASE
            ):
                groups = targets
            intent = re.sub(r"\bsr\d{3}\b", " ", " ".join(words(part)))
            for group in groups:
                for code in group:
                    # Strip release names so words inside a title cannot create a field request.
                    release = self.releases[code]
                    for title in sorted([release["title"], *release["aliases"]], key=len, reverse=True):
                        intent = re.sub(r"\b" + re.escape(" ".join(words(title))) + r"\b", " ", intent)
            if UNSUPPORTED.search(intent):
                result["unanswered"].append(f"The notes don’t establish an answer to “{part.strip()}”")
                continue

            fields = [field for field, pattern in FIELDS.items() if re.search(pattern, intent)]
            # The first pass gave Glass Current's digital date for a vinyl question.
            # A real quote still needs to answer the question as phrased.
            date_words = {
                "date", "dates", "release", "released", "come", "came", "out",
                "compare", "catalogue", "number", "original", "format", "formats",
            }
            if "date" in fields and set(keywords(intent)) - date_words:
                result["unanswered"].append("I can cite the release date for the catalogue entry as a whole.")
                continue
            if "tracks" in fields and "sound" in fields and re.search(r"\b(?:sound|style|describe)\b", intent):
                fields.remove("tracks")
            if "edition" in fields and "format" in fields:
                fields.remove("format")
            if not fields:
                result["unanswered"].append(f"I couldn't identify a supported catalogue detail in “{part.strip()}”")
                continue
            if not groups:
                result["unanswered"].append(f"I couldn't identify the release in “{part.strip()}”")
                continue
            if len(groups) > 1 and len(fields) > 1:
                result["unanswered"].append("Ask about one catalogue detail at a time when comparing releases.")
                continue
            # A second title can be missing from this little catalogue. Keep the
            # first answer and leave the other half visibly open.
            if len(groups) == 1:
                segments = re.split(r"\s+(?:and|or|with)\s+", part, flags=re.IGNORECASE)
                for segment in segments[1:]:
                    if self.resolve(segments[0]) and not self.resolve(segment) and keywords(segment):
                        result["unanswered"].append(f"I couldn't identify a second release in “{segment.strip()}”")
                        break
            for group in groups:
                if not group:
                    result["unanswered"].append("That catalogue number is missing from the archive.")
                    continue
                code, = group
                for field in fields:
                    # The entity and requested field are hard constraints. Ranked near misses
                    # in the diagnostic search can never become evidence for this claim.
                    hits = self.search(f"{code} {field}", mode, code=code, field=field, limit=1)
                    if hits:
                        evidence[hits[0]["id"]] = hits[0]
                    else:
                        result["unanswered"].append(f"I found no {field} passage for {code} in this search mode.")

        result["retrieved"] = list(evidence.values())
        # Visitors should see the same words when they open the cited passage.
        result["claims"] = [{"text": hit["text"], "source_id": hit["id"]} for hit in evidence.values()]
        if evidence:
            result["outcome"] = "partially_answered" if result["unanswered"] else "answered"
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--mode", choices=MODES, default=DEFAULT_MODE)
    parser.add_argument("--search", action="store_true", help="Show ranked passages without composing an answer.")
    args = parser.parse_args()
    archive = Archive.from_directory(DATA)
    try:
        result = archive.search(args.question, args.mode) if args.search else archive.answer(args.question, args.mode)
    except ValueError as error:
        parser.error(str(error))
    finally:
        archive.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
