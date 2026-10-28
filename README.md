# literature-rag

The GEG literature RAG. A paper uploaded with `geg-rag-upload` lands in a bucket under its DOI
name, a Cloud Function imports it into a Vertex AI RAG corpus, and `GEG-Publication-Corpus-Agent`
answers questions only from that corpus, citing author, year, title and DOI. This repository holds
all of it: the upload tool, the ingestion function, the agent, and the Terraform that owns their
GCP resources.

Forked from [danielvogler/Gemini-Rag-Automator](https://github.com/danielvogler/Gemini-Rag-Automator)
(MIT) on 2026-10-23; self-sufficient since.

## Ask a question

Open the [playground of `GEG-Publication-Corpus-Agent`](https://console.cloud.google.com/agent-platform/runtimes/locations/europe-west1/agent-engines/4185840766943232000/playground?project=geg-core-dev),
or in the GCP Console, project `geg-core-dev`: Agent Platform → Agents → Deployments →
`GEG-Publication-Corpus-Agent` → Playground. You need GCP access, see geg-ops
`computing/infrastructure/gcp.md`. From a terminal, after the setup below:

```bash
just agent-query "What did Ezzat et al. 2021 find about ..."
```

The agent abstains with a fixed sentence when the corpus has nothing on the question. It never
uses general knowledge.

## Add a paper

Published versions only. An accepted manuscript that is not yet published, a preprint of a paper
that has a published version, or anything under embargo does not go into the bucket.

Once:

```bash
gcloud auth login
gcloud auth application-default login
uv tool install git+https://github.com/GEG-ETHZ/literature-rag
```

Per paper:

```bash
geg-rag-upload upload paper.pdf                 # --dry-run shows the plan without uploading
geg-rag-upload upload paper.pdf --doi 10.1000/x # when the PDF carries no DOI
geg-rag-upload migrate ~/papers --dry-run       # a whole folder, or gs://some-bucket
```

The tool prints one line per file: source, DOI, target name, action and reason. Exit code 1 means at
least one file needs `--doi` or `--title`. The function ingests the new object within one to two
minutes.

### How a file is named

| Found | Object name | Example |
|---|---|---|
| DOI in PDF metadata or on the first two pages, confirmed at doi.org | DOI, lower case, `/` and other unsafe characters become `_` | `10.1016_j.cesys.2022.100086.pdf` |
| No DOI, but a title (Crossref, PDF metadata or the largest-font line on page 1) | `python-slugify` of the title, at most 120 characters | `natural-convection-in-porous-media.pdf` |
| Neither | the tool stops and asks for `--doi` or `--title` | |

### When a file is skipped

- The target name already exists in the bucket. `--force` overwrites, but only for a project
  admin: group members hold `objectCreator` and `objectViewer` on the bucket, which cannot
  replace or delete an object, so a wrong PDF under a DOI name is fixed by an admin, not by a
  second upload.
- A byte-identical file exists under any name. Never overridden; a second copy helps nobody.

DOI, title, year, first author, original file name, uploader and time are written to the object's
custom metadata. The agent reads them back to render each citation, so the bucket stays flat and
still searchable.

## Layout

```text
src/uploader/        geg-rag-upload: doi, naming, plan (pure), pdfmeta, crossref, bucket, cli
src/ingestor/        the Cloud Function: Eventarc on object.finalized → rag.import_files, with retry
src/local_ingestor/  geg-rag-ingest: re-run the handler locally for one object
src/agent/           the corpus-only ADK agent: tool, callbacks, prompt, citation rendering
scripts/             deploy_agent.py, query_agent.py, query_rag.py, list_rag_files.py,
                     init_rag_corpus.py, import_bucket.py, switch-agent-corpus.sh, missing_list.py
terraform/           bucket, service account, IAM, secret, function, staging bucket; GCS state
docs/                migration record (2026-10) and the missing-papers list
tests/               one file per module; the CLI is tested against a fake store
```

## Deployment in geg-core-dev

Everything runs in project `geg-core-dev`, region `europe-west1` (Gemini and RAG Engine are both
served there; `europe-west6` is not). Nothing below is secret; the corpus resource name sits in
Secret Manager and the agent's `.env` is never committed.

| What | Name |
|---|---|
| Papers bucket | `geg-core-dev-rag-own-publications` (group members: `roles/storage.objectCreator` and `objectViewer`, no overwrite or delete) |
| Ingestion function | `rag-own-publications-ingestor`, Python 3.12, one instance, Eventarc retries on |
| Service account | `rag-ingestor-sa-corpus-agent` (function and agent) |
| Corpus | `GEG-Own-Publications`, resource name in secret `rag-own-publications-corpus-id` |
| Agent | `GEG-Publication-Corpus-Agent` on Agent Engine, staging bucket `geg-publications-rag-agent-staging-bucket` |
| Terraform state | `gs://geg-core-dev-tfstate/literature-rag/state` |

The values live in `terraform/geg-core-dev.tfvars` (Terraform) and `.env.example` (scripts).

### Deploy a change

```bash
just setup                  # once: uv sync, git hooks
cp .env.example .env        # once: the scripts read it
just tf-init                # once per clone: GCS state backend, providers

just tf-plan                # after a change to src/ingestor/ or terraform/
just tf-apply               # read the plan, then confirm
just agent-deploy           # after a change to src/agent/: updates the agent in place
```

`just tf-apply` zips `src/ingestor/` and rebuilds the function. `just agent-deploy` pins the
local `google-adk` version into the container and writes the agent's resource name back to `.env`.

Never run these against `geg-core-dev`: `tofu destroy` (the buckets have `force_destroy`),
`scripts/init_rag_corpus.py` (creates a second corpus and a new secret version), or an agent
delete. The old pipeline next to this one (`geg-publications-*` buckets and corpora) is tracked in
geg-ops #365 and not touched from here.

### If something breaks

- Function: `gcloud functions logs read rag-own-publications-ingestor --project geg-core-dev --region europe-west1`.
  A busy corpus is retried for eight minutes by `src/ingestor/retry.py`, then Eventarc redelivers
  the event for up to 24 hours.
- Missed events: `uv run scripts/import_bucket.py` imports every PDF of the bucket in one operation;
  files already in the corpus are skipped.
- Agent on the wrong corpus: `scripts/switch-agent-corpus.sh <engine id> <corpus resource name>`.

## Develop

```bash
just setup    # uv sync + git hooks
just check    # format, lint, mypy strict, tests with coverage ≥ 80 %
just tf-check # terraform fmt and validate, no state access
```

Branches and reviews follow [CONTRIBUTING.md](CONTRIBUTING.md). Say in the pull request whether a
change was deployed.

## Contribute a missing paper

81 GEG papers on geg.ethz.ch have no PDF in the RAG yet. Anyone in the group can help, no coding
needed beyond running the upload tool.

1. Pick a paper from [docs/missing-papers/PAPERS_TO_GET.md](docs/missing-papers/PAPERS_TO_GET.md).
   The list is grouped by what to try: ETH network or VPN, a title search, or asking the author.
2. Upload the PDF with `geg-rag-upload upload paper.pdf`, as described under [Add a paper](#add-a-paper).
3. Remove the paper's row from `docs/missing-papers/still_to_get.csv`, rebuild the list with
   `uv run python scripts/missing_list.py docs/missing-papers/still_to_get.csv docs/missing-papers/PAPERS_TO_GET.md`,
   and open a pull request.

If you cannot get a paper, record who tried, when and what happened in its CSV row instead. Details:
[docs/missing-papers/README.md](docs/missing-papers/README.md).

**Never commit a PDF.** This repository is public and the papers are under copyright. PDFs go into
the bucket only; `.gitignore` blocks them.
