# State lives next to geg-core-infra's, in the versioned bucket that INIT.md there
# describes (created by hand on 2026-04-17). A separate prefix keeps the two roots apart.
terraform {
  backend "gcs" {
    bucket = "geg-core-dev-tfstate"
    prefix = "literature-rag/state"
  }
}
