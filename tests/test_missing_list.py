import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from missing_list import group_of, main, render, usable_link  # noqa: E402

FIELDS = ["year", "type", "title", "doi_or_link", "reason", "platform_url", "tried_by", "tried_on", "outcome"]
PAYWALLED = "ETH Research Collection entry is metadata only; paywalled at publisher"
NO_DOI = "no DOI or link on the platform; ask the author or search by title"
THESIS = "thesis not found open access; ask the author or the library"


def row(
    year: str, title: str, link: str = "", reason: str = PAYWALLED, kind: str = "journal"
) -> dict[str, str]:
    return {
        "year": year,
        "type": kind,
        "title": title,
        "doi_or_link": link,
        "reason": reason,
        "platform_url": f"https://geg.ethz.ch/publications/{year}",
        "tried_by": "",
        "tried_on": "",
        "outcome": "",
    }


def test_group_follows_the_reason() -> None:
    assert group_of(PAYWALLED) == "paywalled"
    assert group_of(NO_DOI) == "nodoi"
    assert group_of(THESIS) == "thesis"
    assert group_of("anything else") == "paywalled"


def test_placeholder_links_are_not_usable() -> None:
    assert usable_link("https://doi.org/10.1306/12181818038") == "https://doi.org/10.1306/12181818038"
    assert usable_link("") == ""
    assert usable_link("https://doi.org/(none)") == ""
    assert usable_link("https://www.ethz.ch/") == ""
    assert usable_link("https://pangea.stanford.edu/ERE/db/GeoConf/.../Gar.pdf") == ""


def test_render_groups_sorts_newest_first_and_counts() -> None:
    rows = [
        row("2017", "Old paper", "https://doi.org/10.1/old"),
        row("2024", "New paper", "https://doi.org/10.1/new"),
        row("2020", "No link paper", reason=NO_DOI),
    ]

    text = render(rows, "2026-10-23")

    assert "3 GEG-own papers" in text
    assert "## Paywalled: open the link on the ETH network or VPN (2)" in text
    assert "## No DOI or link: search by title (1)" in text
    assert "Theses" not in text
    assert text.index("New paper") < text.index("Old paper")
    assert "Updated 2026-10-23" in text


def test_render_falls_back_to_scholar_and_escapes_brackets() -> None:
    rows = [row("2020", "A [bracketed] title", "https://www.ethz.ch/")]

    text = render(rows, "2026-10-23")

    assert "[A (bracketed) title](https://scholar.google.com/scholar?q=" in text
    assert "www.ethz.ch" not in text


def test_main_writes_the_checklist(tmp_path: Path) -> None:
    src = tmp_path / "still_to_get.csv"
    with src.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(row("2019", "Thesis title", reason=THESIS, kind="thesis-msc"))
    out = tmp_path / "PAPERS_TO_GET.md"

    assert main([str(src), str(out), "--date", "2026-10-23"]) == 0

    assert "## Theses: ask the author or the ETH Library (1)" in out.read_text()


def test_grouping_ignores_case() -> None:
    assert group_of("Thesis not found; ask the author") == "thesis"
    assert group_of("No DOI on the platform") == "nodoi"


def test_bare_doi_becomes_a_doi_link_and_schemeless_text_is_dropped() -> None:
    assert usable_link("10.1306/12181818038") == "https://doi.org/10.1306/12181818038"
    assert usable_link("www.example.org/paper") == ""


def test_parentheses_in_a_doi_do_not_break_the_link() -> None:
    text = render([row("1999", "Paren paper", "https://doi.org/10.1016/S0016-7037(99)00123-4")], "2026-10-23")

    assert "(<https://doi.org/10.1016/S0016-7037(99)00123-4>)" in text


def test_odd_years_render_and_sort_last() -> None:
    rows = [row("", "No year"), row("n.d.", "Undated"), row("2020", "Dated")]

    text = render(rows, "2026-10-23")

    assert "- [ ] n.d. · [No year]" in text
    assert text.index("Dated") < text.index("No year")
    assert text.endswith("\n")


def write_csv(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.write_text(",".join(FIELDS) + "\n" + text, encoding=encoding)


def test_main_reads_a_csv_saved_with_a_bom(tmp_path: Path) -> None:
    src, out = tmp_path / "in.csv", tmp_path / "out.md"
    write_csv(src, "2020,journal,BOM paper,,no DOI,https://geg.ethz.ch/p,,,\n", encoding="utf-8-sig")

    assert main([str(src), str(out), "--date", "2026-10-23"]) == 0
    assert "- [ ] 2020 · [BOM paper]" in out.read_text()


def test_main_rejects_a_row_without_title_or_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src, out = tmp_path / "in.csv", tmp_path / "out.md"
    write_csv(src, "2024,journal,Short row\n")

    assert main([str(src), str(out)]) == 1
    assert "row 2" in capsys.readouterr().err
    assert not out.exists()
