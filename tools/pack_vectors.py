"""Pack a Gensim-format GloVe 50d gzip file. Corpus vocabulary is independent of evaluation questions."""
import argparse
import base64
import gzip
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from silt_relay import DATA, keywords


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    releases = json.loads((DATA / "releases.json").read_text(encoding="utf-8"))
    catalogue_words = set(keywords(" ".join(
        value for release in releases for value in [release["title"], *release["notes"].values()]
    )))

    with gzip.open(args.source, "rt", encoding="utf-8") as glove, (DATA / "vectors.tsv").open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        next(glove)  # Gensim header contains vocabulary size and dimensions.
        for index, line in enumerate(glove):
            word, _, values = line.partition(" ")
            if index >= 12000 and word not in catalogue_words:
                continue
            if keywords(word) != [word]:
                continue
            vector = [float(value) for value in values.split()]
            norm = math.sqrt(sum(value * value for value in vector))
            if norm:
                packed = struct.pack("50b", *(round(127 * value / norm) for value in vector))
                output.write(f"{word}\t{base64.b64encode(packed).decode('ascii')}\n")


if __name__ == "__main__":
    main()
