"""Pure decision logic: what to do with one paper given the bucket's current contents."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from uploader.naming import doi_to_object_name, title_to_object_name


@dataclass(frozen=True)
class Paper:
    """What the tool knows about one local PDF before deciding."""

    source: str
    md5: str
    doi: str | None
    title: str | None


@dataclass(frozen=True)
class BucketState:
    """Names and content hashes of the PDFs already in the bucket."""

    names: frozenset[str]
    md5_to_name: Mapping[str, str]

    def with_object(self, name: str, md5: str) -> "BucketState":
        """Return a new state that also contains ``name``; the receiver is unchanged."""
        return BucketState(names=self.names | {name}, md5_to_name={**self.md5_to_name, md5: name})


class Action(Enum):
    """The outcome for one paper."""

    UPLOAD = "upload"
    SKIP_SAME_BYTES = "skip: same file already in bucket"
    SKIP_NAME_EXISTS = "skip: name already in bucket"
    NEEDS_OVERRIDE = "needs --doi or --title"
    FAILED = "upload failed, rerun to retry"


@dataclass(frozen=True)
class Decision:
    """A paper, the action to take and the name it would get."""

    paper: Paper
    action: Action
    target_name: str | None
    reason: str


def target_name_for(paper: Paper) -> str | None:
    """Return the canonical object name, or ``None`` when neither DOI nor title is known."""
    if paper.doi:
        return doi_to_object_name(paper.doi)
    if paper.title:
        return title_to_object_name(paper.title)
    return None


def decide(paper: Paper, state: BucketState, force: bool = False) -> Decision:
    """Decide what to do with ``paper`` given ``state``.

    Byte-identical files are skipped even with ``force``: there is nothing to gain from a second copy.
    """
    existing = state.md5_to_name.get(paper.md5)
    if existing is not None:
        return Decision(paper, Action.SKIP_SAME_BYTES, existing, f"identical bytes stored as {existing}")
    name = target_name_for(paper)
    if name is None:
        return Decision(paper, Action.NEEDS_OVERRIDE, None, "no DOI found and no usable title")
    if name in state.names and not force:
        return Decision(paper, Action.SKIP_NAME_EXISTS, name, f"{name} exists with different bytes")
    return Decision(paper, Action.UPLOAD, name, "overwrite" if name in state.names else "new")
