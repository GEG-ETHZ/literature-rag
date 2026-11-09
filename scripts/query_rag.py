"""Script to query the Gemini RAG Pipeline.

LEGACY — kept for reference and debugging only.

This uses ``Tool.from_retrieval(rag.Retrieval(...))`` (server-side grounding),
which on Gemini 2.5/3 blends parametric knowledge with retrieved chunks. For
corpus-only answers with citations, use the ADK agent at ``src/agent/`` and
the helpers ``scripts/deploy_agent.py`` + ``scripts/query_agent.py``
(``make agent-deploy`` / ``make agent-query Q="..."``).
"""

import argparse
import logging
import os

from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    """Execute the query against the RAG engine."""
    parser = argparse.ArgumentParser(description="Query the Gemini RAG Automator Pipeline")
    parser.add_argument("query", type=str, help="The question to ask the RAG engine")
    args = parser.parse_args()

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    corpus_id = os.environ.get("GCP_SECRET_ID")  # Fallback, ideally fetched from secret manager
    # Reads the agent's AGENT_MODEL_NAME and AGENT_MODEL_LOCATION, not GEMINI_MODEL_NAME (the
    # ingestion parser): Gemini 3.x is not served in the corpus region.
    model_name = os.environ.get("AGENT_MODEL_NAME", "gemini-3.8-flash")
    model_location = os.environ.get("AGENT_MODEL_LOCATION", "eu")

    if not all([project_id, corpus_id]):
        logger.error("Missing required environment variables (GOOGLE_CLOUD_PROJECT, GCP_SECRET_ID).")
        return

    # Note: In a real scenario, you'd fetch the actual Corpus ID (projects/.../locations/.../ragCorpora/...)
    # from Secret Manager. For testing if you have the direct ID, you could pass it directly.
    # Kept simple: the corpus id is read the same way the Cloud Function reads it.

    from google.cloud import secretmanager

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{corpus_id}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
        true_corpus_id = response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logger.error(f"Error fetching Corpus ID from Secret Manager: {e}")
        return

    logger.info(f"\n[+] Using RAG Corpus: {true_corpus_id}")
    logger.info(f"[+] Querying {model_name} with question: '{args.query}'\n")

    # The RAG tool points at the corpus in its own region; the model runs on model_location.
    rag_retrieval_tool = types.Tool(
        retrieval=types.Retrieval(
            vertex_rag_store=types.VertexRagStore(
                rag_resources=[types.VertexRagStoreRagResource(rag_corpus=true_corpus_id)],
                similarity_top_k=5,
            )
        )
    )
    genai_client = genai.Client(vertexai=True, project=project_id, location=model_location)
    generation_response = genai_client.models.generate_content(
        model=model_name,
        contents=args.query,
        config=types.GenerateContentConfig(tools=[rag_retrieval_tool]),
    )

    logger.info("ANSWER:")
    logger.info(generation_response.text)

    # Surface the retrieved corpus chunks that grounded the answer, alongside
    # their source document, so the citation can show *which text segment*
    # backed the response (not just which PDF it came from).
    candidates = generation_response.candidates
    if candidates:
        grounding_metadata = candidates[0].grounding_metadata
        grounding_chunks = grounding_metadata.grounding_chunks if grounding_metadata else []
        if grounding_chunks:
            logger.info("\nSOURCE CHUNKS:")
            for i, chunk in enumerate(grounding_chunks, start=1):
                retrieved_context = chunk.retrieved_context
                if retrieved_context is None:
                    continue
                title = retrieved_context.title or retrieved_context.uri
                logger.info(f"\n[{i}] {title}")
                logger.info(retrieved_context.text)


if __name__ == "__main__":
    main()
