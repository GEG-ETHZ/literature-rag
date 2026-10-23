# AGENTS.md

You are working on the GEG literature RAG: the `geg-rag-upload` tool, the ingestion Cloud
Function, the corpus-only agent and the Terraform that owns their GCP resources. Read
`./.agent/rules.md` first; it holds the group's conventions for commits, paths and code quality.

## What is deployed

One deployment, in GCP project `geg-core-dev`, region `europe-west1`. The names are in
`README.md` under "Deployment in geg-core-dev", the values in `terraform/geg-core-dev.tfvars` and
`.env.example`. There is no test deployment; a change reaches production through
`just tf-apply` (function, Terraform) or `just agent-deploy` (agent).

## Before touching GCP

- Pass `--project geg-core-dev` on every `gcloud` command; never rely on the ambient default.
- Read-only commands are fine. Anything that writes (`tofu apply`, `tofu import`, `tofu state`,
  `gcloud ... deploy|create|update|delete`, `just agent-deploy`) needs a yes from a person in the
  conversation first.
- Never: `tofu destroy`, `scripts/init_rag_corpus.py`, deleting the agent, deleting objects in the
  papers bucket. The old pipeline (`geg-publications-*`) is handled in geg-ops #365, not here.
- Secrets stay in Secret Manager. `.env` is never committed; nothing in `.env.example` is secret.

## Checks

`just check` must pass before a pull request: ruff format and lint, strict mypy, tests with at
least 80 % coverage. `just tf-check` validates the Terraform without touching state.

## Where things are documented

- How the group uses the RAG: `README.md`. geg-ops `computing/ai/literature-rag.md` only links here.
- How the bucket was filled in October 2026: `docs/migration-2026-10.md`.
- Papers still missing: `docs/missing-papers/`.
- Why citations come from the object metadata and not Firestore: `CHANGELOG.md`, geg-ops #367.
