# Plan: Move Regeneratable Storage to /scratch

## Problem
The `/work/` partition has a 150GB quota, currently at 262GB usage. The main culprits are:
- `.venv/` - Python virtual environment (PyTorch, vLLM, CUDA deps) - likely 50-100GB+
- Model cache in `$HOME/.cache/vllm-models/` - 40-120GB per model

## Solution
Move all regeneratable data to `/scratch/` (500GB available on `/` partition):
1. **Virtual environment** → `/scratch/venv/`
2. **Model/HuggingFace cache** → `/scratch/cache/`

## Files to Modify

### 1. [hpc_setup.sh](hpc_setup.sh)

Update the environment variables block (lines 63-86) to:

```bash
# Cache directories on /scratch (500GB available, regeneratable)
export VLLM_BASE="/scratch/cache/vllm"
export HF_HOME="/scratch/cache/huggingface"
export HUGGINGFACE_HUB_CACHE="/scratch/cache/huggingface/hub"
export VLLM_CACHE_ROOT="/scratch/cache/vllm"
export TORCH_HOME="/scratch/cache/torch"

# Virtual environment on /scratch
export UV_PROJECT_ENVIRONMENT="/scratch/venv"
```

Add directory creation before `uv sync`:

```bash
mkdir -p /scratch/cache/vllm /scratch/cache/huggingface/hub /scratch/cache/torch /scratch/venv
```

### 2. [hpc_env.sh](hpc_env.sh)

Update to match (lines 8-11):

```bash
export VLLM_BASE="/scratch/cache/vllm"
export HF_HOME="/scratch/cache/huggingface"
export HUGGINGFACE_HUB_CACHE="/scratch/cache/huggingface/hub"
export VLLM_CACHE_ROOT="/scratch/cache/vllm"
export TORCH_HOME="/scratch/cache/torch"
export UV_PROJECT_ENVIRONMENT="/scratch/venv"
```

## Immediate Actions (Before Machine Start)

Via web interface, delete from `/work/20251104-FirstRun/`:
- [x] `.venv/` (will be recreated at `/scratch/venv/`)

## Verification

After starting the machine and running `hpc_setup.sh`:

```bash
# Confirm venv is in /scratch
ls -la /scratch/venv/

# Confirm cache directories exist
ls -la /scratch/cache/

# Check /work usage is now under quota
du -sh /work/20251104-FirstRun/

# After first vLLM run, confirm models are in /scratch
ls -la /scratch/cache/huggingface/hub/
```

## Syncthing (.stignore)

No changes needed. The `/scratch/` paths are outside the Syncthing-watched directory (`/work/20251104-FirstRun/`), so they won't be synced regardless.

Current `.stignore` already excludes `.venv/` and `.cache/` for any local development.

## Notes

- Models will re-download on first vLLM run (~30 min for 20b model)
- `.venv/` recreated by `uv sync` in hpc_setup.sh (already present at line 94)
- Critical data (`input/`, `Elaborations/`, `out/`) stays in `/work/`
