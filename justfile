# exhib — common tasks. `just` (https://just.systems) with no arguments lists recipes.

# Upload a piece or collection package (a lowercase-slug folder with manifest.toml
# and the media files) to the gallery's processor inbox on the cluster.
# Requires kubectl configured for the cluster.
upload package:
    #!/usr/bin/env bash
    set -euo pipefail
    PACKAGE="{{package}}"
    if [[ ! -d "$PACKAGE" ]]; then
      echo "Usage: just upload path/to/item-folder" >&2
      exit 2
    fi
    PACKAGE="$(cd "$PACKAGE" && pwd)"
    SLUG="$(basename "$PACKAGE")"
    [[ -f "$PACKAGE/manifest.toml" ]] || { echo "manifest.toml is required in the package folder" >&2; exit 2; }
    [[ "$SLUG" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "Folder name must be a lowercase slug (letters, numbers, hyphens)." >&2; exit 2; }
    command -v kubectl >/dev/null || { echo "kubectl is required." >&2; exit 1; }

    POD="$(kubectl -n exhib get pods -l app.kubernetes.io/name=exhib -o jsonpath='{.items[0].metadata.name}')"
    [[ -n "$POD" ]] || { echo "No exhib pod found in namespace exhib." >&2; exit 1; }
    REMOTE="/data/incoming/.upload-${SLUG}-$(date +%s)"
    DEST="/data/incoming/${SLUG}"
    if kubectl -n exhib exec "$POD" -c uploader -- sh -c "test ! -e '$DEST'"; then
      :
    else
      echo "An upload with slug '$SLUG' is already queued." >&2
      exit 1
    fi
    kubectl -n exhib exec "$POD" -c uploader -- mkdir -p "$REMOTE"
    tar -C "$PACKAGE" -cf - . | kubectl -n exhib exec -i "$POD" -c uploader -- tar -xf - -C "$REMOTE"
    kubectl -n exhib exec "$POD" -c uploader -- mv "$REMOTE" "$DEST"
    echo "Queued $SLUG. The processor will transcode it and rebuild the gallery automatically."
