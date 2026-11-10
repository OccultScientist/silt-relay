# Silt Relay

**A crate-digging tool for a fictional drum & bass label.**

Start with a sound, an instrument or a mood across 21 fictional releases. Ask for a format and follow the matches to the release notes. For a linked reissue, the reader compares the original and reissue tracklists and shows where each change comes from.

Try “mellow keys and a brushed break on vinyl”, “which records sound like Basin Window?” or “what did the vinyl reissue of Silt Thread add?”. The catalogue Q&A and ranking comparison are also available from the reader.

[Open the live demo](https://occultscientist.github.io/silt-relay/)

## Run it

Clone the repository and run these commands in its root. Use Python 3.9+ with SQLite FTS5 enabled. The corpus and the small, quantised embedding table are bundled. The CLI works offline with the Python standard library.

```sh
python3 silt_relay.py --dig 'Liquid electric piano on vinyl. What changed on the reissue?'
python3 silt_relay.py --editions SR001
python3 silt_relay.py 'When did Glass Current come out, and did the vinyl ship?'
python3 silt_relay.py 'When was Basin Window released?'
python3 silt_relay.py --search --mode semantic 'horns and echoes'
python3 evaluate.py --discovery
python3 evaluate.py --audit
python3 evaluate.py
python3 -m unittest discover -s tests -v
```

Use `--mode bm25`, `semantic` or `hybrid` to compare ranking methods. Discovery defaults to hybrid. The exact lookup tool defaults to BM25.

## Run the browser interface locally

```sh
python3 tools/build_site.py
python3 -m http.server 8000 --bind 127.0.0.1 --directory _site
```

Open [localhost:8000](http://127.0.0.1:8000). The first build downloads and verifies the pinned Pyodide runtime. The staged site is about 14 MB before transport compression. It runs the same Python module in a browser worker. GitHub Pages serves the static build from the `gh-pages` branch, including the runtime, so questions never leave the browser.

## How crate digging works

1. **Read the request.** Pull out supported format and reissue constraints, then rank the sound passages. A small, shared cue vocabulary covers wording such as “horns” and “brass”. Each result exposes the wording it found and any requested cues it could not confirm. Sound ranks can use BM25, local GloVe vectors or reciprocal rank fusion.
2. **Join the editions.** An explicit catalogue link connects a reissue to its original. The sound note can be from one edition and the format from another, with each citation labelled separately. A proposed pressing is shown separately from released formats.
3. **Compare the tracklists.** Compute additions and tracks listed only on the original directly from the two quoted tracklists. The comparison also exposes both dates, formats and the note documenting the reissue relationship.

The search handles positive descriptions and a small set of format and relationship phrases. “Digital only” restricts the documented media, and an explicit original or catalogue number restricts which edition can supply the format. A follow-up such as “Was it ever released on vinyl?” checks the matches from the first request. Suggestions for “sounds like” quote the reference and candidate notes and show their shared wording. Mood cues are approximate, and partial sound matches flag descriptors the passage does not confirm.

## Discovery evaluation

Run `python3 evaluate.py --discovery` against the [17 labelled requests](data/discovery.json). The cases check ranking, format constraints and alternatives, family linkage, both tracks in a comparison, and withholding. Citations must match the original passage and belong to the release family where they appear.

| Ranking | Full cases | Required passages | Tracklist comparisons | Withholding |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 16/17 | 35/35 | 3/3 | 8/8 |
| Semantic | 17/17 | 35/35 | 3/3 | 8/8 |
| Hybrid | 17/17 | 35/35 | 3/3 | 8/8 |

For “a choir on a sparse beat”, BM25 found *Glass Currents* but ranked *Sedge Relay* ahead of it. Semantic and hybrid ranked the expected release first. These are author-labelled checks on a tiny fictional collection. The set includes regression cases found while building. Inspect the [per-case report](reports/discovery.json) for the actual miss and judge relevance from the notes.

### Portfolio audit

The [12 review questions](data/audit.json) came from a separate review of the crate-digging engine. They exposed failures around digital-only requests, original versus reissue formats, mixed format logic and “sounds like” returning the reference itself. The corrected version passes all 12 cases in each mode. These are regression checks because the review informed the fixes. The [audit report](reports/audit.json) includes the source and withholding counts. Use `python3 evaluate.py --audit` to rerun it.

## How answers work

1. **Resolve the release and requested detail.** The engine uses exact catalogue numbers or titles and a small set of question patterns. It asks for clarification when a title refers to multiple editions.
2. **Retrieve eligible evidence.** SQLite FTS5 supplies BM25. The semantic experiment averages local 50-dimensional GloVe word vectors and ranks by cosine similarity. Hybrid uses reciprocal rank fusion. Evidence for an answer must match the resolved release and requested field. The unfiltered search results are separate and show what the ranking itself found.
3. **Compose a bounded answer.** The engine quotes the passage verbatim and attaches its stable ID. The four outcomes are **answered**, **partially answered**, **needs clarification** and **insufficient evidence**. For this archive, generation is extractive and deterministic. An LLM is unnecessary for presenting these short passages.

A passage can match a search and still be irrelevant to the question. The evidence panel distinguishes cited passages from search candidates. For example, a note recording a proposed vinyl pressing gives no basis for saying it shipped.

### A lesson from the first pass

Toby asked us to check that each citation supports the specific claim. In review, the first version answered a question about the proposed *Glass Current* vinyl edition with the date of the digital EP. The date came straight from the notes and still answered the wrong question. There is now a [regression test](tests/test_engine.py) for that distinction.

## Evaluation

The labelled set has 10 development questions and 25 evaluation questions. It exercises paraphrases, multi-release questions, ambiguous editions, unsupported requests and a prompt asking the system to invent a figure. The labels name expected passages, outcomes and clarification choices.

| Retrieval mode | Search recall@5 | Answer outcomes | Supported citations | Required answer evidence | Withholding cases |
| --- | ---: | ---: | ---: | ---: | ---: |
| BM25 | 7/9 | 15/17 | 10/10 | 10/12 | 9/9 |
| Semantic | 5/9 | 15/17 | 10/10 | 10/12 | 9/9 |
| Hybrid | 7/9 | 15/17 | 10/10 | 10/12 | 9/9 |

Search recall counts relevant passages found in the top five over all labelled relevant passages across the eight search questions. Citation support checks both that the quote is exact and that its source is labelled as supporting the specific question. Withholding counts partial, ambiguous and unanswerable cases that return the expected outcome, evidence and choices. The field constraints explain why the three modes tie on these answer questions.

**BM25 is the default for catalogue Q&A.** Hybrid ties it on this set, and the dense model misses some paraphrases. All modes miss the production credit on *Mudlark Phase* and ask for clarification on “the original Basin Window”. Those failures show the limits of the bounded question parser. The first evaluation pass also caught a plural “tracklists” bug, which was fixed with a regression test before this report was recorded. These are small, author-labelled results on a synthetic corpus.

Read the [per-case misses and run details](reports/evaluation.json), inspect the [labels](data/evaluation.json), or rerun the development split with `python3 evaluate.py --split development`.

## Data and provenance

All releases, artists, dates and label activity in [the catalogue](data/releases.json) are fictional. The vector table is a separate retrieval asset. It contains quantised 50d GloVe weights for common vocabulary and terms appearing in the fictional notes, selected independently of the evaluation questions. Stanford distributes the pretrained weights under the [Open Data Commons PDDL 1.0](https://opendatacommons.org/licenses/pddl/1-0/). See [vector provenance](data/VECTORS.md) for the upstream source and rebuild instructions.
