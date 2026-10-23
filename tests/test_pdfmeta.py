from pathlib import Path

import pymupdf

from uploader.pdfmeta import read_pdf, title_from


def make_pdf(path: Path, title_meta: str, big_line: str, body: str) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), big_line, fontsize=20)
    page.insert_text((72, 200), body, fontsize=10)
    doc.set_metadata({"title": title_meta, "subject": "subject text"})
    doc.save(str(path))


def test_read_pdf_returns_metadata_text_and_largest_font_line(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    make_pdf(pdf, "Meta Title", "Biggest Heading", "body with doi 10.1234/abcd")
    info = read_pdf(pdf)
    assert info.metadata["title"] == "Meta Title"
    assert "10.1234/abcd" in info.text
    assert info.largest_font_line == "Biggest Heading"


def test_title_from_prefers_good_metadata_title(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    make_pdf(pdf, "A Proper Metadata Title", "Heading", "body")
    assert title_from(read_pdf(pdf)) == "A Proper Metadata Title"


def test_title_from_falls_back_to_largest_font_line_for_junk_metadata(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    make_pdf(pdf, "Microsoft Word - draft.docx", "Real Heading", "body")
    assert title_from(read_pdf(pdf)) == "Real Heading"


def test_title_from_returns_none_when_nothing_usable(tmp_path: Path) -> None:
    pdf = tmp_path / "p.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(pdf))
    assert title_from(read_pdf(pdf)) is None


def test_title_ignores_slightly_larger_caption_at_page_bottom(tmp_path: Path) -> None:
    pdf = tmp_path / "supplement.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "GSA Data Repository 2016028", fontsize=12, fontname="helv")
    page.insert_text((72, 90), "Nanoscale constraints on porosity generation", fontsize=12, fontname="hebo")
    page.insert_text((72, 120), "Benjamin M. Tutolo, David F.R. Mildner", fontsize=12, fontname="helv")
    page.insert_text((72, 700), "for use in calculation of the neutron scattering", fontsize=12.02)
    doc.save(str(pdf))
    assert title_from(read_pdf(pdf)) == "Nanoscale constraints on porosity generation"


def test_title_joins_consecutive_lines_of_the_same_style(tmp_path: Path) -> None:
    pdf = tmp_path / "two-line-title.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "Evolution of permeability of natural", fontsize=16, fontname="hebo")
    page.insert_text(
        (72, 100), "fractures due to THMC processes in the subsurface", fontsize=16, fontname="hebo"
    )
    page.insert_text((72, 140), "Author One, Author Two", fontsize=11, fontname="helv")
    doc.save(str(pdf))
    assert title_from(read_pdf(pdf)) == (
        "Evolution of permeability of natural fractures due to THMC processes in the subsurface"
    )


def test_title_ignores_arxiv_stamp_in_the_margin(tmp_path: Path) -> None:
    pdf = tmp_path / "arxiv.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 80), "A Real Paper Title About Fractures", fontsize=14, fontname="hebo")
    page.insert_text((20, 300), "arXiv:1801.08321v1 [physics.geo-ph] 25 Jan 2018", fontsize=16, rotate=90)
    doc.save(str(pdf))
    assert title_from(read_pdf(pdf)) == "A Real Paper Title About Fractures"


def test_title_from_treats_coversheet_as_junk(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    make_pdf(pdf, "Coversheet", "Code development for modeling induced seismicity", "body")
    assert title_from(read_pdf(pdf)) == "Code development for modeling induced seismicity"
