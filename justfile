# exhib: common tasks. Run `just` to list the recipes.
# Paths are relative to the directory you run `just` from.

# kubectl uses the cluster kubeconfig in the infra repo root, next to this repo.
export KUBECONFIG := justfile_directory() / ".." / "infra" / "kubeconfig"

# List the available recipes.
default:
    @just --list

# Open the manifest editor on uploads/ (or on one slug folder in it). Flags: --port N, --no-browser.
manifest folder="uploads" *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{invocation_directory()}}"
    FOLDER="{{folder}}"
    # Run from anywhere: fall back to uploads/ next to this justfile.
    [[ -d "$FOLDER" ]] || FOLDER="{{justfile_directory()}}/{{folder}}"
    [[ -d "$FOLDER" ]] || { echo "Not a folder: {{folder}}" >&2; exit 2; }
    exec uv run --quiet --project "{{justfile_directory()}}/tools/manifest" \
      exhib-manifest "$(cd "$FOLDER" && pwd)" {{flags}}

# Upload a slug folder (manifest.toml plus media, or plus one .md body for a writing). Needs kubectl for the cluster.
upload folder:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{invocation_directory()}}"
    PACKAGE="{{folder}}"
    if [[ ! -d "$PACKAGE" ]]; then
      echo "Usage: just upload path/to/slug-folder" >&2
      exit 2
    fi
    PACKAGE="$(cd "$PACKAGE" && pwd)"
    SLUG="$(basename "$PACKAGE")"
    [[ -f "$PACKAGE/manifest.toml" ]] || { echo "manifest.toml is required. Run: just manifest {{folder}}" >&2; exit 2; }
    [[ "$SLUG" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "Folder name must be a lowercase slug (letters, numbers, hyphens)." >&2; exit 2; }
    command -v kubectl >/dev/null || { echo "kubectl is required." >&2; exit 1; }
    [[ -f "$KUBECONFIG" ]] || { echo "No kubeconfig at $KUBECONFIG (infra repo root)." >&2; exit 1; }

    POD="$(kubectl -n exhib get pods -l app.kubernetes.io/name=exhib -o jsonpath='{.items[0].metadata.name}')"
    [[ -n "$POD" ]] || { echo "No exhib pod found in namespace exhib." >&2; exit 1; }
    REMOTE="/data/incoming/.upload-${SLUG}-$(date +%s)"
    DEST="/data/incoming/${SLUG}"
    if ! kubectl -n exhib exec "$POD" -- test ! -e "$DEST"; then
      echo "An upload with slug '$SLUG' is already queued." >&2
      exit 1
    fi
    kubectl -n exhib exec "$POD" -- mkdir -p "$REMOTE"
    COPYFILE_DISABLE=1 tar -C "$PACKAGE" --no-xattrs --exclude=.DS_Store -cf - . | kubectl -n exhib exec -i "$POD" -- tar -xf - -C "$REMOTE"
    kubectl -n exhib exec "$POD" -- mv "$REMOTE" "$DEST"
    echo "Queued $SLUG. Follow with: just logs"

# Follow the processor and web server logs.
logs:
    kubectl -n exhib logs deploy/exhib -f

# Rebuild the live site from /data/content (after a manual edit on the PVC).
rebuild:
    kubectl -n exhib exec deploy/exhib -- uv run --frozen --no-sync python -m processor rebuild

# Format Python sources. `just fmt --check` only reports (CI uses it).
fmt *flags:
    uvx ruff@0.15 format {{flags}} processor uploader entrypoint.py tools/manifest/src

# Everything CI runs: format check, lint, Hugo build.
check:
    uvx ruff@0.15 format --check processor uploader entrypoint.py tools/manifest/src
    uvx ruff@0.15 check processor uploader entrypoint.py tools/manifest/src
    hugo --quiet --destination "$(mktemp -d)"

# Build the image for the local architecture (smoke test before a release).
image:
    docker buildx build --load -t exhib:dev .

# Tag vX.Y.Z from pyproject.toml and push (CI publishes the image). --check only validates.
release *flags:
    #!/usr/bin/env bash
    set -euo pipefail
    version="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml | head -1)"
    tag="v${version}"
    [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "pyproject.toml version '$version' is not X.Y.Z" >&2; exit 1; }
    ! git rev-parse -q --verify "refs/tags/$tag" >/dev/null || { echo "tag $tag exists; bump pyproject.toml" >&2; exit 1; }
    [[ -z "$(git status --porcelain)" ]] || { echo "working tree is not clean; commit first" >&2; exit 1; }
    git fetch -q origin
    [[ "$(git rev-parse HEAD)" == "$(git rev-parse @{u})" ]] || { echo "HEAD differs from upstream; push or pull first" >&2; exit 1; }
    just check
    if [[ "{{flags}}" == *--check* ]]; then echo "$tag is ready"; exit 0; fi
    git tag -a "$tag" -m "Release $version"
    git push origin "$tag"
    echo "pushed $tag; CI publishes ghcr.io/bfeitknecht/exhib"

# Make the small lossy copies for every image that lacks them, then rebuild. Safe to re-run.
variants:
    kubectl -n exhib exec deploy/exhib -- uv run --frozen --no-sync python -m processor variants

# Preview the site locally with the repo content.
serve:
    hugo server --bind 0.0.0.0 --port 4173
