# Local CI Runners with `act`

PromptGrimoire relies on GitHub Actions for its CI pipeline. When debugging complex failures—especially E2E test failures that are difficult to reproduce natively on a host machine—it is useful to run the CI pipeline locally exactly as it executes on GitHub.

To achieve this, we use [`act`](https://github.com/nektos/act), a tool that runs GitHub Actions workflows locally using Docker. We specifically use it via the GitHub CLI extension: `gh act`.

## Prerequisites

1. **Docker:** Must be installed and running.
2. **Docker Permissions:** Your user must be part of the `docker` group so that `act` can interact with the Docker daemon without `sudo`.
   ```bash
   sudo usermod -aG docker $USER
   # You may need to log out and log back in, or run `newgrp docker`
   ```
3. **GitHub CLI & Act Extension:**
   ```bash
   gh extension install https://github.com/nektos/gh-act
   ```

## The Problem with Default Workflows

You **cannot** simply run `gh act pull_request` against the default `.github/workflows/ci.yml`. If you do, you will encounter several issues:

1. **Port Conflicts:** `act` runs its main container on the host network by default and maps service ports directly to the host. The `ci.yml` defines three parallel jobs (`test-all`, `e2e-playwright`, `nicegui-ui`), each of which spins up a PostgreSQL 17 service mapped to `ports: - 5432:5432`. Running this will cause the jobs to collide with each other, and it will clobber any local Postgres instance you already have running on port 5432.
2. **Docker Network Isolation Issues:** If you try to fix the port conflicts by isolating the run in a custom bridge network (e.g., `gh act ... --network act-bridge`), `act` exhibits a bug where the main container is placed on `act-bridge`, but the service containers are placed on dynamically generated, isolated networks. The main container will fail to resolve the `postgres` host, resulting in `[Errno -3] Temporary failure in name resolution`.
3. **Segfaults on Health Checks:** The current version of `act` has a known bug where evaluating service health checks (e.g., `--health-cmd "pg_isready -U postgres"`) can cause the Go runtime to panic and segfault.

## The Solution: `act-ci.yml`

To work around these limitations, we maintain a modified workflow file specifically for local debugging at `.github/workflows/act-ci.yml`.

This file patches the standard `ci.yml` in three ways:
1. **Port Remapping:** The Postgres services are mapped to `ports: - 5433:5432` to avoid conflicting with a local host database on `5432`.
2. **URL Adjustment:** The `DEV__TEST_DATABASE_URL` environment variables are updated to connect to `localhost:5433`.
3. **Health Checks Disabled:** The `options: >- --health-cmd ...` block is commented out for the Postgres services to prevent `act` from segfaulting.

*(Note: If the primary `ci.yml` changes significantly, `act-ci.yml` will need to be re-synced and patched with these three modifications).*

## Custom Runner Image

`act` does not support `actions/cache`, so every run cold-starts TinyTeX and system packages. The LaTeX font cache build alone takes ~5GB RAM and 10+ minutes. To avoid this, build a custom Docker image with everything pre-installed:

```bash
docker build -t grimoire-act-runner -f Dockerfile.act .
```

This only needs rebuilding when `scripts/setup_latex.py` or system dependencies change. Use `-P` to map it:

```bash
gh act pull_request -W .github/workflows/act-ci.yml -j test-all \
  -P ubuntu-latest=grimoire-act-runner
```

Or add to `~/.config/act/actrc` (or project `.actrc`):
```
-P ubuntu-latest=grimoire-act-runner
```

## How to Run

To run a specific job locally, use the following command, specifying the patched workflow file and the exact job you want to debug.

**Do not run all jobs at once**, as they will all try to bind to `5433`. Run them sequentially by targeting them with the `-j` flag:

```bash
# Debug the NiceGUI UI lane
gh act pull_request -W .github/workflows/act-ci.yml -j nicegui-ui

# Debug the Playwright lane
gh act pull_request -W .github/workflows/act-ci.yml -j e2e-playwright

# Debug the standard unit and integration tests
gh act pull_request -W .github/workflows/act-ci.yml -j test-all
```

**Warning on Dry Runs:** Do not use the `--dryrun` flag. Due to the way `act` handles service container stubs, it will still segfault when tearing down the environment even if the health checks are removed. Run the jobs natively.
