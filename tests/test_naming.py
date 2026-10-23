from uploader.naming import doi_to_object_name, title_to_object_name


def test_doi_to_object_name_replaces_slash() -> None:
    assert doi_to_object_name("10.1016/j.cesys.2022.100086") == "10.1016_j.cesys.2022.100086.pdf"


def test_doi_to_object_name_sanitises_shell_unfriendly_characters() -> None:
    assert doi_to_object_name("10.1002/(SICI)1097-0363(19990615)30:3<287::AID-FLD>3.0.CO;2-M") == (
        "10.1002_sici_1097-0363_19990615_30_3_287_aid-fld_3.0.co_2-m.pdf"
    )


def test_title_to_object_name_slugifies_unicode() -> None:
    assert title_to_object_name("Natürliche Konvektion in porösen Medien: Übersicht") == (
        "naturliche-konvektion-in-porosen-medien-ubersicht.pdf"
    )


def test_title_to_object_name_truncates_long_titles_at_word_boundary() -> None:
    title = " ".join(["word"] * 60)
    name = title_to_object_name(title)
    assert name.endswith(".pdf")
    assert len(name) <= 120 + len(".pdf")
    assert not name.endswith("-.pdf")
