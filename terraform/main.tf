locals {
  services = toset([
    "secretmanager.googleapis.com",
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "eventarc.googleapis.com",
    "cloudbuild.googleapis.com",
    "storage.googleapis.com",
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "pubsub.googleapis.com"
  ])
}

resource "google_project_service" "enabled_apis" {
  for_each = local.services
  project  = var.project_id
  service  = each.key

  disable_dependent_services = false
  disable_on_destroy         = false
}

resource "time_sleep" "wait_for_apis" {
  depends_on      = [google_project_service.enabled_apis]
  create_duration = "60s"
}

# force_destroy off: a destroy must never take the papers with it.
resource "google_storage_bucket" "rag_document_source" {
  name                        = lower(var.bucket_name)
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  depends_on                  = [time_sleep.wait_for_apis]
}

resource "google_storage_bucket" "function_source" {
  name                        = "${var.project_id}-${var.function_name}-source"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
}

resource "google_storage_bucket" "agent_engine_staging" {
  name                        = lower(var.agent_engine_staging_bucket_name)
  location                    = var.agent_engine_region
  uniform_bucket_level_access = true
  force_destroy               = false
  depends_on                  = [time_sleep.wait_for_apis]
}

data "archive_file" "function_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/ingestor"
  output_path = "${path.module}/../src/ingestor.zip"
}

resource "google_storage_bucket_object" "function_zip" {
  name   = "ingestor-${data.archive_file.function_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_zip.output_path
}

resource "google_service_account" "rag_ingestor_sa" {
  account_id   = var.service_account_id
  display_name = "RAG Ingestor Service Account"
}

resource "google_project_iam_member" "eventarc_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.rag_ingestor_sa.email}"
}

resource "google_project_iam_member" "run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.rag_ingestor_sa.email}"
}

resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.rag_ingestor_sa.email}"
}

resource "google_project_iam_member" "aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.rag_ingestor_sa.email}"
}

# The agent runs as the same service account and reads each cited object's
# custom metadata (doi, title, year, first_author, written by geg-rag-upload)
# to render the citation. Without this grant the lookup 403s and citations
# silently fall back to the bare filename.
resource "google_storage_bucket_iam_member" "ingestor_source_reader" {
  bucket = google_storage_bucket.rag_document_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.rag_ingestor_sa.email}"
}

# Group members read and write papers through geg-rag-upload. Authoritative
# for this one role on this bucket; the member list lives in geg-core-dev.tfvars.
resource "google_storage_bucket_iam_binding" "bucket_users" {
  bucket  = google_storage_bucket.rag_document_source.name
  role    = "roles/storage.objectUser"
  members = var.bucket_user_members
}

resource "google_secret_manager_secret" "rag_corpus_id" {
  secret_id = var.secret_id
  replication {
    auto {}
  }
  depends_on = [time_sleep.wait_for_apis]
}

# No depends_on: deferring this read to apply time makes the member unknown at
# plan time and forces a replace of gcs_pubsub_publishing, which drops every
# Cloud Storage trigger in the project for the seconds in between.
data "google_storage_project_service_account" "gcs_account" {
  project = var.project_id
}

resource "google_project_iam_member" "gcs_pubsub_publishing" {
  project    = var.project_id
  role       = "roles/pubsub.publisher"
  member     = "serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"
  depends_on = [time_sleep.wait_for_apis]
}

resource "google_cloudfunctions2_function" "ingestor" {
  name        = var.function_name
  location    = var.region
  description = "Ingests PDFs from GCS into Vertex AI RAG Corpus"

  build_config {
    runtime     = "python312"
    entry_point = "process_file"
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_zip.name
      }
    }
  }

  service_config {
    max_instance_count    = 1
    min_instance_count    = 0
    available_memory      = "512Mi"
    timeout_seconds       = 540
    service_account_email = google_service_account.rag_ingestor_sa.email
    environment_variables = {
      GCP_SECRET_ID         = var.secret_id
      GOOGLE_CLOUD_PROJECT  = var.project_id
      GOOGLE_CLOUD_LOCATION = var.region
      GEMINI_MODEL_NAME     = var.gemini_model_name
      LOG_EXECUTION_ID      = "true"
    }
  }

  event_trigger {
    event_type            = "google.cloud.storage.object.v1.finalized"
    trigger_region        = var.region
    service_account_email = google_service_account.rag_ingestor_sa.email
    event_filters {
      attribute = "bucket"
      value     = google_storage_bucket.rag_document_source.name
    }
    # RAG Engine runs one import per corpus at a time; a refused import is
    # retried by src/ingestor/retry.py for up to eight minutes, and Eventarc
    # redelivers the event for up to 24 h when the function still fails.
    retry_policy = "RETRY_POLICY_RETRY"
  }

  depends_on = [
    google_project_iam_member.eventarc_receiver,
    google_project_iam_member.run_invoker,
    google_project_iam_member.secret_accessor,
    google_project_iam_member.aiplatform_user,
    google_project_iam_member.gcs_pubsub_publishing,
    google_storage_bucket_iam_member.ingestor_source_reader,
    time_sleep.wait_for_apis
  ]
}

resource "null_resource" "init_rag_corpus" {
  triggers = {
    always_run = timestamp()
  }

  provisioner "local-exec" {
    command = "echo 'Intended logic: uv run python scripts/init_rag_corpus.py'"
  }

  depends_on = [
    google_secret_manager_secret.rag_corpus_id
  ]
}
