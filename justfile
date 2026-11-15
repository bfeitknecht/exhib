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

# Preview the site locally with the repo content.
serve:
    hugo server --bind 0.0.0.0 --port 4173
