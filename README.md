# Silt Relay

**An evidence-first search and Q&A demo for a fictional drum & bass label.**

The catalogue contains 20 invented releases. Ask about a date, format, tracklist, credit, sound or edition. The answer opens the exact release-note passage it came from. Try asking about a vinyl pressing that was proposed, sales figures that were never recorded, or a title shared by two editions.

[Open the live demo](https://occultscientist.github.io/silt-relay/)

## Run it

Clone the repository and run these commands in its root. Use Python 3.9+ with SQLite FTS5 enabled. The corpus and the small, quantised embedding table are bundled. The CLI works offline with the Python standard library.

```sh
python3 silt_relay.py 'When did Glass Current come out, and did the vinyl ship?'
python3 silt_relay.py 'When was Basin Window released?'
python3 silt_relay.py --search --mode semantic 'horns and echoes'
python3 evaluate.py
python3 -m unittest discover -s tests -v
```

The first command returns one claim with `SR004:date` and a separate unanswered part. The second offers two catalogue numbers so you can ask again. Use `--mode bm25`, `semantic` or `hybrid` with either command.

## Run the browser interface locally

```sh
python3 tools/build_site.py
python3 -m http.server 8000 --bind 127.0.0.1 --directory _site
```

Open [localhost:8000](http://127.0.0.1:8000). The first build downloads and verifies the pinned Pyodide runtime. The staged site is about 14 MB before transport compression. It runs the same Python module in a browser worker. GitHub Pages serves the static build from the `gh-pages` branch, including the runtime, so questions never leave the browser.

## How answers work

1. **Resolve the release and requested detail.** The engine uses exact catalogue numbers or titles and a small set of question patterns. It asks for clarification when a title refers to multiple editions.
2. **Retrieve eligible evidence.** SQLite FTS5 supplies BM25. The semantic experiment averages local 50-dimensional GloVe word vectors and ranks by cosine similarity. Hybrid uses reciprocal rank fusion. Evidence for an answer must match the resolved release and requested field. The unfiltered search results are separate and show what the ranking itself found.
3. **Compose a bounded answer.** The engine quotes the passage verbatim and attaches its stable ID. The four outcomes are **answered**, **partially answered**, **needs clarification** and **insufficient evidence**. For this archive, generation is extractive and deterministic. An LLM is unnecessary for presenting these short passages.

A passage can match a search and still be irrelevant to the question. The evidence panel distinguishes cited passages from search candidates. For example, a note recording a proposed vinyl pressing gives no basis for saying it shipped.

## Evaluation

The labelled set has 10 development questions and 25 evaluation questions. It exercises paraphrases, multi-release questions, ambiguous editions, unsupported requests and a prompt asking the system to invent a figure. The labels name expected passages, outcomes and clarification choices.

| Retrieval mode | Search recall@5 | Answer outcomes | Supported citations | Required answer evidence | Withholding cases |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 7/9 | 15/17 | 10/10 | 10/12 | 9/9 |
| Semantic | 5/9 | 15/17 | 10/10 | 10/12 | 9/9 |
| Hybrid | 7/9 | 15/17 | 10/10 | 10/12 | 9/9 |

Search recall counts relevant passages found in the top five over all labelled relevant passages across the eight search questions. Citation support checks both that the quote is exact and that its source is labelled as supporting the specific question. Withholding counts partial, ambiguous and unanswerable cases that return the expected outcome, evidence and choices. The field constraints explain why the three modes tie on these answer questions.

**BM25 is the default.** Hybrid ties it on this set, and the dense model misses some paraphrases. All modes miss the production credit on *Mudlark Phase* and ask for clarification on “the original Basin Window”. Those failures show the limits of the bounded question parser. The first evaluation pass also caught a plural “tracklists” bug, which was fixed with a regression test before this report was recorded. These are small, author-labelled results on a synthetic corpus.

Read the [per-case misses and run details](reports/evaluation.json), inspect the [labels](data/evaluation.json), or rerun the development split with `python3 evaluate.py --split development`.

## Data and provenance

All releases, artists, dates and label activity in [the catalogue](data/releases.json) are fictional. The vector table is a separate retrieval asset. It contains quantised 50d GloVe weights for common vocabulary and terms appearing in the fictional notes, selected independently of the evaluation questions. Stanford distributes the pretrained weights under the [Open Data Commons PDDL 1.0](https://opendatacommons.org/licenses/pddl/1-0/). See [vector provenance](data/VECTORS.md) for the upstream source and rebuild instructions.
