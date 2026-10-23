"""Turn a DOI or a title into a bucket object name."""

import re

from slugify import slugify

MAX_SLUG_LENGTH = 120
PDF_SUFFIX = ".pdf"
UNSAFE_CHARACTERS = re.compile(r"[^a-z0-9._-]+")


def doi_to_object_name(doi: str) -> str:
    """Return a flat, shell-safe file name for ``doi``.

    ``/`` becomes ``_`` so the bucket stays flat; any other character outside ``[a-z0-9._-]`` also becomes
    ``_``. The original DOI is kept in object metadata, so the mapping does not need to be reversible.
    """
    flattened = UNSAFE_CHARACTERS.sub("_", doi.lower())
    collapsed = re.sub(r"_+", "_", flattened).strip("_")
    return f"{collapsed}{PDF_SUFFIX}"


def title_to_object_name(title: str) -> str:
    """Return a slug file name for a paper without a DOI."""
    slug = slugify(title, max_length=MAX_SLUG_LENGTH, word_boundary=True)
    return f"{slug}{PDF_SUFFIX}"
