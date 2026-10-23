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
