# Semantic vector provenance

The 50-dimensional GloVe Wikipedia 2014 and Gigaword 5 pretrained weights are by Jeffrey Pennington, Richard Socher and Christopher D. Manning. Stanford distributes these weights under the Open Data Commons Public Domain Dedication and License v1.0. The source used here is the Gensim distribution of the same weights. The repository bundles a selected and quantised derivative. It contains no text from the source corpora and is used only to rank the fictional catalogue.

- [Stanford GloVe project and licence declaration](https://nlp.stanford.edu/projects/glove/)
- [PDDL 1.0 licence](https://opendatacommons.org/licenses/pddl/1-0/)
- [Gensim release](https://github.com/RaRe-Technologies/gensim-data/releases/tag/glove-wiki-gigaword-50)

To reproduce the table from the repository root, download the source asset and verify its digest, then run the packer. The source is roughly 66 MiB and is needed only for rebuilding the table.

```sh
curl -fL -o /tmp/silt-relay-glove-50.gz \
  https://github.com/RaRe-Technologies/gensim-data/releases/download/glove-wiki-gigaword-50/glove-wiki-gigaword-50.gz
shasum -a 256 /tmp/silt-relay-glove-50.gz
python3 tools/pack_vectors.py /tmp/silt-relay-glove-50.gz
shasum -a 256 data/vectors.tsv
```

| File | SHA-256 |
| --- | --- |
| Source gzip | `5c55f98957aa9fed8d2ac5fb1dcff57af3b23c5a3ee7af3f7945f8d49198eb24` |
| Bundled vectors | `de63d137404f9f5e00a0c490ec0d754b8ee3fc04aad61f0d3854cfed19636733` |

The packer selects from the first 12,000 upstream entries and adds words that occur in the catalogue. It drops stop words and multi-token entries, normalises each vector and rounds it to signed bytes. The ASCII table stores a word, a tab and the Base64 encoding of its 50 signed bytes per row.
