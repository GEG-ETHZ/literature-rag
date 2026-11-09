# Changelog

All notable changes to `literature-rag` are documented here.
`literature-rag` does not yet follow [Semantic Versioning](https://semver.org/) — everything is
pre-release. Once the first public release (`1.0.0`) is cut, the project will
adopt SemVer strictly.

## [In Development]

### Added

- Forked from [danielvogler/Gemini-Rag-Automator](https://github.com/danielvogler/Gemini-Rag-Automator)
  at `40adcec` as the single GEG repository for the literature RAG.
- `geg-rag-upload`, the migration record and the missing-papers list, moved from
  `GEG-ETHZ/rag-own-publications`, which is archived.
- `src/ingestor/retry.py`: the ingestion function waits while the corpus is busy with
  another import instead of failing the event.
- Terraform state in `gs://geg-core-dev-tfstate` under `literature-rag/state`; the
  group-wide bucket binding; the non-secret deployment values in
  `terraform/geg-core-dev.tfvars`.

### Changed

- The corpus-ID secret is replicated only in the corpus region instead of automatically, so
  every stored piece of the deployment stays in the EU. Changing replication replaces the
  secret and drops its versions: after `tofu apply`, add the corpus resource name again with
  `gcloud secrets versions add`.
- Ingestion and the agent use `gemini-3.8-flash` on the `eu` multi-region endpoint instead of
  `gemini-2.5-flash`, which Google lists as retired on 20 Oct 2026. No Gemini 3.x model is
  served in `europe-west1`; the corpora stay there. The ingestion function now fails without
  `GEMINI_MODEL_NAME` instead of falling back to a short model name, and Terraform requires the
  full model path with the project number, the only form RAG Engine accepted for `eu`.
- Group members hold `roles/storage.objectCreator` and `roles/storage.objectViewer` on the
  papers bucket instead of `roles/storage.objectUser`, so the no-duplicates rule of
  `geg-rag-upload` is enforced by IAM: nobody but a project admin can overwrite or delete a
  DOI-named object. Raised in geg-core-infra !10 review.
- README: the bucket takes published versions only.
- The function source zip leaves out `__pycache__`, so a local test run no longer changes
  its hash and redeploys the function. The deployed zip carried three stale `.pyc` files.
- Citations name the paper from the object's Crossref metadata (`first_author`, `year`,
  `title`, `doi`) that `geg-rag-upload` writes, instead of Gemini reading page one into
  Firestore. Firestore is gone from the code and the Terraform.
- GEG python-template conventions: `just` instead of `make`, ruff at 110 columns with the
  strict rule set, strict mypy, `prek` hooks, `.agent/` rules.
- Ingestion function on `python312` with Eventarc retries on, as deployed.

### Fixed

### Removed

- Firestore database, `roles/datastore.user`, `pypdf`.

<!-- Version comparison links — verify and update when cutting a release.
     Label is [Unreleased] (not [In Development]) so changelog tooling recognises it. -->
[Unreleased]: https://github.com/GEG-ETHZ/literature-rag/commits/main
