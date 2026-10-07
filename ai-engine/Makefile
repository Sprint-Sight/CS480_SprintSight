# SprintSight AI Engine — Development Shortcuts
# Run from ai-engine/ directory.

.PHONY: help hpc hpc-status hpc-models hpc-tunnel hpc-submit hpc-stop \
        local local-stop health logs

help: ## Show this help
	@grep -E '^[a-z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

# ── HPC workflow ─────────────────────────────────────────────────────────────

hpc: ## Full HPC startup (tunnel must be open in another terminal)
	bash hpc/hpc-dev.sh full

hpc-status: ## Check cluster job, tunnel, models, Docker, healthcheck
	bash hpc/hpc-dev.sh status

hpc-models: ## Create/verify sprintsight-* models on remote Ollama
	bash hpc/hpc-dev.sh models

hpc-tunnel: ## Open SSH tunnel (blocking — run in its own terminal)
	bash hpc/hpc-dev.sh tunnel

hpc-submit: ## Submit the Slurm GPU job on the cluster
	bash hpc/hpc-dev.sh submit

hpc-stop: ## Stop Docker services, show tunnel teardown
	bash hpc/hpc-dev.sh stop

# ── Local workflow (Ollama in Docker, no GPU) ────────────────────────────────

local: ## Start full local stack (Ollama + models + db + mlflow + app)
	docker compose up -d

local-stop: ## Stop everything
	docker compose down

# ── Utilities ────────────────────────────────────────────────────────────────

health: ## Hit the /health endpoint
	@curl -sf http://localhost:8001/health | python3 -m json.tool 2>/dev/null || echo "Not responding"

logs: ## Tail sprintsight_ai logs
	docker compose logs -f sprintsight_ai
