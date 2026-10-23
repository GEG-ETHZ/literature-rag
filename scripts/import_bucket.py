# /// script
# requires-python = ">=3.11"
# dependencies = ["google-cloud-aiplatform>=1.38.0"]
# ///
"""Import every PDF of a bucket into a RAG corpus in one operation, with the same settings as the function.

Use for a first fill or to catch up after missed events. Files already in the corpus are skipped by
RAG Engine. Blocks until the import finishes and prints the counts.
"""

import argparse

import vertexai
from vertexai.preview import rag


def main() -> None:
    """Parse arguments and run one bulk import."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", help="corpus resource name, projects/.../ragCorpora/...")
    parser.add_argument("--bucket", default="geg-core-dev-rag-own-publications")
    parser.add_argument("--project", default="geg-core-dev")
    parser.add_argument("--location", default="europe-west1")
    parser.add_argument("--model", default="gemini-2.5-flash")
    args = parser.parse_args()
    vertexai.init(project=args.project, location=args.location)
    response = rag.import_files(
        corpus_name=args.corpus,
        paths=[f"gs://{args.bucket}/"],
        transformation_config=rag.TransformationConfig(
            chunking_config=rag.ChunkingConfig(chunk_size=512, chunk_overlap=50)
        ),
        llm_parser=rag.LlmParserConfig(model_name=args.model),
        timeout=7200,
    )
    print(
        f"imported: {response.imported_rag_files_count}, failed: {response.failed_rag_files_count}, "
        f"skipped: {response.skipped_rag_files_count}"
    )


if __name__ == "__main__":
    main()
