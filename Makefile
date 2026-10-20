SHELL := /usr/bin/env bash

.DEFAULT_GOAL := help

.PHONY: up down status submit help

up:        ## Start everything (GPU tunnel + both Docker stacks). Prompts for the HPC password.
	bash start.sh

down:      ## Stop both Docker stacks and close the GPU tunnel.
	bash stop.sh

status:    ## Show VPN / Slurm GPU job / tunnel / Docker / health.
	bash ai-engine/hpc/hpc-dev.sh status

submit:    ## Reserve a GPU on the cluster (submit the Slurm job). Run once per session.
	bash ai-engine/hpc/hpc-dev.sh submit

help:      ## List available targets.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-10s %s\n", $$1, $$2}'
