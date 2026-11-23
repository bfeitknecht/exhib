# exhib

A chronological Hugo gallery for standalone pieces, collections and writings. The site is static. It uses custom templates and CSS-only viewers (`:target` overlays). The only JavaScript is a small (~20-line) keyboard-navigation script on collection pages (arrow keys move between items, Escape closes the viewer). There is no Hugo theme, no gallery admin UI and no remote image service. Hugo configuration is `hugo.toml`. Content front matter is TOML (`+++`) throughout.

The design language is the site's original one, kept intact: Helvetica Neue (system stack) for prose and UI, Commit Mono (self-hosted) for navigation, dates and metadata, system light/dark scheme. Colors use OKLCH with zero chroma (neutral colors only). The light and dark schemes switch via `prefers-color-scheme`.

## Quick orientation

| View              | Route / action         | Main template                      | What it controls                                                                                                                                                     |
| ----------------- | ---------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Home / top level  | `/`                    | `layouts/index.html`               | Tagline, Apex/sitemap/feed links, feed of cards, newest first                                                                                                        |
| Collections index | `/collections/`        | `layouts/collections/section.html` | Collection archive/list                                                                                                                                              |
| Pieces index      | `/pieces/`             | `layouts/pieces/section.html`      | List of standalone pieces, newest first                                                                                                                              |
| Collection        | `/collections/<slug>/` | `layouts/collections/section.html` | Title/date/description, 1:√2 image/video grid, CSS `:target` details with close and `<< n/m >>` (and arrow/Escape) navigation                                        |
| Writings index    | `/writings/`           | `layouts/writings/section.html`    | List of writings, newest first                                                                                                                                       |
| Tags (cloud)      | `/tags/`               | `layouts/taxonomy.html`   | All tags sized by usage; the global nav's `/tags/` entry                                                                                                           |
| Tag (filter)      | `/tags/<tag>/`         | `layouts/term.html`       | Pieces, collections and writings carrying the tag, newest first; text cards: title, date, description, tags                                                                  |
| Writing           | `/writings/<slug>/`    | `layouts/writings/single.html`     | Title/date/description and a markdown body in a verse measure; no media, no metadata                                                                                 |
| Standalone piece  | `/pieces/<slug>/`      | `layouts/pieces/single.html`       | Title/date/description and the first media item as stage artwork (`.piece-flow`), no metadata; clicking opens a fullscreen detail with metadata and no previous/next |

The shared document shell is in `layouts/_default/baseof.html`. Every page carries the global bar: `0xbf.ch` on the left; `/`, `/collections/`, `/pieces/`, `/writings/` and `/tags/` on the right. The feeds and sitemap live in the footer. It is styled like the page chrome (Commit Mono, muted). The current view is marked with `aria-current="page"`.

- Home-page card markup: `layouts/partials/listing/item-card.html` (writings reuse it without the image block).
- Media ordering: `layouts/partials/media/sorted-media.html`. One order for grid, overlays, piece stage and homepage mosaic: `position` by default, or capture date first with `sort = "date"` (images and videos mixed; generated posters excluded).
- Fullscreen viewer body: `layouts/partials/media/media-detail.html`.
- Shared media slice (ordering, overlay ids, aspect ratios): `layouts/partials/media/media-view.html`.
- Home/feed entry list: `layouts/partials/listing/feed-entries.html`.
- Automatic image metadata: `layouts/partials/metadata/metadata-list.html`.

`static/css/site.css` controls fonts, colors, spacing, responsive layout, preview sizes and viewer sizing. `layouts/_default/baseof.html` inlines it into every page (`readFile`), so styles exist at first paint and links never flash in the browser default color. The file is not linked or served separately.

### Images load in steps

The processor writes small lossy WebP copies next to each lossless master when it converts an upload (`processor/variants.py`): `<stem>.<hash>.w480|w960|w1920|w2880.webp` plus a 24 px blur `<stem>.<hash>.w24.webp`. `<hash>` is the first 8 hex digits of the master's SHA-256. `layouts/partials/media/img.html` renders them as one `<img>` with a `srcset`, `sizes`, width and height (no layout shift) and the blur inlined as its CSS background. The browser fetches the smallest copy that is sharp enough for the slot and the screen density. The fullscreen viewer also lists the lossless master as the largest candidate. The copies are not media: `sorted-media.html` skips them by name. Images with no copies (SVG, the repo placeholders) fall back to a Hugo resize. No JavaScript is involved.

Caching (`sws.toml`): pages, masters and videos revalidate (`no-cache`, 304). Copies and Hugo resizes carry a content hash in their name, so they are `immutable` for one year. The build writes a `.gz` beside each HTML/XML/SVG file and SWS serves it (`compression-static`).

### Styling knobs

- **System light/dark colors:** CSS variables `--bg`, `--fg` and `--muted` near the top of `static/css/site.css`. `prefers-color-scheme` switches between them.
- **Typography:** `--sans` is "Helvetica Neue", Helvetica, Arial, system-ui. It is used for prose and UI. `--mono` is Commit Mono (self-hosted from `static/fonts/`; license in `OFL-CommitMono.txt`; checksums in `SHA256SUMS`). It is used for navigation, dates and metadata, matching the original design.
- **OKLCH neutrals:** `--bg`/`--fg`/`--muted` use `oklch()` with chroma 0. Light: `oklch(96% 0 0)` paper (≈`#f2f2f2`), `oklch(21% 0 0)` ink (≈`#181818`), `oklch(47% 0 0)` muted (≈`#5b5b5b`). Dark: `oklch(17% 0 0)` (≈`#0f0f0f`), `oklch(95% 0 0)` (≈`#eeeeee`), `oklch(70% 0 0)` (≈`#9e9e9e`). This palette was chosen in the thyme design session. Keep chroma at 0. Emphasis comes from weight, size and letter-spacing, not color. The `theme-color` metas and the favicon use the hex approximations.
- **Top-level card density:** `.timeline`, `.item-card` and `.item-preview`. The responsive timeline columns and the maximum card width decide how many cards fit per screen.
- **Preview artwork:** `.item-preview`, `.preview-grid` and `.preview-grid a`. A selected collection thumbnail uses the single-image route. Otherwise the template places up to nine resource images in a landscape mosaic. Each mosaic cell links to the fullscreen overlay for that image (`#photo-NN`; images occupy photo-01..photo-N because videos come after the images). Clicking a tile opens the viewer at that image. Empty areas use the site background. There are no placeholder cells.
- **Collection page grid:** `.collection-grid` and `.collection-photo`. Tiles use the site-wide 1:√2 (`1.41421356 / 1`) aspect ratio. There are no 1:1 squares.
- **Fullscreen details:** `.photo-viewer`, `.viewer-unit`, `.viewer-image`, `.viewer-nav`, `.close-detail` and `.metadata-list`. Image dimensions are read from the resource itself (bitmap dimensions or an SVG `viewBox`), so the full image scales to the viewport. You do not need to duplicate dimensions in TOML.
- **Motion:** pure CSS. Cropped tiles (`.item-preview`, `.preview-grid` cells, `.collection-photo`) and card titles (`.item-copy h2 a`, scale anchored left) ease to 1.03 on hover/focus over .7 s. Only the hovered mosaic tile zooms. Chrome links fade in color over .25 s. The fullscreen `:target` viewer opens instantly; there are no overlay transitions. No loops, no scroll effects. Everything is disabled under `prefers-reduced-motion`.
- **Keyboard navigation:** `static/js/viewer-keys.js` (~20 lines, served `no-cache`). The left and right arrow keys move between open overlays. Escape closes back to the grid on collection pages. The script acts only while a `#photo-*` overlay is open. It clamps at the ends, like the disabled `<<` and `>>` controls. This is the only JavaScript on the site.

## Tags

Pieces, collections and writings carry an optional list of tags in front matter, e.g. `tags = ["evergrowing"]` for monthly snapshot collections or `["design"]` for posters. Uploads pass them in the manifest: `tags = ["evergrowing"]`. Hugo generates `/tags/` — a cloud with one sized entry per tag — and `/tags/<tag>/`, which lists the tagged items with the usual item cards, newest first. Tag chips render on the homepage feed, the archive lists, the per-tag pages and the page intros, and are clickable everywhere. Feeds carry the tags as `<category>` entries. Tag slugs are urlized, so use lowercase slug-like names (`evergrowing`, `design`, `essay`).

## Content model and TOML examples

Use Hugo page bundles so each page and its local artwork stay together. New collections and pieces should use real dates. The home feed sorts entries newest first.

### Standalone piece

Create `content/pieces/<slug>/index.md` plus the media file beside it. The template uses the first ordered media item (image or video) as the artwork. Video pieces show their poster.

```toml
+++
title = "Evening study"
date = 2026-11-01T00:00:00Z
description = "A short note about this work."

[[resources]]
src = "evening-study.jpg"
title = "Evening study"
+++
```

Clicking the image opens a fullscreen `:target` detail. `X` closes back to the standalone page. There is no previous/next navigation on standalone pages.

### Writings

On the live site, publish writings with `just upload` (`kind = "writing"`, see [docs/manual.md](docs/manual.md) §5). In the repo, create `content/writings/<slug>/index.md`. Writings are text only. There is no media, no grid and no metadata. The body is markdown. A single newline breaks the line; a blank line separates paragraphs and stanzas. This suits verse. Descriptions are optional.

```toml
+++
title = "Field notes"
date = 2026-11-08T12:00:00Z
description = "Optional summary. *Markdown* is supported."
+++

First line
Second line

A new stanza.
```

The home feed shows writings without an image: title, date and description. `/writings/` lists all writings. Writings appear in the home feed and in the RSS and Atom feeds.

Descriptions are rendered as markdown wherever they appear on the page (page intros, cards). In the `<meta name="description">` tag and in the RSS and Atom feeds they are flattened to plain text.

### Collection

Create `content/collections/<slug>/_index.md` and place the image files in the same directory. A selected thumbnail is optional. Without one, the home card uses a mosaic.

```toml
+++
title = "Evening walks"
date = 2026-11-01T00:00:00Z
description = "A short description of the collection."
thumbnail = "cover.jpg" # omit or set to "" for the mosaic

[[resources]]
src = "cover.jpg"
title = "Evening light"
[resources.params]
position = 1 # display-order fallback only; not image metadata

[[resources]]
src = "street.jpg"
title = "Street after rain"
[resources.params]
position = 2
+++
```

`thumbnail` is only a presentation setting. The selected image stays in the collection grid. Items appear in `position` order, images and videos mixed. With `sort = "date"` in front matter, items with a capture date (image EXIF, video creation date) come first, oldest first, then the rest by `position`. Videos use their generated poster as the grid tile and as the detail poster. The poster is not listed as a gallery item. `title` is the human caption and alt text. It is not a substitute for EXIF.

### Resource metadata is automatic

Do **not** copy EXIF values into TOML. The project config enables all available fields from EXIF, IPTC and XMP:

```toml
[imaging.meta]
fields = ["**"]
sources = ["exif", "iptc", "xmp"]
```

The detail view iterates every extracted field. Aperture, exposure time, focal length, ISO, camera/lens, capture time, GPS and any other tags are read from the image file. Common rational values (f-number, exposure time, focal length) are formatted for readability. There is no `publish_gps` switch and no manual longitude/latitude entry. If the tags remain in the asset, they are eligible to display.

Hugo's metadata extractor supports AVIF, BMP, GIF, HEIC/HEIF, JPEG, PNG, TIFF and WebP. SVGs have no EXIF; their pixel or viewBox dimensions are read for layout only. Unsupported formats have no auto-extracted metadata.

**Privacy rule:** all extracted fields are publish-by-default. If a field must not be public, strip it from the input asset before upload or build. For uploaded items, the site serves the generated WebP derivative; the source stays private. For assets added directly to the Hugo content tree, the original asset is served. Hiding a value in the HTML does not remove it from the served file. Inspect with ExifTool and strip only the unwanted fields from the upload copy, then verify:

```sh
exiftool -G1 -a -s photo.jpg                     # inspect all metadata groups
exiftool -GPS:all= -overwrite_original photo.jpg  # remove EXIF GPS from this copy
exiftool -all= -overwrite_original photo.jpg      # remove all metadata if desired
exiftool -G1 -a -s photo.jpg                     # re-check before publishing
```

The GPS example removes the EXIF GPS group. XMP is enabled too. Inspect the XMP section and remove the matching XMP GPS tags if present. The `-all=` command removes every metadata group. Keep private originals outside the public content tree. Hugo does not sanitize embedded metadata. It reads the metadata for the HTML and copies the image resource to the output.

## Image sources and attribution

All artwork is local to this repository. The templates do not fetch images from another service.

- `content/collections/placeholders/` holds the assistant-created placeholder artwork: the cover, the studies, the standalone-piece, the card previews and the generated test-pattern clips and calibration charts.

## Build and local preview

Use Hugo Extended (validated with v0.169.0):

```sh
hugo --minify
hugo server --bind 0.0.0.0 --port 4173
```

Hugo writes static output to `public/`. The home page links to Apex (`https://0xbf.ch/`), `/sitemap.xml`, `/rss.xml` and `/atom.xml`. The two feeds are generated by `layouts/index.rss.xml` and `layouts/index.atom.xml` from the shared `layouts/partials/listing/feed-entries.html` list. Section and page RSS output are disabled. Only the home page publishes feeds. `hugo.toml` also enables `/robots.txt` (`User-agent: *`).

## Self-hosting: SWS + media processor on Talos

The public site is served by **Static Web Server (SWS)**. The exhib pod is a **single container** from `ghcr.io/bfeitknecht/exhib:latest` — the same image serves HTTP and ingests uploads, like the other tier-2 apps. `uv run python entrypoint.py` (Python 3.15, uv project at the repo root) starts `static-web-server` (SWS) and `python -m processor` side by side and supervises them: if either exits, the other is stopped and the container exits with the same code, so Kubernetes restarts the pod instead of leaving a half-dead gallery. A third child, the gallery editor (`python -m uploader` on 8081, `glry.0xbf.ch/upload` behind authentik), is the `just manifest` editor on the PVC: drafts in `/data/drafts`, publish replaces an item, dropped files go to `/data/trash` ([docs/manual.md](docs/manual.md) §1.1). `just upload` still works through `kubectl exec`.

- **SWS** serves `/data/public`. Its configuration (`sws.toml`, in this repo) is baked into the image at `/etc/sws/sws.toml`; the infra repo carries no `sws.toml`, no ConfigMap and no volume. All responses are `no-cache`; clients revalidate with Last-Modified and unchanged files are answered 304. No served file has a content hash in its name, so no `immutable` rule is used — that would pin stale bytes in returning browsers. SWS provides `/health` for the probes.
- **Processor** watches `/data/incoming`. It converts media, writes Hugo page bundles into `/data/content`, keeps uploaded originals privately in `/data/originals` and rebuilds the public output. It shares the container with SWS, so an image rebuild is required when the site, the processor, the SWS base version, `sws.toml` or dependencies change. New gallery items do not need an image rebuild or push. The ingest code is a small package (`processor/`, run as `python -m processor`): `paths` (environment-derived locations), `media` (FFmpeg, cwebp and exiftool conversion), `bundle` (manifest validation, page bundles, atomic site rebuild), `__main__` (the poll loop).

The PVC request is 50 GiB. This gives room for both retained originals and generated output. The PVC is pinned to the cluster's `local-path` StorageClass (like the other app PVCs). Adjust the capacity for your library. `/data/originals` holds the only copies of uploaded originals. Tier-2 apps carry no k8up schedule. Whether exhib warrants one is open. Treat the PVC as the only backup until this is resolved.

The manifests live in `bfeitknecht/infra` under `kubernetes/applications/exhib/` (the tier-2 layout used by apex and glob): namespace, PVC (`local-path`), a single-container Deployment (probes on `/health`, `fsGroup: 1000`), Service and HTTPRoute for `glry.0xbf.ch` (matching `baseURL` here), and the owner-created `ghcr.sops.yaml` GHCR pull secret referenced by the Kustomization. A generic busybox initContainer creates the data directories on the PVC. Infra carries no application configuration — no ConfigMap, no `sws.toml`, no environment beyond what the image sets. The Flux Kustomization lives in that repo's `kubernetes/cluster/applications.yaml` (`dependsOn: storage, traefik`, sops decryption). Keel keeps the `:latest` image digest in motion. The infra repo is the single source of truth for cluster state. The reusable GitHub workflow builds the root `Dockerfile` and publishes `ghcr.io/bfeitknecht/exhib` (`:latest` + `:<tag>`) on `v*` tags and on manual dispatch — one image is the whole app and its release, like glob. Content uploads never require an image build. Only template, processor, serving or dependency changes do; re-tag this repo for those.

### Upload a collection, piece or writing

The full guide is [docs/manual.md](docs/manual.md). Make a folder whose name is a lowercase slug. Put the source media files in it (or one `.md` body for a writing). Run `just manifest path/to/folder` for a local browser editor that writes `manifest.toml` (`tools/manifest/`, a separate uv project that runs only on your machine). The smallest working manifest:

```toml
kind = "collection" # or "piece" or "writing"
title = "Evening walks"
date = 2026-11-07T18:30:00Z
```

The folder name becomes the URL slug. Every supported media file in the folder is included automatically, in numeric-aware filename order, titled after the filename (`01-paper-light.jpg` → “Paper light”). Still images with an EXIF capture date are shown oldest first; the rest follow in filename order. Per-file `[[media]]` tables (`file`, optional `title`, optional `caption`, optional `position`) are only needed to override those defaults — `title` falls back to the filename, `caption` (markdown) is shown under the title in the fullscreen info panel, and `position` to the list index. It was called `weight`, then `order`; manifests with either are rejected. `thumbnail_focus = [x, y]` (percent) crops the cover on the card. Optional extras in the manifest: `description` and `thumbnail` (the name of one media file; without it, the feed card uses a mosaic of the first items).

With [`just`](https://just.systems) installed and `kubectl` configured for the Talos cluster, run:

```sh
just upload path/to/my-new-collection
```

The `upload` recipe in the `justfile` streams the complete folder to a temporary directory on the PVC. It then moves the folder into the processor inbox. The processor detects the new folder, converts the media, generates the Hugo bundle and rebuilds the gallery. If a build or a conversion fails, the processor logs the error and keeps the upload under a hidden `.failed-*` name in the inbox for inspection. Originals are kept under `/data/originals/` after processing.

Still images in JPEG, PNG, WebP, AVIF, TIFF, HEIC or HEIF are converted to **lossless WebP** (`cwebp -lossless -exact`). EXIF/IPTC/XMP is copied from the source into the WebP, so Hugo can publish all image metadata automatically. Videos in MOV/MP4/M4V/3GP/MKV/WebM are converted to WebM with **quality-targeted VP9** (CRF 32; lossless turned a 10 MB phone clip into 550 MB) and an Opus 128k audio track. The long side is capped at 1920 px and never upscaled. 10-bit HLG sources stay 10-bit, so HDR clips keep their look. Only the first audio track is kept; phone clips carry extra audio-typed metadata streams with no decoder. A lossless WebP poster is generated for each video. The site uses native HTML `<video controls>`. Each video is probed (ffprobe, falling back to ffmpeg's input banner); resolution, frame rate and duration are written into the generated page bundle alongside the fixed `WebM · VP9` format. Image metadata publishing stays automatic and publish-by-default, including GPS. Strip anything you do not want public from the source asset before upload. Lossless conversion keeps the decoded pixels, but the files can be larger than the iPhone's HEIC/HEVC originals. The originals remain privately stored on the PVC.

The processor writes one generated Hugo page bundle per upload. For a collection, each included file becomes one item in the grid and in the CSS-only detail navigation. For a standalone piece, the first ordered media item is shown; videos open in the same closeable detail overlay. There is no JavaScript admin UI and no network upload service.

Hugo configuration, SWS configuration, manifests and generated page front matter use TOML. Kubernetes resources stay YAML, as required by Kubernetes/Kustomize. The pod runs one image, built from this repo; the infra repo only references it. It needs rebuilding when templates, conversion logic, the SWS base version, `sws.toml` or dependencies change. It does not need rebuilding when content changes.
