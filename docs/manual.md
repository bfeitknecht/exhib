# exhib manual

How to use the gallery library, make collections, pieces and writings, and make them go live.
Commands are nushell. The `just` recipes set `KUBECONFIG` to `../infra/kubeconfig` (the infra repo root, next to this repo); this overrides `$env.KUBECONFIG`. Raw `kubectl` commands below need the same: `$env.KUBECONFIG = ("../infra/kubeconfig" | path expand)` from the exhib repo root.

Short form:

```nu
just manifest uploads/2026-11   # edit manifest.toml in the browser
just upload uploads/2026-11     # send it to the gallery
just logs                       # watch it publish
```

## 1. The library

The library is the PVC `exhib-site`, mounted at `/data` in the pod. The image holds code and templates only. It holds no media.

```
/data
├── incoming/      upload inbox; the processor polls it every 3 s
│   └── .failed-*  uploads that failed; kept for inspection
├── content/       live Hugo content tree (page bundles); source of truth for the site
│   ├── collections/<slug>/_index.md + converted media
│   ├── pieces/<slug>/index.md + converted media
│   └── writings/<slug>/index.md
├── originals/     private copies of every upload, never served
│   ├── collection/<slug>/
│   ├── piece/<slug>/
│   └── writing/<slug>/
├── public/        Hugo output; SWS serves this at gallery.0xbf.ch
└── .hugo-resources/  Hugo resized previews; cache, safe to delete
```

What lives where:

| Thing                                   | Lives in                  | Goes live by                     |
| --------------------------------------- | ------------------------- | -------------------------------- |
| Templates, CSS, JS, processor, sws.toml | this repo, baked in image | `v*` tag, CI push, Keel restart  |
| Collections, pieces, writings           | PVC `/data/content`       | `just upload` (no tag, no image) |
| Originals                               | PVC `/data/originals`     | never served                     |

Important: the repo `content/` directory seeds `/data/content` **only on first boot, when `/data/content` is empty**. After that, edits to repo `content/` do not reach production. The PVC is the source of truth for content.

## 2. The upload folder

Every item is one folder. The folder name is the URL slug. Use lowercase letters, digits and hyphens (`evening-walks`, `2026-11`). The folder holds `manifest.toml` and the source files:

| Kind         | Source files                        | URL                    |
| ------------ | ----------------------------------- | ---------------------- |
| `collection` | images and videos                   | `/collections/<slug>/` |
| `piece`      | one image or video                  | `/pieces/<slug>/`      |
| `writing`    | exactly one `.md` file (the body)   | `/writings/<slug>/`    |

Do not convert media. The processor does that.

### 2.1 Manifest editor (`just manifest`)

You do not need to write `manifest.toml` by hand. Put the source files in a slug folder under `uploads/`, then run the editor.

```
just manifest [folder] [--port N] [--no-browser]
```

| Argument       | Meaning                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------ |
| `[folder]`     | `uploads` (default) or one slug folder in it. Relative to where you run `just`.            |
| `--port N`     | serve on port `N`. Default: any free port.                                                 |
| `--no-browser` | do not open the browser. Open the printed URL yourself.                                    |

```nu
just manifest                        # folder list of uploads/
just manifest uploads/bw             # opens bw directly
just manifest uploads --port 4321    # fixed URL: http://127.0.0.1:4321/
```

One server serves all of `uploads/`:

- **Path bar** (top left, `uploads/<slug>`): type or pick another folder and press Enter. The browser back button works. With unsaved changes it asks first.
- Only direct child folders of `uploads/` open. No other path is reachable (no `..`, no `/`, no hidden folders).
- A folder name that is not a lowercase slug opens with a warning. Rename it before upload.
- Starting on a slug folder (`just manifest uploads/bw`) uses its parent as the root.

It runs on your machine only and never talks to the cluster. It needs [uv](https://docs.astral.sh/uv/). It writes only `manifest.toml`, plus `body.md` for a writing. It never changes media files. Stop it with Ctrl-C.

On the page:

- **Kind** (top right): collection, piece or writing. A new folder guesses: no media and one `.md` file is a writing, one media file a piece, else a collection.
- **Title, date, description, tags.** Date is `DD/MM/YYYY` (dots work too), time is 24h `HH:MM`, in the browser time zone (shown below the fields). **now** fills in the current minute. The manifest stores local time with its offset, e.g. `2026-11-15T18:30:00+01:00`. Description is markdown. Tags: type and press Enter or comma; Backspace in the empty field removes the last one.
- **Card**: live preview of the homepage card: cover or mosaic, title, date, rendered description, tags.
- **Media grid** (collection, piece): one tile per file. Badges show the `position` and `cover`. Excluded tiles are dimmed. Drag tiles to reorder. Click a tile to edit it.
- **Item editor** (below the grid, after a click): large preview, caption (empty means the file name), `position` (1 comes first; a number past the end means last), include, ← / → to move, and **cover** (collection only).
- **Cover**: press **cover** to make this item the homepage cover; press it again for the mosaic of the first nine images. Pressing it on another item moves the cover. A cover is always included. A video cover shows its poster on the site.
- **Cover crop**: while the item is the cover, the large preview shows the card's 1:√2 frame. Drag it to choose the part shown on the card; the card preview follows. **center** resets it. An image with the card's aspect ratio has nothing to crop.
- **Body** (writing): the text, saved to `body.md` (or to the one `.md` file already in the folder).
- **save** (button or ⌘S): checks the values and writes `manifest.toml`. Errors show next to the button; nothing is written then. The saved text shows below. `[[media]]` tables (`file`, `title`, `position`) appear only if you excluded a file, changed the order or set a caption. `thumbnail_focus` appears only if the crop is not centered.

Full flow for one collection:

```nu
just manifest              # open bw from the list; set fields, cover, crop; ⌘S
just upload uploads/bw
just logs                  # wait for "Published collection bw"
```

### 2.2 Manifest keys

```toml
kind = "collection"
title = "Evening walks"
date = 2026-11-07T18:30:00Z
```

| Key           | Required | Meaning                                                                                       |
| ------------- | -------- | --------------------------------------------------------------------------------------------- |
| `kind`        | yes      | `"collection"`, `"piece"` or `"writing"`                                                      |
| `title`       | yes      | page title                                                                                    |
| `date`        | yes      | TOML datetime (not a string). No zone means UTC. Sets feed order, newest first.               |
| `description` | no       | markdown; shown in intro and cards, flattened in feeds and `<meta>`                           |
| `tags`        | no       | list of strings, e.g. `["evergrowing"]`. Use slug-like names.                                 |
| `thumbnail`   | no       | collection only. File name of one source file. Without it, the card shows a mosaic.          |
| `thumbnail_focus` | no   | collection only, with `thumbnail`. Crop of the cover on the card: `[x, y]` in percent, as CSS `object-position`. Default `[50, 50]`. |
| `[[media]]`   | no       | collection and piece. Per-file overrides. Without it, every supported file is included.       |

Without `[[media]]`:

- Every supported file in the folder becomes one item. Hidden files and unknown types are skipped.
- Order is numeric-aware filename order (`2-a.jpg` before `10-b.jpg`).
- Caption comes from the file name: `01-paper-light.jpg` becomes "Paper light".

With `[[media]]`, only the listed files are included:

```toml
[[media]]
file = "IMG_4012.HEIC"
title = "Street after rain"   # optional; falls back to the file name
position = 1                  # optional; falls back to list index

[[media]]
file = "clip.mov"
```

`position` sets the place in the grid: lower comes first. It was called `weight`, then `order`. A manifest with either fails with `[[media]] weight is renamed to position` (or `order`). The editor reads both and writes `position`. Bundles already on the PVC with `weight` still sort correctly.

Display order on the page:

1. Images with an EXIF capture date, oldest first.
2. Images without capture date, by `position`.
3. Videos, by `position`.

So `position` is a fallback. EXIF capture date wins for images.

Supported media:

- Images: `jpg jpeg png webp avif tif tiff heic heif`
- Video: `mov mp4 m4v 3gp mkv webm`

## 3. Collections

Example, a monthly snapshot:

```
2026-11/
├── manifest.toml
├── IMG_4001.HEIC
├── IMG_4002.HEIC
└── IMG_4003.MOV
```

```toml
kind = "collection"
title = "November 2026"
date = 2026-11-30T12:00:00Z
tags = ["evergrowing"]
thumbnail = "IMG_4002.HEIC"
```

## 4. Pieces

Same as a collection, with `kind = "piece"`. The page shows the **first ordered** media item only. Use one file per piece folder.

```toml
kind = "piece"
title = "Evening study"
date = 2026-11-01T00:00:00Z
description = "A short note about this work."
tags = ["design"]
```

## 5. Writings

Writings are text-only pages. They have no media, no grid and no metadata. They show in the home feed (no image), in `/writings/`, in `/tags/` and in the RSS and Atom feeds.

```
field-notes/
├── manifest.toml
└── body.md
```

```toml
kind = "writing"
title = "Field notes"
date = 2026-11-08T12:00:00Z
description = "Optional summary. *Markdown* is supported."
tags = ["essay"]
```

```markdown
First line
Second line

A new stanza.
```

Rules:

- The folder holds `manifest.toml` and exactly one `.md` file. Any name works; the editor uses `body.md`. Other files fail the upload.
- The body has no front matter. All metadata is in `manifest.toml`. A body that starts with `+++` or `---` fails the upload.
- Markdown. A single newline breaks the line (`white-space: pre-line`), so verse keeps its shape. A blank line starts a new paragraph or stanza.
- Raw HTML is dropped (`markup.goldmark.renderer.unsafe = false`).

The editor (`just manifest`) has a body text area for writings. You can write the whole piece there.

## 6. Make it go live

Before upload, strip metadata you do not want public. **All EXIF/IPTC/XMP is published, including GPS.** The processor copies all metadata into the served WebP.

```nu
exiftool -G1 -a -s path/to/2026-11/IMG_4001.HEIC          # inspect
exiftool -GPS:all= -overwrite_original path/to/2026-11/*  # drop GPS
```

Upload and watch:

```nu
just upload path/to/2026-11
just logs
```

Success prints `Published collection 2026-11` (or `piece`, `writing`). The page is live at `https://gallery.0xbf.ch/collections/2026-11/`. No commit, tag or image build is needed.

Video conversion is slow (lossless VP9 on the Pi). A minute of video can take many minutes. The site keeps serving the old build until the new build is complete.

### 6.1 Staging folder and size limits

Keep upload folders in `uploads/` at the repo root. Git and Docker ignore it. Do **not** put upload folders in `content/`: that only seeds an empty PVC, and it puts the files into git and the image.

```nu
just manifest uploads/bw
just upload uploads/bw
```

The pod has 2 GiB. Measured with a 2 GiB cap:

| Step                                    | Peak memory                      |
| --------------------------------------- | -------------------------------- |
| `cwebp` on 4961×7016 RGBA (35 Mpx)      | 0.6–0.8 GB                       |
| `cwebp` on 7016×9921 RGBA (70 Mpx)      | 1.5 GB (too close; do not use)   |
| Hugo cold build with 35 Mpx posters     | 1.5 GB (2 threads, `GOMEMLIMIT`) |

Keep images at or below about 35 Mpx (A2 at 300 dpi, 4961×7016). Downscale larger ones before upload:

```nu
sips --resampleHeightWidth 7016 4961 uploads/bw/abriss.png
```

If a step is killed for memory, the upload fails like any other (§8), and the site stays up. `EXHIB_HUGO_THREADS` (default `2`) and `EXHIB_HUGO_MEMLIMIT` (default `1GiB`) in the pod env tune the Hugo build.

Avoid `?`, `*`, `[` and `]` in file names. Hugo reads a resource `src` as a glob, so `??.png` matches other files and the image drops off the page.

### 6.2 Previews

The grid, the homepage cards and the piece stage show resized lossy WebP previews (1200 px wide; 2400 px for the piece stage) that Hugo makes at build time. The fullscreen view shows the lossless original and loads it only when opened. Previews are cached in `/data/.hugo-resources`, so a rebuild or pod restart reuses them. The first build after a new image makes all missing previews once.

Hugo does not build pages with a date in the future. A future-dated item appears only at the first rebuild after that date. Rebuilds happen on upload, `just rebuild` or pod restart.

Preview templates or a writing locally with repo content:

```nu
just serve   # http://localhost:4173
```

## 7. Change, replace or delete an item

A slug can be uploaded once. A second upload with the same slug fails with `an item with this slug already exists`. To replace or delete, remove the bundle and the original, then rebuild:

```nu
kubectl -n exhib exec deploy/exhib -- rm -rf /data/content/collections/2026-11 /data/originals/collection/2026-11
just rebuild
```

Sections and original folders: `collections` / `collection`, `pieces` / `piece`, `writings` / `writing`. Then `just upload` the corrected folder if you replace it. Your local folder still holds `manifest.toml`, so `just manifest` reopens it with the old values.

A bundle with no upload original (seeded from the repo or added by hand) is replaced by an upload with the same slug.

For a text-only fix (title, description, tags), you can also edit the front matter of `/data/content/<section>/<slug>/_index.md` (or `index.md`) in place, then `just rebuild`. Keep the `[[resources]]` blocks. They are generated.

A pod restart also rebuilds (the processor builds on boot), but the `Recreate` strategy gives a short outage. Prefer `just rebuild`.

## 8. When an upload fails

The processor logs `Upload <slug> failed: <reason>` and renames the folder to `/data/incoming/.failed-<slug>`. It removes the partial bundle and the pending original. The live site is not changed.

```nu
kubectl -n exhib exec deploy/exhib -- ls -a /data/incoming
```

To retry: fix the cause in your local folder, delete the failed copy, upload again.

```nu
kubectl -n exhib exec deploy/exhib -- rm -rf /data/incoming/.failed-2026-11
just upload path/to/2026-11
```

Common reasons:

- `date` written as a string (`"2026-11-07"`).
- Slug with uppercase or underscores.
- `thumbnail` names a file not in the upload.
- No supported media in a collection or piece folder.
- Writing: zero or several `.md` files, extra files, or front matter in the body.
- `[[media]]` uses `weight` or `order` instead of `position`.

## 9. How the pipeline works

There is no uploader sidecar. It was a busybox container that slept. Its only job was to be an `exec` target with a writable `/data`. It did no conversion. Conversion, Hugo and front matter are in the processor. The pod is now one container, and `just upload` execs into it.

The container runs `uv run python entrypoint.py` (Python 3.15). The supervisor creates the `/data` directories, then starts two children:

- `static-web-server`: serves `/data/public` on `8080`, `/health` for probes, `Cache-Control: no-cache` on all responses.
- `python -m processor`: the ingest loop.

If one child exits, the supervisor stops the other and exits with its code (a signal N gives `128 + N`). Kubernetes then restarts the pod.

Upload path, step by step:

1. **Transfer** (`just upload`, on your machine). Checks slug and `manifest.toml`. Refuses if `/data/incoming/<slug>` is already queued. Streams the folder as tar (no macOS xattrs, no `.DS_Store`) through `kubectl exec` into `/data/incoming/.upload-<slug>-<epoch>`. Then `mv` to `/data/incoming/<slug>`. The hidden name hides the partial copy from the processor. The `mv` is atomic, so the processor sees only complete folders.
2. **Detect** (`processor/__main__.py`). Every 3 s, takes non-hidden folders in `/data/incoming`, sorted, one at a time.
3. **Validate** (`processor/bundle.py: read_manifest`, `publish_bundle`). Slug format, `kind`, `title`, TOML datetime `date`, no existing `/data/originals/<kind>/<slug>`.
4. **Write the bundle** in `/data/content/<section>/<slug>/`:
    - Writing (`write_writing`): checks the one `.md` body, then writes `index.md` = front matter from the manifest + body.
    - Collection or piece (`write_media_bundle`): converts each file (`processor/media.py`) into a scratch dir `.converted/`, then writes `_index.md` (collection) or `index.md` (piece).
        - Images: `cwebp -lossless -exact` to WebP. HEIC/HEIF decode first with `heif-convert`; AVIF via `ffmpeg`. Then `exiftool -TagsFromFile` copies all source metadata into the WebP, so Hugo can read EXIF.
        - Video: `ffmpeg` to WebM, lossless VP9 video, Opus 128k audio, metadata kept, no resize. Poster: frame at 1 s (falls back to frame 0), to lossless WebP, metadata copied.
        - Video facts: `ffprobe` (JSON) for resolution, frame rate, duration. Falls back to parsing the `ffmpeg -i` banner. Format is fixed `WebM · VP9`.
5. **Front matter** (`build_front_matter`). TOML `+++` block: `title`, `date` (UTC offset), optional `description`, `tags`, `thumbnail` (mapped to the converted file; a video maps to its poster), `thumbnail_focus`. Media bundles get one `[[resources]]` per output file with `params.position` and `params.kind`. Videos also get `format`, `resolution`, `framerate`, `duration`, `poster`. Each poster is its own resource with `role = "poster"`, so templates hide it from the grid.
6. **Keep original.** Copies the upload folder to `/data/originals/<kind>/.<slug>.pending`.
7. **Build** (`build_and_publish`). `hugo --source /app --contentDir /data/content --destination /data/.public-next --minify`. Templates come from the image; content from the PVC. Hugo reads EXIF from the WebP files at build time for the metadata list and ordering.
8. **Swap.** Renames `public` to `.public-previous`, `.public-next` to `public`, deletes the old one. SWS never serves a half-written site. On a failed rename it restores the old one.
9. **Commit.** Renames the pending original to `/data/originals/<kind>/<slug>` and deletes the inbox folder.

Any error in steps 3 to 8 removes the bundle and pending original and parks the upload as `.failed-<slug>` (§8).

`just rebuild` runs steps 7 and 8 only (`python -m processor rebuild`).

Generated front matter for a collection with one image and one video:

```toml
+++
title = "November 2026"
date = 2026-11-30T12:00:00+00:00
tags = ["evergrowing"]
thumbnail = "IMG_4002.webp"

[[resources]]
src = "IMG_4002.webp"
title = "IMG 4002"
[resources.params]
position = 1
kind = "image"

[[resources]]
src = "IMG_4003.webm"
title = "IMG 4003"
[resources.params]
position = 2
kind = "video"
format = "WebM · VP9"
resolution = "1920×1080"
framerate = "30 fps"
duration = "12 s"
poster = "IMG_4003-poster.webp"

[[resources]]
src = "IMG_4003-poster.webp"
title = "IMG 4003"
[resources.params]
position = 2
kind = "image"
role = "poster"
+++
```

Generated `index.md` for a writing:

```markdown
+++
title = "Field notes"
date = 2026-11-08T12:00:00+00:00
description = "Optional summary. *Markdown* is supported."
tags = ["essay"]
+++

First line
Second line

A new stanza.
```

## 10. Develop and release

Python is 3.15, managed by uv. Two uv projects:

| Project        | Path              | Runs where     | Purpose                              |
| -------------- | ----------------- | -------------- | ------------------------------------ |
| `exhib`        | repo root         | image + local  | `entrypoint.py`, `processor/`        |
| `exhib-manifest` | `tools/manifest/` | your machine | manifest editor (`just manifest`)    |

Both have no third-party dependencies. `tools/` and `docs/` are not in the image (`.dockerignore`).

```nu
uv run python -m processor rebuild   # needs hugo; uses $env.EXHIB_DATA (default /data)
uvx ruff format processor entrypoint.py tools/manifest/src
```

The image is `python:3.15-alpine3.24` plus uv, Hugo extended, SWS, FFmpeg, libwebp, libheif and exiftool. `uv sync --frozen` builds the venv at build time. At runtime `uv run --no-sync` only starts it.

Release: commit, then push a `v*` tag. CI publishes `ghcr.io/bfeitknecht/exhib:latest` and `:<tag>`. Keel sees the new digest and restarts the pod. On boot the processor rebuilds `/data/public` with the new templates. Content on the PVC is untouched.

Infra contract (`bfeitknecht/infra`, `kubernetes/applications/exhib/`): one container, image `ENTRYPOINT` (no `command`), port `8080`, probes on `/health`, `/data` read-write. Keep these stable, or change infra in step.

## 11. Known gaps

- Uploaded videos get no animated `preview` WebP. Grid tiles fall back to an autoplaying `<video>`. The placeholder previews were made by hand.
- No in-place update of an uploaded item; delete and re-upload (§7).
- No k8up Schedule for exhib. `/data/originals` holds the only copy of uploaded originals and writings.
