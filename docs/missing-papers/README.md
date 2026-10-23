# GEG own papers still without a PDF

The group's publication platform, geg.ethz.ch/publications, lists papers that the literature RAG
cannot answer from, because nobody has the PDF. These 81 papers are open for anyone in the group to
find. Talks and posters are not listed; they have no PDF to find.

State on 2026-10-22: every paper here was tried once and was not reachable. It is not open access,
not a full text in the ETH Research Collection, and not in the former RAG bucket.

| File | What it is |
|---|---|
| [PAPERS_TO_GET.md](PAPERS_TO_GET.md) | The list as clickable links, grouped by what to try. Start here. |
| `still_to_get.csv` | The source of the list: title, DOI or link, why it failed, platform page, who tried when. |

## Find a paper

The list has three groups. Each needs a different approach.

1. **Paywalled.** Open the link on the ETH network or through the ETH VPN. If ETH has no
   subscription, order the paper through ETH Library document delivery, or email an author from the
   group.
2. **No DOI or link.** Mostly conference proceedings. Use the Scholar link. If nothing turns up, ask
   the first author.
3. **Theses.** Ask the author or the ETH Library.

## When you have the PDF

1. Upload it with the tool from this repository. The tool's setup is in the
   [main README](../../README.md#use).

   ```bash
   geg-rag-upload upload paper.pdf --dry-run    # check the name it picks
   geg-rag-upload upload paper.pdf
   ```

   If the paper has no DOI, the tool asks for one. Pass the title from the list instead:
   `--title "Exact title from the list"`.

2. Remove the paper's row from `still_to_get.csv`, then rebuild the list:

   ```bash
   uv run python scripts/missing_list.py docs/missing-papers/still_to_get.csv docs/missing-papers/PAPERS_TO_GET.md
   ```

3. Open a pull request with both files. One PR for several papers is fine.

**Never commit a PDF to this repository.** It is public, and most of these papers are under the
publisher's copyright. The PDF goes into the bucket only.

## When you cannot get it

Fill in `tried_by`, `tried_on` and `outcome` in that paper's row of `still_to_get.csv`, so the next
person knows what was already tried. Then open a pull request as above. Replace the earlier entry; the
latest attempt is what matters.

## How the list was made

On 2026-10-22, every platform record flagged as GEG own was compared with the PDFs collected from
the old group website and with the former RAG bucket. Open-access copies were fetched automatically.
What could not be found is this list. The one-off scripts that built it are not kept here. From now
on, the CSV is maintained by hand through pull requests.
