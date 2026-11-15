# exhib manual

How to use the gallery library, make pieces and collections, and make them go live.
Commands are nushell. `kubectl` must point at the cluster
(`kubectl --kubeconfig kubeconfig` from the infra repo root, or `$env.KUBECONFIG`).

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
│   └── piece/<slug>/
└── public/        Hugo output; SWS serves this at gallery.0xbf.ch
```

What lives where:

| Thing                                   | Lives in                  | Goes live by                     |
| --------------------------------------- | ------------------------- | -------------------------------- |
| Templates, CSS, JS, processor, sws.toml | this repo, baked in image | `v*` tag, CI push, Keel restart  |
| Pieces and collections                  | PVC `/data/content`       | `just upload` (no tag, no image) |
| Writings                                | PVC `/data/content`       | `kubectl cp` + rebuild (see §5)  |
| Originals                               | PVC `/data/originals`     | never served                     |

Important: the repo `content/` directory seeds `/data/content` **only on first boot, when `/data/content` is empty**. After that, edits to repo `content/` do not reach production. The PVC is the source of truth for content.

## 2. Make a collection

1. Make a folder. The folder name is the URL slug. Use lowercase letters, digits and hyphens (`evening-walks`, `2026-11`).
2. Put the source media files in it. Do not convert them. The processor does that.
3. Add `manifest.toml`.

Minimal manifest:

```toml
kind = "collection"
title = "Evening walks"
date = 2026-11-07T18:30:00Z
```

All keys:

| Key           | Required | Meaning                                                                            |
| ------------- | -------- | ---------------------------------------------------------------------------------- |
| `kind`        | yes      | `"collection"` or `"piece"`                                                        |
| `title`       | yes      | page title                                                                         |
| `date`        | yes      | TOML datetime (not a string). No zone means UTC. Sets feed order, newest first.    |
| `description` | no       | markdown; shown in intro and cards, flattened in feeds and `<meta>`                |
| `tags`        | no       | list of strings, e.g. `["evergrowing"]`. Use slug-like names.                      |
| `thumbnail`   | no       | file name of one source file (`"cover.jpg"`). Without it, the card shows a mosaic. |
| `[[media]]`   | no       | per-file overrides. Without it, every supported file is included.                  |

Without `[[media]]`:

- Every supported file in the folder becomes one item. Hidden files and unknown types are skipped.
- Order is numeric-aware filename order (`2-a.jpg` before `10-b.jpg`). This order sets `weight`.
- Title comes from the file name: `01-paper-light.jpg` becomes "Paper light".

With `[[media]]`, only the listed files are included, in list order:

```toml
[[media]]
file = "IMG_4012.HEIC"
title = "Street after rain"   # optional; falls back to file stem
weight = 1                    # optional; falls back to list position

[[media]]
file = "clip.mov"
```

Display order on the page:

1. Images with an EXIF capture date, oldest first.
2. Images without capture date, by `weight`.
3. Videos, by `weight`.

So `weight` is a fallback. EXIF capture date wins for images.

Supported input:

- Images: `jpg jpeg png webp avif tif tiff heic heif`
- Video: `mov mp4 m4v 3gp mkv webm`

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

## 3. Make a piece

Same as a collection, with `kind = "piece"`. The page shows the **first ordered** media item only. A piece needs at least one image or video. Use one file per piece folder.

```toml
kind = "piece"
title = "Evening study"
date = 2026-11-01T00:00:00Z
description = "A short note about this work."
tags = ["design"]
```

## 4. Make it go live

Before upload, strip metadata you do not want public. **All EXIF/IPTC/XMP is published, including GPS.** The processor copies all metadata into the served WebP.

```nu
exiftool -G1 -a -s path/to/2026-11/IMG_4001.HEIC          # inspect
exiftool -GPS:all= -overwrite_original path/to/2026-11/*  # drop GPS
```

Upload:

```nu
just upload path/to/2026-11
```

Watch the processor:

```nu
kubectl -n exhib logs deploy/exhib -f
```

Success prints `Published collection 2026-11`. The page is live at `https://gallery.0xbf.ch/collections/2026-11/`. No commit, tag or image build is needed.

Conversion is slow for video (lossless VP9 on the Pi). A minute of video can take many minutes. The site keeps serving the old build until the new build is complete.

## 5. Writings

Writings are text-only pages at `/writings/<slug>/`. They have no media, no grid and no metadata. They show in the home feed (no image), in `/writings/`, in `/tags/` and in the RSS and Atom feeds.

`just upload` does not accept writings. The processor accepts only `piece` and `collection`. You write the Hugo page directly into the live content tree, then rebuild.

### 5.1 Write the page

Make a folder named after the slug (lowercase, digits, hyphens). Put one file `index.md` in it:

```
field-notes/
└── index.md
```

```toml
+++
title = "Field notes"
date = 2026-11-08T12:00:00Z
description = "Optional summary. *Markdown* is supported."
tags = ["essay"]
+++

First line
Second line

A new stanza.
```

Front matter (TOML, `+++`):

| Key           | Required | Meaning                                                                    |
| ------------- | -------- | -------------------------------------------------------------------------- |
| `title`       | yes      | page title                                                                 |
| `date`        | yes      | TOML datetime. Sets feed order. A future date hides the page (see below).  |
| `description` | no       | markdown; shown under the title and on cards; plain text in feeds          |
| `tags`        | no       | list of slug-like strings                                                  |
| `draft`       | no       | `true` hides the page from the build                                       |

Body rules:

- Markdown.
- A single newline breaks the line. The body uses `white-space: pre-line`. Verse keeps its shape.
- A blank line starts a new paragraph or stanza.
- Raw HTML is dropped (`markup.goldmark.renderer.unsafe = false`).
- Do not add images. The template shows none.

Hugo does not build pages with a date in the future. If you set a future date, the page appears only on the first rebuild after that date. Rebuilds happen only on upload, exec rebuild or pod restart.

Preview locally before you publish. Put the folder in repo `content/writings/` and run:

```nu
hugo server --bind 0.0.0.0 --port 4173
```

### 5.2 Publish

```nu
let slug = "field-notes"
let pod = (kubectl -n exhib get pods -l app.kubernetes.io/name=exhib -o jsonpath='{.items[0].metadata.name}')
kubectl -n exhib exec $pod -- mkdir -p $"/data/content/writings/($slug)"
kubectl -n exhib cp $"./($slug)/index.md" $"exhib/($pod):/data/content/writings/($slug)/index.md"
kubectl -n exhib exec $pod -- python3 -c "from processor.bundle import build_and_publish; build_and_publish()"
```

The rebuild prints Hugo's page counts. A Hugo error means the old site stays live. Fix the file and run the rebuild again. The page is then live at `https://gallery.0xbf.ch/writings/field-notes/`.

### 5.3 Edit

Copy the changed `index.md` over the old one with the same `kubectl cp` line, then rebuild. To change the slug, delete the old folder (5.4) and publish under the new slug. The old URL then returns 404.

### 5.4 Delete

```nu
kubectl -n exhib exec $pod -- rm -rf $"/data/content/writings/($slug)"
kubectl -n exhib exec $pod -- python3 -c "from processor.bundle import build_and_publish; build_and_publish()"
```

### 5.5 Keep a copy in git

The PVC copy is the live one. There is no copy in `/data/originals` and no backup. Commit each writing to repo `content/writings/<slug>/index.md` too. This gives history, and it seeds a fresh, empty PVC. Repo content does **not** update a PVC that already has content, so always do 5.2 as well.

## 6. Change, replace or delete an item

A slug can be uploaded once. A second upload with the same slug fails with `an item with this slug already exists`. To replace or delete, remove the bundle and the original, then rebuild:

```nu
let pod = (kubectl -n exhib get pods -l app.kubernetes.io/name=exhib -o jsonpath='{.items[0].metadata.name}')
kubectl -n exhib exec $pod -- rm -rf /data/content/collections/2026-11 /data/originals/collection/2026-11
kubectl -n exhib exec $pod -- python3 -c "from processor.bundle import build_and_publish; build_and_publish()"
```

Then re-upload with `just upload` if you replace it.

For a text-only fix (title, description, tags), edit the front matter of `/data/content/<section>/<slug>/_index.md` (or `index.md`) in place and rebuild. Keep the `[[resources]]` blocks. They are generated.

A pod restart also rebuilds (the processor builds on boot), but `Recreate` strategy gives a short outage. Prefer the exec rebuild.

## 7. When an upload fails

The processor logs `Upload <slug> failed: <reason>` and renames the folder to `/data/incoming/.failed-<slug>`. It removes the partial bundle and the pending original. The live site is not changed.

```nu
kubectl -n exhib exec deploy/exhib -- ls -a /data/incoming
```

To retry: fix the cause in your local folder, delete the failed copy, upload again.

```nu
kubectl -n exhib exec deploy/exhib -- rm -rf /data/incoming/.failed-2026-11
just upload path/to/2026-11
```

Common reasons: `date` written as a string (`"2026-11-07"`), slug with uppercase or underscores, `thumbnail` that names a file not in the upload, no supported media in the folder.

## 8. How the pipeline works (no uploader sidecar)

The uploader sidecar was a busybox container that slept. Its only job was to be an `exec` target with a writable `/data` mount (the SWS container mounts `/data` read-only). It did no conversion. Conversion, Hugo and front matter were always in the processor. PR #8 merges SWS and processor into one container, so the exec target is now that container. Nothing else moved.

The single container runs `entrypoint.py`, which starts two children and supervises them:

- `static-web-server`: serves `/data/public` on `8080`, `/livez` and `/readyz` for probes, `Cache-Control: no-cache` on all responses.
- `python3 -m processor`: the ingest loop.

If one child exits, the supervisor stops the other and exits with the same code. Kubernetes then restarts the pod.

Upload path, step by step:

1. **Transfer** (`just upload`, on your machine). Checks slug and `manifest.toml`. Refuses if `/data/incoming/<slug>` is already queued. Streams the folder as tar through `kubectl exec` into `/data/incoming/.upload-<slug>-<epoch>`. Then `mv` to `/data/incoming/<slug>`. The hidden name hides the partial copy from the processor. The `mv` is atomic, so the processor sees only complete folders.
2. **Detect** (`processor/__main__.py`). Every 3 s, takes non-hidden folders in `/data/incoming`, sorted, one at a time.
3. **Validate** (`processor/bundle.py: publish_bundle`). Slug format, `kind`, `title`, TOML datetime `date`, media list, no path escape (`../`), no existing `/data/originals/<kind>/<slug>`.
4. **Convert** (`processor/media.py`), into a scratch dir `.converted/` inside the new bundle:
    - Images: `cwebp -lossless -exact` to WebP. HEIC/HEIF decode first with `heif-convert`; AVIF via `ffmpeg`. Then `exiftool -TagsFromFile` copies all source metadata into the WebP, so Hugo can read EXIF.
    - Video: `ffmpeg` to WebM, lossless VP9 video, Opus 128k audio, metadata kept, no resize. Poster: frame at 1 s (falls back to frame 0), to lossless WebP, metadata copied.
    - Video facts: `ffprobe` (JSON) for resolution, frame rate, duration. Falls back to parsing the `ffmpeg -i` banner. Format is fixed `WebM · VP9`.
5. **Front matter** (`build_front_matter`). Writes `_index.md` (collection) or `index.md` (piece) in `/data/content/<section>/<slug>/`. TOML `+++` block: `title`, `date` (normalized to UTC offset), optional `description`, `tags`, `thumbnail` (mapped to the converted file; a video maps to its poster). One `[[resources]]` per output file with `params.weight` and `params.kind`. Videos also get `format`, `resolution`, `framerate`, `duration`, `poster`. Each poster is its own resource with `role = "poster"`, so templates hide it from the grid.
6. **Keep original.** Copies the upload folder to `/data/originals/<kind>/.<slug>.pending`.
7. **Build** (`build_and_publish`). `hugo --source /app --contentDir /data/content --destination /data/.public-next --minify`. Templates come from the image; content from the PVC. Hugo reads EXIF from the WebP files at build time for the metadata list and ordering.
8. **Swap.** Renames `public` to `.public-previous`, `.public-next` to `public`, deletes the old one. SWS never serves a half-written site. On a failed rename it restores the old one.
9. **Commit.** Renames the pending original to `/data/originals/<kind>/<slug>` and deletes the inbox folder.

Any error in steps 3 to 8 removes the bundle and pending original and parks the upload as `.failed-<slug>` (§7).

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
weight = 1
kind = "image"

[[resources]]
src = "IMG_4003.webm"
title = "IMG 4003"
[resources.params]
weight = 2
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
weight = 2
kind = "image"
role = "poster"
+++
```

## 9. Release code changes

Templates, CSS, JS, processor, `sws.toml`, `Dockerfile`: commit, then push a `v*` tag. CI publishes `ghcr.io/bfeitknecht/exhib:latest` and `:<tag>`. Keel sees the new digest and restarts the pod. On boot the processor rebuilds `/data/public` with the new templates. Content on the PVC is untouched.

### Rollout of PR #8 (one-time)

PR #8 changes the image entrypoint to run SWS too. Production infra still runs 3 containers (`sws`, `uploader`, `processor`). Order matters:

1. Merge PR #8, tag exhib. Keel rolls the `processor` container to the new image. Its SWS cannot bind `8080` (the `sws` container holds it), so the supervisor exits and `processor` crash-loops. The `sws` container keeps serving the old site. Uploads stop.
2. Tag infra with the single-container Deployment right after: one `exhib` container, port `8080`, probes `/readyz` and `/livez`, memory limit from the old processor (`2Gi`), `/data` mounted read-write. Delete `sws.toml`, the `exhib-sws` `configMapGenerator`, the `sws-config` volume and the `uploader` container.

Do not tag infra first. The old image does not run SWS, so the site would go down.

Between step 1 and 2, `just upload` also fails. `kubectl exec` without `-c` targets the first container, `sws`, which mounts `/data` read-only.

## 10. Known gaps

- Uploaded videos get no animated `preview` WebP. Grid tiles fall back to an autoplaying `<video>`. The placeholder previews were made by hand.
- No upload path for writings; they use `kubectl cp` and no backup covers them (§5).
- No in-place update of an uploaded item; delete and re-upload (§6).
- No k8up Schedule for exhib. `/data/originals` holds the only copy of uploaded originals.
