# SprintSight setup and onboarding guide

<!--
TEMPLATE STATUS: sections are pre-filled from the repo as of Nov 2026.
Anything marked TODO needs a teammate to confirm (UI labels, versions, quotas).
Keep this file the single source of truth; the README and any in-app help
should link here rather than copy it (see Appendix A).
-->

**Who this is for**

| Role | Read |
|---|---|
| **Operator / developer**: runs the stack, the GPU job and the AI engine | All sections |
| **Instructor**: runs assessments in the web app | §1, §5, §6, §8 |

**Time to first assessment:** about 1–2 hours the first time, most of it
model downloads. After that, about 5 minutes per work session.

---

## 1. How SprintSight fits together

```
Your laptop (Docker)                         Origami GPU cluster
┌───────────────────────────────┐            ┌─────────────────────────────┐
│ frontend :3000                │  VPN + SSH │ login node                  │
│ backend  :8000 ── repo/ (ro)  │  tunnel    │   └─ Slurm job (gpu:1)      │
│ sprintsight_ai :8001 ─────────┼──:11435───►│        GPU node: Ollama     │
│ MLflow :5000  Postgres  MinIO │            │        :11434 (RTX 3090)    │
└───────────────────────────────┘            └─────────────────────────────┘
```

- The GPU is **not** on your laptop. You reserve one per session by
  submitting a Slurm job, and `start.sh` tunnels to it.
- Student code is read from **local clones** in `repo/`, mounted read-only
  into the backend.

---

## 2. Prerequisites

### 2.1 Accounts and access

- [ ] SMU network access, or an **SMUResearch VPN** account (request it from
      the course instructor).
- [ ] **Origami cluster** login (`HPC_USER`; currently the group account
      `CS480G2`) and a check that `myinfo` shows partition `project`, QoS
      `cs480qos`.
- [ ] Read access to the SprintSight GitHub repository.
- [ ] Read access to every **student team repository** you will assess
      (GitHub/GitLab).
- [ ] Jira credentials for the team boards (configured in the app).
      <!-- TODO: link the Jira credential setup screen/docs -->
- [ ] SMTP provider credentials if email notifications are needed (see
      `backend/README.md`).

### 2.2 Your machine

| Requirement | Minimum | Notes |
|---|---|---|
| OS | Windows 10/11, macOS or Linux | On Windows, run the scripts from **Git Bash** or WSL, not cmd/PowerShell |
| Docker Desktop (Compose v2) | <!-- TODO version --> | Must be running before `start.sh` |
| RAM | 16 GB recommended | Runs Postgres, MinIO, MLflow and 3 app containers |
| Free disk | ~15 GB | Docker images and volumes; no model weights are stored locally in HPC mode |
| Git | any recent | Also used to clone student repos |
| SSH client, `curl` | bundled with Git Bash / macOS / Linux | |
| Python 3.12+ | only for research/eval scripts | The containers bring their own Python (3.13 AI engine, 3.12 backend) |
| Local GPU / CUDA | **Not required** | All inference runs on the cluster |

### 2.3 GPU, VRAM and CUDA

**On Origami (the default path):** the Slurm job provides the GPU and NVIDIA
driver. The `ollama/ollama` container bundles its own CUDA runtime, so **no
CUDA toolkit needs installing anywhere**.

| Model alias | Base | Approx. weights | GPU needed | Context we use |
|---|---|---|---|---|
| sprintsight-qwen | qwen3:8b | ~5 GB | ≥ 12 GB | up to 32K |
| sprintsight-llama31 | llama3.1:8b | ~5 GB | ≥ 12 GB | up to 32K |
| sprintsight-mistral | mistral:7b | ~4 GB | ≥ 12 GB | up to 32K |
| sprintsight-gemma | gemma4:12b | <!-- TODO --> | ≥ 16 GB | up to 32K |
| sprintsight-qwen25-32b / r1-32b / coder-32b | 32B Q4_K_M | ~20 GB each | **24 GB**, with `OLLAMA_KV_CACHE_TYPE=q4_0` | 16K |

- **Cluster disk quota:** the model cache in `~/sprintsight/ollama_data` is
  roughly **25 GB for the four small models and 80 GB+ with the three 32B
  models**. Check `quota -s` before the first job, and comment out models you
  don't need in `hpc/ollama-entrypoint.sh`.
- **Self-hosting on your own GPU (optional):** an NVIDIA GPU with compute
  capability ≥ 5.0, a recent NVIDIA driver (check Ollama's GPU docs for the
  current minimum), and the **NVIDIA Container Toolkit**. Then uncomment the
  `deploy.resources` GPU block in `ai-engine/docker-compose.yaml`. CPU-only
  Ollama is for wiring tests only.

How to confirm the GPU is really being used: §7.

---

## 3. One-time setup

### 3.1 On your laptop

```bash
git clone <sprintsight-repo-url> CS480_SprintSight
cd CS480_SprintSight
cp "ai-engine/.env example" ai-engine/.env
cp ai-engine/.env.hpc.example ai-engine/.env.hpc     # set HPC_USER / HPC_LOGIN_HOST if different
# backend/.env: create from the variable list in backend/README.md
# TODO: commit a backend/.env.example (backend/README.md links to one that is missing)
```

**Build the AI-engine image while off the VPN.** The VPN blocks Docker Hub
and PyPI, so a first build on the VPN fails:

```bash
cd ai-engine && REBUILD=yes bash hpc/hpc-dev.sh docker
```

### 3.2 On the cluster (once per account)

```bash
ssh <HPC_USER>@<HPC_LOGIN_HOST>
git clone <sprintsight-repo-url> ~/CS480_SprintSight
mkdir -p ~/slurm-logs
cd ~/CS480_SprintSight/ai-engine/hpc && bash setup_ollama_container.sh
myinfo        # confirm partition/qos match ollama_gpu.sbatch
```

The first GPU job downloads all the models. Expect it to take a while.

---

## 4. Prepare student repositories (before every assessment round)

The backend reads Git history and files directly from local clones. It does
**not** fetch from GitHub during an assessment.

1. Clone each team's repo **into `repo/`** at the project root, one folder per
   team:
   ```bash
   cd repo
   git clone <team-repo-url> <team-folder>      # full clone: do NOT use --depth
   ```
   A shallow clone silently truncates the commit history, and with it the
   collaboration and code-quality evidence.
2. Make sure the branch you want to grade is checked out, or present as HEAD.
   Pull before each sprint assessment:
   ```bash
   git -C repo/<team-folder> pull
   ```
3. **Check commit author emails.** Commits are linked to students **by email**.
   A student committing with a personal or unlisted email shows up as
   unattributed. <!-- TODO: say where to add alternate emails, if supported -->
4. In the app, set the project's **local repository path** to the folder name
   relative to `repo/` (e.g. `esports`). The path must stay inside `repo/` and
   contain a `.git` directory, otherwise the backend rejects it.

Inside Docker, `repo/` is mounted read-only at `/app/repo`. The app never
modifies student clones.

---

## 5. Every work session

1. Connect the **SMUResearch VPN**.
2. Reserve a GPU: `bash ai-engine/hpc/hpc-dev.sh submit`
3. Wait for `RUNNING`: `bash ai-engine/hpc/hpc-dev.sh status`
   (`PENDING` means the cluster is busy; re-check in a minute.)
4. Start everything: `bash start.sh` (enter your HPC password once).
5. Check it's up:

| Service | URL |
|---|---|
| Web app | http://localhost:3000 |
| Backend API docs | http://localhost:8000/docs |
| AI engine health | http://localhost:8001/health (`ok`, or `degraded` while models load) |
| MLflow | http://localhost:5000 |
| MinIO console | http://localhost:9001 |

---

## 6. Running an assessment (instructor workflow)

<!-- TODO: replace with the exact UI labels/screens from the frontend -->

1. Log in and open (or create) the **course** and **project**; add team
   members.
2. Set the project's **local repository path** (§4) and Jira board.
3. **Sync** repository and Jira data for the sprint.
4. Optionally upload project documents or manual sprint notes.
5. **Run the assessment** and choose the model (default `sprintsight-qwen`).
   Expect several minutes per team. Per-dimension progress appears in
   `docker compose logs -f sprintsight_ai`.
6. Review scores and evidence citations (they link to file:line), override
   if needed (overrides are audit-logged), then **export**.

Grading is **team-level**: one grade per team, with no individual member
grades.

---

## 7. Verify the GPU is doing the work

| Check | Command | Healthy result |
|---|---|---|
| Model fully on GPU | `curl http://localhost:11435/api/ps` | `size_vram` equals `size` |
| Live GPU usage | `bash ai-engine/hpc/hpc-dev.sh gpu --watch` | Utilisation and VRAM rise during an assessment |
| Which process holds VRAM | `bash ai-engine/hpc/hpc-dev.sh gpu --processes` | Only Ollama |
| Cluster dashboard | https://green.smu.edu.sg/gpustats (node → GPU → time range) | Matches the above |

Full measurement and tuning method: [gpu-utilisation-plan.md](gpu-utilisation-plan.md).

---

## 8. Shutting down, and GPU etiquette

```bash
bash stop.sh                                   # stops Docker + closes the tunnel
ssh <HPC_USER>@<HPC_LOGIN_HOST> "scancel --me" # releases the GPU
```

`stop.sh` does **not** cancel the Slurm job. An idle job keeps holding a
shared GPU until its 8-hour limit runs out, so cancel it when you finish.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot reach <host>. Is the SMUResearch VPN on?` | VPN off | Connect the VPN and re-run |
| `No running Slurm job named 'sprintsight-ollama'` | No GPU reserved *for you* (jobs aren't shared), job expired, or still `PENDING` | §5 steps 2–3 |
| Build fails: `failed to resolve source metadata for docker.io` / `pypi.org` | Building on the VPN | Build off-VPN (§3.1) |
| `/health` stays `degraded` | Models still loading on the GPU | Wait, then check `hpc-dev.sh status` |
| Assessment very slow, low GPU usage | Model partly on CPU, or a cold model load | §7 first row; see the GPU plan |
| "Local repository path must remain inside…" / "…not a Git repository" | Path outside `repo/`, or not a clone | §4 step 4 |
| Commits not attributed to students | Author email ≠ student account email | §4 step 3 |
| Job killed early | `project` queue pre-emption | Resubmit; models are cached |

---

## 10. Reference

- Cluster docs: https://violet.scis.dev/docs (containers, monitoring GPU metrics)
- `ai-engine/hpc/README.md`: cluster commands, `num_ctx` tuning
- `ai-engine/research/eval/RUNBOOK.md`: evaluation and research runs
- `backend/README.md`: email, audit retention, API testing

---

## Appendix A: where this guide lives

**Decision:** docs-as-code in this repository, linked from the README, plus
small, task-specific help inside the app that links back here. No separate
wiki.

| | External (repo `docs/`, wiki, docs site) | In-app (wizard, help modal) |
|---|---|---|
| Works before the app runs | **Yes.** VPN, Slurm, Docker and cloning all happen before there is a UI | No. The chicken-and-egg problem rules it out for setup |
| Stays in sync with scripts | **Yes, if in the repo**: changed in the same PR as `start.sh`/sbatch and reviewed. GitHub wiki and external sites drift, because they aren't PR-reviewed | Needs a frontend release for every wording change |
| Audience fit | Operators and developers | Instructors mid-task |
| Discoverability | Must be linked; easy to skip | **Seen at the moment of need** |
| Can react to live state | No | **Yes.** It can show "AI engine unreachable" or "repo path invalid" from `/health` and API errors |
| Cost to build | Minimal | Frontend work (owned by a teammate) |

The rationale:

1. Most of the guide (§2–§5, §7–§9) covers things that happen **outside and
   before** the app, so it has to live outside the app. Keeping it in the
   repo means one source of truth, versioned and reviewed alongside the
   scripts it describes.
2. Inside the app, **actionable state beats prose.** The most valuable in-app
   pieces are a status banner driven by `GET :8001/health` (GPU/AI engine
   offline → link to §5) and inline hints on the repository-path field
   (§4 rules). A short first-run checklist for instructors (§6) is optional.
   Every in-app message links to the matching section here instead of
   copying it.
3. If a public-facing site is wanted later, render this same `docs/` folder
   with MkDocs or GitHub Pages. That's a publishing step, not a second copy.
