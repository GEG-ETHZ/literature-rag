set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set dotenv-load

# One-time setup after cloning: install deps, approve .envrc (macOS/Linux), and install git hooks
setup: _setup-direnv
    uv sync
    uv run prek install --hook-type pre-commit --hook-type pre-push --hook-type post-checkout --overwrite

[unix]
_setup-direnv:
    #!/usr/bin/env sh
    if ! command -v direnv >/dev/null 2>&1; then
        echo ""
        echo "Note: direnv not found (optional — install it for automatic environment activation on cd)."
        echo "  macOS:  brew install direnv"
        echo "  Linux:  sudo apt install direnv"
        echo "  Then add the shell hook: https://direnv.net/docs/hook.html"
        echo ""
    else
        grep -q 'direnv hook' ~/.zshrc 2>/dev/null || grep -q 'direnv hook' ~/.bashrc 2>/dev/null || {
            echo ""
            echo "Note: direnv is installed but not hooked into your shell."
            echo "Add one of the following (as appropriate) to your shell rc file and restart your shell:"
            echo "  ~/.zshrc:   eval \"\$(direnv hook zsh)\""
            echo "  ~/.bashrc:  eval \"\$(direnv hook bash)\""
            echo "  See: https://direnv.net/docs/hook.html"
            echo ""
        }
        direnv allow . || {
            echo ""
            echo "Warning: 'direnv allow .' failed — run it manually after checking your .envrc."
            echo ""
        }
    fi

[windows]
_setup-direnv:
    @echo "Note: direnv is not available on Windows — skipping."

# Format Python code with ruff
fmt:
    uv run ruff format .

# Lint Python code with ruff
lint:
    uv run ruff check .

# Type-check with mypy
typecheck:
    uv run mypy

# Run test suite
test:
    uv run pytest -v

# Run all quality checks in CI order: format → lint → typecheck → test
check: fmt lint typecheck test

# --- Terraform (OpenTofu): the GCP resources of the geg-core-dev deployment ---

tf_dir := "terraform"
tf_vars := "-var-file=geg-core-dev.tfvars"

# Connect to the GCS state backend and download providers
tf-init:
    cd {{tf_dir}} && tofu init

# Format and validate the Terraform files without touching state
tf-check:
    cd {{tf_dir}} && tofu fmt -check && tofu init -backend=false && tofu validate -no-color

# Show what an apply would change
tf-plan:
    cd {{tf_dir}} && tofu plan {{tf_vars}}

# Apply after reading the plan; asks for confirmation
tf-apply:
    cd {{tf_dir}} && tofu apply {{tf_vars}}

# --- Corpus and agent ---

# Query the RAG corpus directly, without the agent: just query "question"
query Q:
    uv run python scripts/query_rag.py "{{Q}}"

# List the files the corpus holds
list-files:
    uv run python scripts/list_rag_files.py

# Re-run the ingestion handler locally for one object already in the bucket
ingest-test NAME:
    echo "{{NAME}}" | uv run geg-rag-ingest run ingest_test

# Run the agent locally in the ADK web UI on http://localhost:8000
agent-run:
    uv run adk web src/

# Deploy the agent to Agent Engine (creates or updates by AGENT_DISPLAY_NAME)
agent-deploy:
    uv run python scripts/deploy_agent.py

# Ask the deployed agent: just agent-query "question"
agent-query Q:
    uv run python scripts/query_agent.py "{{Q}}"
