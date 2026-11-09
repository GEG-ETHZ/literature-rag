# The GEG deployment in geg-core-dev. Nothing here is secret; the corpus resource
# name sits in Secret Manager under secret_id and is never written to the repo.
project_id = "geg-core-dev"
region     = "europe-west1"

bucket_name = "geg-core-dev-rag-own-publications"
bucket_user_members = [
  "user:jpatterson@ethz.ch",
]

secret_id           = "rag-own-publications-corpus-id"
corpus_display_name = "GEG-Own-Publications"
corpus_description  = "GEG publications, one PDF per DOI, uploaded with geg-rag-upload"

service_account_id = "rag-ingestor-sa-corpus-agent"
function_name      = "rag-own-publications-ingestor"
# Gemini 3.x is not served in europe-west1; the eu endpoint keeps PDF parsing in the EU.
# RAG Engine accepts the path only with the project number, not the project ID.
gemini_model_name = "projects/436056981716/locations/eu/publishers/google/models/gemini-3.8-flash"

agent_engine_region              = "europe-west1"
agent_engine_staging_bucket_name = "geg-publications-rag-agent-staging-bucket"
