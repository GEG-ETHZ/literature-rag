"""Command line: ``geg-rag-upload upload <pdf...>`` and ``geg-rag-upload migrate <folder|gs://bucket>``."""

import argparse
import getpass
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from tabulate import tabulate

from uploader.bucket import ObjectStore, download_pdfs, gcs_store, local_md5
from uploader.crossref import Record, doi_resolves, fetch_record, new_client, search_doi_by_title
from uploader.doi import clean_doi, find_doi
from uploader.pdfmeta import read_pdf, title_from
from uploader.plan import Action, BucketState, Decision, Paper, decide

DEFAULT_PROJECT = "geg-core-dev"
DEFAULT_BUCKET = "geg-core-dev-rag-own-publications"
GCS_PREFIX = "gs://"
EXIT_OK = 0
EXIT_ATTENTION = 1


@dataclass(frozen=True)
class Options:
    """Parsed command line."""

    command: str
    sources: list[str]
    bucket: str
    project: str
    dry_run: bool
    force: bool
    offline: bool
    doi: str | None
    title: str | None


def parse_args(argv: Sequence[str]) -> Options:
    """Parse ``argv`` into ``Options``."""
    parser = argparse.ArgumentParser(prog="geg-rag-upload", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    upload = sub.add_parser("upload", help="upload one or more PDFs under their DOI name")
    upload.add_argument("sources", nargs="+", metavar="PDF")
    upload.add_argument("--doi", help="use this DOI instead of detecting one (single PDF only)")
    upload.add_argument("--title", help="use this title instead of detecting one (single PDF only)")
    migrate = sub.add_parser("migrate", help="process every PDF in a folder or in a gs://bucket")
    migrate.add_argument("sources", nargs=1, metavar="FOLDER_OR_GS_URL")
    for p in (upload, migrate):
        p.add_argument("--bucket", default=DEFAULT_BUCKET)
        p.add_argument("--project", default=DEFAULT_PROJECT)
        p.add_argument("--dry-run", action="store_true", help="report only; upload nothing")
        p.add_argument("--force", action="store_true", help="overwrite an object that has the same name")
        p.add_argument("--offline", action="store_true", help="skip doi.org and Crossref lookups")
    ns = parser.parse_args(argv)
    overrides = (getattr(ns, "doi", None), getattr(ns, "title", None))
    if any(overrides) and len(ns.sources) != 1:
        parser.error("--doi and --title apply to exactly one PDF")
    return Options(
        ns.command, list(ns.sources), ns.bucket, ns.project, ns.dry_run, ns.force, ns.offline, *overrides
    )


def collect_pdfs(options: Options, workdir: Path) -> list[Path]:
    """Resolve the command's sources to local PDF paths, downloading from GCS when asked."""
    if options.command == "upload":
        return [Path(s) for s in options.sources]
    source = options.sources[0]
    if source.startswith(GCS_PREFIX):
        import google.cloud.storage as storage

        return download_pdfs(storage.Client(project=options.project), source[len(GCS_PREFIX) :], workdir)
    return sorted(p for p in Path(source).iterdir() if p.suffix.lower() == ".pdf")


def describe(path: Path, options: Options, client: httpx.Client | None) -> tuple[Paper, Record | None]:
    """Read ``path`` and return what is known about it, consulting doi.org and Crossref unless offline."""
    info = read_pdf(path)
    doi = clean_doi(options.doi) if options.doi else find_doi(info.metadata, info.text)
    if doi and client is not None and not doi_resolves(doi, client):
        print(
            f"warning: {path.name}: {doi} does not resolve at doi.org, falling back to title", file=sys.stderr
        )
        doi = None
    if doi is None and client is not None and not options.title:
        doi = doi_from_title(path, title_from(info), info.text, client)
    record = fetch_record(doi, client) if doi and client is not None else None
    title = options.title or (record.title if record and record.title else None) or title_from(info)
    if doi is None and not options.title and title and title == info.largest_font_line:
        print(
            f"note: {path.name}: no DOI; title read from the page layout: {title!r}, verify", file=sys.stderr
        )
    return Paper(source=path.name, md5=local_md5(path), doi=doi, title=title), record


def doi_from_title(path: Path, title: str | None, text: str, client: httpx.Client) -> str | None:
    """Second chance for a PDF without a DOI: ask Crossref for a work with this exact title and author."""
    doi = search_doi_by_title(title, text, client) if title else None
    if doi:
        print(
            f"note: {path.name}: no DOI in the PDF; {doi} found via Crossref title match, verify",
            file=sys.stderr,
        )
    return doi


def metadata_for(paper: Paper, record: Record | None) -> dict[str, str]:
    """Return the custom metadata written next to the object."""
    fields = {
        "doi": paper.doi,
        "title": paper.title,
        "year": str(record.year) if record and record.year else None,
        "first_author": record.first_author if record else None,
        "original_filename": paper.source,
        "uploaded_by": getpass.getuser(),
        "uploaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return {k: v for k, v in fields.items() if v}


def process(pdfs: list[Path], options: Options, store: ObjectStore) -> list[Decision]:
    """Decide and, unless dry-run, upload each PDF; later files see earlier uploads of the same run."""
    state: BucketState = store.state()
    client = None if options.offline else new_client()
    decisions: list[Decision] = []
    for path in pdfs:
        paper, record = describe(path, options, client)
        decision = decide(paper, state, force=options.force)
        if decision.action is Action.UPLOAD and decision.target_name:
            decision = upload_one(path, decision, record, options, store)
            if decision.action is Action.UPLOAD:
                state = state.with_object(decision.target_name or "", paper.md5)
        decisions.append(decision)
    return decisions


def upload_one(
    path: Path, decision: Decision, record: Record | None, options: Options, store: ObjectStore
) -> Decision:
    """Upload one file; a network failure is reported for that file and does not stop the run."""
    if options.dry_run or decision.target_name is None:
        return decision
    try:
        store.upload(path, decision.target_name, metadata_for(decision.paper, record))
    except Exception as error:  # noqa: BLE001  any transport error: report, keep going, rerun retries
        print(f"error: {path.name}: upload failed: {error}", file=sys.stderr)
        return Decision(decision.paper, Action.FAILED, decision.target_name, type(error).__name__)
    print(f"uploaded {path.name} -> {decision.target_name}", file=sys.stderr, flush=True)
    return decision


def render(decisions: list[Decision], dry_run: bool) -> str:
    """Return a table of what happened, or would happen."""
    rows = [
        (d.paper.source, d.paper.doi or "-", d.target_name or "-", d.action.value, d.reason)
        for d in decisions
    ]
    headline = "DRY RUN: nothing uploaded" if dry_run else "done"
    counts = {a.value: sum(1 for d in decisions if d.action is a) for a in Action}
    summary = ", ".join(f"{k}: {v}" for k, v in counts.items() if v)
    table = tabulate(rows, headers=["source", "doi", "target name", "action", "reason"])
    return f"{table}\n\n{headline}; {summary}"


def run(argv: Sequence[str], store: ObjectStore | None = None) -> int:
    """Entry point; ``store`` is injected by tests."""
    options = parse_args(argv)
    store = store or gcs_store(options.project, options.bucket)
    with tempfile.TemporaryDirectory() as tmp:
        pdfs = collect_pdfs(options, Path(tmp))
        decisions = process(pdfs, options, store)
    print(render(decisions, options.dry_run))
    attention = {Action.NEEDS_OVERRIDE, Action.FAILED}
    return EXIT_ATTENTION if any(d.action in attention for d in decisions) else EXIT_OK


def main() -> None:
    """Console script entry point."""
    sys.exit(run(sys.argv[1:]))
