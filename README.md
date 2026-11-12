# exhib

A chronological Hugo gallery for standalone pieces, collections and writings. The site is static. It uses custom templates and CSS-only viewers (`:target` overlays). The only JavaScript is a small (~20-line) keyboard-navigation script on collection pages (arrow keys move between items, Escape closes the viewer). There is no Hugo theme, no gallery admin UI and no remote image service. Hugo configuration is `hugo.toml`. Content front matter is TOML (`+++`) throughout.

The design language is the site's original one, kept intact: Helvetica Neue (system stack) for prose and UI, Commit Mono (self-hosted) for navigation, dates and metadata, system light/dark scheme. Colors use OKLCH with zero chroma (neutral colors only). The light and dark schemes switch via `prefers-color-scheme`.

## Quick orientation

| View | Route / action | Main template | What it controls |
|---|---|---|---|
| Home / top level | `/` | `layouts/index.html` | Tagline, Apex/sitemap/feed links, feed of cards, newest first |
| Collections index | `/collections/` | `layouts/collections/section.html` | Collection archive/list |
| Pieces index | `/pieces/` | `layouts/pieces/section.html` | List of standalone pieces, newest first |
| Collection | `/collections/<slug>/` | `layouts/collections/section.html` | Title/date/description, 1:√2 image/video grid, CSS `:target` details with close and `<< n/m >>` (and arrow/Escape) navigation |
| Writings index | `/writings/` | `layouts/writings/section.html` | List of writings, newest first |
| Writing | `/writings/<slug>/` | `layouts/writings/single.html` | Title/date/description and a markdown body in a verse measure; no media, no metadata |
| Standalone piece | `/pieces/<slug>/` | `layouts/pieces/single.html` | Title/date/description and the first media item as stage artwork (`.piece-flow`), no metadata; clicking opens a fullscreen detail with metadata and no previous/next |

The shared document shell is in `layouts/_default/baseof.html`. Every page carries the global bar: `0xbf.ch` on the left; `/`, `/collections/`, `/pieces/`, `/writings/`, `sitemap`, `rss` and `atom` on the right. It is styled like the page chrome (Commit Mono, muted). The current view is marked with `aria-current="page"`.

- Home-page card markup: `layouts/partials/listing/item-card.html` (writings reuse it without the image block).
- Collection image ordering: `layouts/partials/media/sorted-images.html` (images with an EXIF capture date first, oldest first, then `weight` order; generated video posters are excluded).
- Combined image/video ordering: `layouts/partials/media/sorted-media.html`.
- Fullscreen viewer body: `layouts/partials/media/media-detail.html`.
- Shared media slice (ordering, overlay ids, aspect ratios): `layouts/partials/media/media-view.html`.
- Home/feed entry list: `layouts/partials/listing/feed-entries.html`.
- Automatic image metadata: `layouts/partials/metadata/metadata-list.html`.

`styles/site.css` controls fonts, colors, spacing, responsive layout, preview sizes and viewer sizing. The source is mounted into Hugo's asset pipeline via `[module] mounts` in `hugo.toml`. Hugo minifies it and adds a content hash with an SRI `integrity` attribute, so the file can be cached immutably. There is no manual `?v=` to bump.

### Styling knobs

- **System light/dark colors:** CSS variables `--bg`, `--fg` and `--muted` near the top of `styles/site.css`. `prefers-color-scheme` switches between them.
- **Typography:** `--sans` is "Helvetica Neue", Helvetica, Arial, system-ui. It is used for prose and UI. `--mono` is Commit Mono (self-hosted from `static/fonts/`; license in `OFL-CommitMono.txt`; checksums in `SHA256SUMS`). It is used for navigation, dates and metadata, matching the original design.
- **OKLCH neutrals:** `--bg`/`--fg`/`--muted` use `oklch()` with chroma 0. Light: `oklch(96% 0 0)` paper (≈`#f2f2f2`), `oklch(21% 0 0)` ink (≈`#181818`), `oklch(47% 0 0)` muted (≈`#5b5b5b`). Dark: `oklch(17% 0 0)` (≈`#0f0f0f`), `oklch(95% 0 0)` (≈`#eeeeee`), `oklch(70% 0 0)` (≈`#9e9e9e`). This palette was chosen in the thyme design session. Keep chroma at 0. Emphasis comes from weight, size and letter-spacing, not color. The `theme-color` metas and the favicon use the hex approximations.
- **Top-level card density:** `.timeline`, `.item-card` and `.item-preview`. The responsive timeline columns and the maximum card width decide how many cards fit per screen.
- **Preview artwork:** `.item-preview`, `.preview-grid` and `.preview-grid a`. A selected collection thumbnail uses the single-image route. Otherwise the template places up to nine resource images in a landscape mosaic. Each mosaic cell links to the fullscreen overlay for that image (`#photo-NN`; images occupy photo-01..photo-N because videos come after the images). Clicking a tile opens the viewer at that image. Empty areas use the site background. There are no placeholder cells.
- **Collection page grid:** `.collection-grid` and `.collection-photo`. Tiles use the site-wide 1:√2 (`1.41421356 / 1`) aspect ratio. There are no 1:1 squares.
- **Fullscreen details:** `.photo-viewer`, `.viewer-unit`, `.viewer-image`, `.viewer-nav`, `.close-detail` and `.metadata-list`. Image dimensions are read from the resource itself (bitmap dimensions or an SVG `viewBox`), so the full image scales to the viewport. You do not need to duplicate dimensions in TOML.
- **Motion:** pure CSS. Cropped tiles (`.item-preview`, `.preview-grid` cells, `.collection-photo`) and card titles (`.item-copy h2 a`, scale anchored left) ease to 1.03 on hover/focus over .7 s. Only the hovered mosaic tile zooms. Chrome links fade in color over .25 s. The fullscreen `:target` viewer opens instantly; there are no overlay transitions. No loops, no scroll effects. Everything is disabled under `prefers-reduced-motion`.
- **Keyboard navigation:** `static/js/viewer-keys.js` (~20 lines, served `no-cache`). The left and right arrow keys move between open overlays. Escape closes back to the grid on collection pages. The script acts only while a `#photo-*` overlay is open. It clamps at the ends, like the disabled `<<` and `>>` controls. This is the only JavaScript on the site.

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

Create `content/writings/<slug>/index.md`. Writings are text only. There is no media, no grid and no metadata. The body is markdown. A single newline breaks the line; a blank line separates paragraphs and stanzas. This suits verse. Descriptions are optional.

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
weight = 1 # display-order fallback only; not image metadata

[[resources]]
src = "street.jpg"
title = "Street after rain"
[resources.params]
weight = 2
+++
```

`thumbnail` is only a presentation setting. The selected image stays in the collection grid. If embedded capture dates exist, image order comes from the image metadata. Images with no capture date follow in `weight` order. Videos follow in `weight` order after the images. Videos use their generated poster as the grid tile and as the detail poster. The poster is not listed as a gallery item. `title` is the human caption and alt text. It is not a substitute for EXIF.

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

The public site is served by **Static Web Server (SWS)**. The exhib pod has three containers that share one PVC:

- **SWS** serves `/data/public` and mounts the PVC read-only. Cache headers come from `sws.toml` in the infra repo's `kubernetes/applications/exhib/`: `no-cache` everywhere (revalidation via Last-Modified → 304), `public, max-age=31536000, immutable` for the content-hashed `css/**`.
- **Uploader** is a quiet BusyBox container. It has no listener and no SSH. Uploads go through the Kubernetes API (`kubectl exec`). There is no public admin endpoint.
- **Processor** watches `/data/incoming`. It converts media, writes Hugo page bundles into `/data/content`, keeps uploaded originals privately in `/data/originals` and rebuilds the public output. It contains Hugo, FFmpeg and metadata tools. The image is rebuilt when the site or the processor code changes. New gallery items do not need an image rebuild or push. The ingest code is a small package (`processor/`, run as `python -m processor`): `paths` (environment-derived locations), `media` (FFmpeg, cwebp and exiftool conversion), `bundle` (manifest validation, page bundles, atomic site rebuild), `__main__` (the poll loop).

The PVC request is 50 GiB. This gives room for both retained originals and generated output. The PVC is pinned to the cluster's `local-path` StorageClass (like the other app PVCs). Adjust the capacity for your library. `/data/originals` holds the only copies of uploaded originals. Tier-2 apps carry no k8up schedule. Whether exhib warrants one is open. Treat the PVC as the only backup until this is resolved.

The manifests live in `bfeitknecht/infra` under `kubernetes/applications/exhib/` (the tier-2 layout used by apex and glob): namespace, PVC (`local-path`), the 3-container Deployment (SWS + uploader + processor), Service and HTTPRoute for `gallery.0xbf.ch` (matching `baseURL` here), and the owner-created `ghcr.sops.yaml` GHCR pull secret referenced by the Kustomization. The Flux Kustomization lives in that repo's `kubernetes/cluster/applications.yaml` (`dependsOn: storage, traefik`, Keel `ignore` on the processor image, sops decryption). Keel keeps the `:latest` processor digest in motion. The infra repo is the single source of truth; a staging copy was used for the go-live and removed afterwards. The reusable GitHub workflow builds the root `Dockerfile` and publishes `ghcr.io/bfeitknecht/exhib` (`:latest` + `:<tag>`) on `v*` tags and on manual dispatch. Content uploads never require an image build. Only template or processor changes do; re-tag this repo for those.

### Upload a piece or collection

Make a folder whose name is a lowercase slug. Put `manifest.toml` and all source media files in it. The manifest has `kind = "piece"` or `kind = "collection"`, plus `title`, a TOML `date`, an optional `description`, an optional `thumbnail` and one `[[media]]` table per file (`file`, optional `title`, optional `weight`). See `examples/upload-package/manifest.toml` for the schema.

With [`just`](https://just.systems) installed and `kubectl` configured for the Talos cluster, run:

```sh
just upload path/to/my-new-collection
```

The `upload` recipe in the `justfile` streams the complete folder to a temporary directory on the PVC. It then moves the folder into the processor inbox. The processor detects the new folder, converts the media, generates the Hugo bundle and rebuilds the gallery. If a build or a conversion fails, the processor logs the error and keeps the upload under a hidden `.failed-*` name in the inbox for inspection. Originals are kept under `/data/originals/` after processing.

Still images in JPEG, PNG, WebP, AVIF, TIFF, HEIC or HEIF are converted to **lossless WebP** (`cwebp -lossless -exact`). EXIF/IPTC/XMP is copied from the source into the WebP, so Hugo can publish all image metadata automatically. Videos in MOV/MP4/M4V/3GP/MKV/WebM are converted to WebM with **lossless VP9 video** and an Opus audio track. Opus audio is lossy, because lossless audio in WebM is not common. No video resizing is applied. A lossless WebP poster is generated for each video. The site uses native HTML `<video controls>`. Video metadata is passed through FFmpeg where supported. Image metadata publishing stays automatic and publish-by-default, including GPS. Strip anything you do not want public from the source asset before upload. Lossless conversion keeps the decoded pixels, but the files can be larger than the iPhone's HEIC/HEVC originals. The originals remain privately stored on the PVC.

The processor writes one generated Hugo page bundle per upload. For a collection, each `[[media]]` entry becomes one item in the grid and in the CSS-only detail navigation. For a standalone piece, the first ordered media item is shown; videos open in the same closeable detail overlay. There is no JavaScript admin UI and no network upload service.

Hugo configuration, SWS configuration, manifests and generated page front matter use TOML. Kubernetes resources stay YAML, as required by Kubernetes/Kustomize. The serving image is the upstream SWS image. The processor image only needs rebuilding when templates, conversion logic or dependencies change. It does not need rebuilding when content changes.
