from uploader.plan import Action, BucketState, Paper, decide

EMPTY = BucketState(names=frozenset(), md5_to_name={})


def paper(doi: str | None = "10.1/abc", title: str | None = None, md5: str = "m1") -> Paper:
    return Paper(source="x.pdf", md5=md5, doi=doi, title=title)


def test_uploads_new_doi_paper_under_doi_name() -> None:
    decision = decide(paper(), EMPTY)
    assert decision.action is Action.UPLOAD
    assert decision.target_name == "10.1_abc.pdf"


def test_skips_when_same_bytes_already_in_bucket_under_any_name() -> None:
    state = BucketState(names=frozenset({"2020_old_name.pdf"}), md5_to_name={"m1": "2020_old_name.pdf"})
    decision = decide(paper(), state)
    assert decision.action is Action.SKIP_SAME_BYTES
    assert "2020_old_name.pdf" in decision.reason


def test_skips_when_target_name_exists_with_different_bytes() -> None:
    state = BucketState(names=frozenset({"10.1_abc.pdf"}), md5_to_name={"other": "10.1_abc.pdf"})
    assert decide(paper(), state).action is Action.SKIP_NAME_EXISTS


def test_force_overwrites_existing_name() -> None:
    state = BucketState(names=frozenset({"10.1_abc.pdf"}), md5_to_name={"other": "10.1_abc.pdf"})
    assert decide(paper(), state, force=True).action is Action.UPLOAD


def test_uses_title_when_no_doi() -> None:
    decision = decide(paper(doi=None, title="A Study of Things"), EMPTY)
    assert decision.action is Action.UPLOAD
    assert decision.target_name == "a-study-of-things.pdf"


def test_needs_override_when_neither_doi_nor_title() -> None:
    decision = decide(paper(doi=None, title=None), EMPTY)
    assert decision.action is Action.NEEDS_OVERRIDE
    assert decision.target_name is None


def test_state_with_object_is_immutable_update() -> None:
    updated = EMPTY.with_object("a.pdf", "m9")
    assert EMPTY.names == frozenset()
    assert updated.names == frozenset({"a.pdf"})
    assert updated.md5_to_name == {"m9": "a.pdf"}
