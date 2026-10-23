import pytest

from ingestor.retry import call_when_free

BUSY = RuntimeError("There are other operations running on the RagCorpus x. Operation IDs are: [1].")


def test_retries_while_corpus_is_busy_then_succeeds() -> None:
    outcomes: list[object] = [BUSY, BUSY, "done"]
    sleeps: list[float] = []

    def action() -> str:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    assert call_when_free(action, sleep=sleeps.append, wait_seconds=5) == "done"
    assert sleeps == [5, 5]


def test_gives_up_after_max_wait() -> None:
    def action() -> str:
        raise BUSY

    with pytest.raises(RuntimeError):
        call_when_free(action, sleep=lambda _s: None, wait_seconds=10, max_wait_seconds=30)


def test_other_errors_are_not_retried() -> None:
    calls: list[int] = []

    def action() -> str:
        calls.append(1)
        raise ValueError("bad pdf")

    with pytest.raises(ValueError):
        call_when_free(action, sleep=lambda _s: None)
    assert calls == [1]
