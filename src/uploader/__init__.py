"""Upload GEG publications to the RAG bucket under DOI-based names, skipping duplicates."""

from importlib.metadata import version

import uploader

__version__ = version("literature-rag")
