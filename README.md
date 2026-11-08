# exhib

A chronological Hugo gallery for standalone pieces and collections. It is a static site with custom templates and CSS-only viewers: no JavaScript, no theme dependency, no gallery admin, and no remote image service. Hugo configuration is `hugo.toml`; content front matter is TOML (`+++`) throughout.

The design language matches [blog.0xbf.ch](https://blog.0xbf.ch): STIX Two Text for prose and headings, Commit Mono for navigation, dates and metadata, warm paper background (`#f4f3ef`) with a near-black ink foreground, switching to a dark scheme via `prefers-color-scheme`.

## Quick orientation

| View | Route / action | Main template | What it controls |
|---|---|---|---|
| Home / top level | `/` | `layouts/index.html` | Intro/tagline, Apex/sitemap/feed links, newest-first feed of collection and standalone cards |
| Collections index | `/collections/` | `layouts/collections/section.html` | Collection archive/list |
| Collection | `/collections/<slug>/` | `layouts/collections/section.html` | Title/date/description, square image/video grid, CSS `:target` details with close and `<< n/m >>` navigation |
| Standalone piece | `/pieces/<slug>/` | `layouts/pieces/single.html` | Title/date/description and first media item; clicking it opens a fullscreen detail with no prev/next |

The shared document shell and feed discovery links are in `layouts/_default/baseof.html`. The home-page card markup is `layouts/partials/item-card.html`; collection image ordering is in `layouts/partials/sorted-images.html` (date-stamped images first, then `weight` order; generated video posters are excluded); combined image/video ordering is in `layouts/partials/sorted-media.html`; the fullscreen detail body is `layouts/partials/media-detail.html`; the home/feed entry list is `layouts/partials/feed-entries.html`; automatic image metadata is formatted in `layouts/partials/metadata-list.html`. `assets/css/site.css` controls fonts, colors, spacing, responsive layout, preview sizes, and viewer sizing; it is minified and content-hashed by Hugo (with an SRI `integrity` attribute), so it can be cached immutably — there is no manual `?v=` to bump.

### Styling knobs

- **System light/dark colors:** CSS variables `--bg`, `--fg`, and `--muted` near the top of `assets/css/site.css`, with `prefers-color-scheme` handling.
- **Typography:** CSS variables `--serif` (STIX Two Text, Georgia fallback) for prose/headings and `--mono` (Commit Mono) for navigation, dates and metadata. Both are self-hosted from `static/fonts/`; licenses and checksums live beside them (`OFL-STIXTwo.txt`, `OFL-CommitMono.txt`, `SHA256SUMS`).
- **Top-level card density:** `.timeline`, `.item-card`, and `.item-preview`. The responsive timeline columns and maximum card width affect how many collections/pieces fit per screen.
- **Preview artwork:** `.item-preview`, `.preview-grid`, and `.preview-grid span`. A selected collection thumbnail uses the single-image route; otherwise the template lays up to nine actual resource images into a landscape mosaic. Empty areas use the site background, with no placeholder cells.
- **Collection page grid:** `.collection-grid` and `.collection-photo`.
- **Fullscreen details:** `.photo-viewer`, `.viewer-unit`, `.viewer-image`, `.viewer-nav`, `.close-detail`, and `.metadata-list`. Image dimensions are derived from the resource itself (bitmap dimensions or an SVG `viewBox`) so the whole image can scale to the available viewport without manually duplicating dimensions in TOML.

## Content model and TOML examples

Use Hugo page bundles so each page and its local artwork stay together. New collections and pieces should use real dates; the home feed sorts entries newest first.

### Standalone piece

Create `content/pieces/<slug>/index.md` plus the media file beside it. The template uses the first ordered media item (image or video) as the artwork; video pieces show their poster.

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

The `/..` link is in the page flow and scrolls away with the title. Clicking the image opens a fullscreen `:target` detail; `X` closes back to the standalone page. There is no standalone previous/next navigation.

### Collection

Create `content/collections/<slug>/_index.md` and place the image files in the same directory. A selected thumbnail is optional. Without one, the home card uses a grid mosaic.

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

`thumbnail` is only a presentation choice. The selected image remains in the collection grid. When embedded capture dates exist, image order is taken from the image metadata; images with no capture date follow in `weight` order; videos follow in `weight` order after the images. Videos use their generated poster as the grid tile and detail poster; the poster itself is not listed as a gallery item. `title` is the human caption/alt text; it is not a substitute for EXIF.

### Resource metadata is automatic

Do **not** copy EXIF values into TOML. The project config enables all available fields from EXIF, IPTC, and XMP:

```toml
[imaging.meta]
fields = ["**"]
sources = ["exif", "iptc", "xmp"]
```

The detail view iterates every extracted field. Aperture, exposure time, focal length, ISO, camera/lens, capture time, GPS, and any other available tags are read from the image file. Common rational values (f-number, exposure time, focal length) are formatted for readability. There is no `publish_gps` switch and no manual longitude/latitude entry: if the tags remain in the asset, they are eligible to display.

Hugo's metadata extractor supports AVIF, BMP, GIF, HEIC/HEIF, JPEG, PNG, TIFF, and WebP. SVGs have no EXIF; their pixel/viewBox dimensions are read for layout only. Unsupported formats will not have auto-extracted metadata.

**Privacy rule:** all extracted fields are intentionally publish-by-default. If a field should not be public, strip it from the input asset before upload/build. For uploaded items, the generated WebP derivative is what the site serves; the source is retained privately. For assets added directly to the Hugo content tree, the original asset is served. Hiding a value in the HTML alone does not remove it from the served file. Inspect with ExifTool and strip only the unwanted fields from the upload copy, then verify:

```sh
exiftool -G1 -a -s photo.jpg                     # inspect all metadata groups
exiftool -GPS:all= -overwrite_original photo.jpg  # remove EXIF GPS from this copy
exiftool -all= -overwrite_original photo.jpg      # remove all metadata if desired
exiftool -G1 -a -s photo.jpg                     # re-check before publishing
```

The GPS example targets the EXIF GPS group; because XMP is enabled too, inspect the XMP section and remove corresponding XMP GPS tags if present. The `-all=` command removes every metadata group. Keep private originals outside the public content tree. Hugo does not sanitize embedded metadata; it reads it for the HTML and copies the image resource to the output.

## Image sources and attribution

All artwork is local to this repository; the templates do not fetch images from another service.

- `content/collections/2026-10/` contains the eight October field-note SVGs preserved from the earlier exhib project. They remain credited to the assistant as requested.
- `content/collections/placeholders/` contains the assistant-created cover and study SVGs, plus a copy of the standalone placeholder illustration.
- `content/pieces/placeholder-study/placeholder.svg` is also retained inside its piece bundle so that the standalone demo is self-contained. It is the same placeholder art as the copy in the Placeholders collection.

## Build and local preview

Use Hugo Extended (validated with v0.169.0):

```sh
hugo --minify
hugo server --bind 0.0.0.0 --port 4173
```

Hugo writes static output to `public/`. The home page links to Apex (`https://0xbf.ch/`), `/sitemap.xml`, `/rss.xml`, and `/atom.xml`; the two feeds are generated by `layouts/index.rss.xml` and `layouts/index.atom.xml` from the shared `layouts/partials/feed-entries.html` list. Section/page RSS output is disabled; only the home page publishes feeds. `hugo.toml` also enables `/robots.txt` (`User-agent: *`).

## Self-hosting: SWS + media processor on Talos

The public site is served by **Static Web Server (SWS)**, not Caddy. The exhib pod now has three containers sharing one PVC:

- **SWS** serves `/data/public` and mounts the PVC read-only. Cache headers come from `infra/exhib/sws.toml`: `no-cache` everywhere (revalidation via Last-Modified → 304), `public, max-age=31536000, immutable` for the content-hashed `css/**` and the self-hosted `fonts/**`.
- **Uploader** is a quiet BusyBox container with no listener and no SSH. Uploads are sent through the Kubernetes API (`kubectl exec`), not through a public admin endpoint.
- **Processor** watches `/data/incoming`, converts media, writes Hugo page bundles into `/data/content`, preserves uploaded originals privately in `/data/originals`, and rebuilds the public output. It contains Hugo, FFmpeg and metadata tools. Its image is built when the site/processor code changes; new gallery items do not require an image rebuild or push.

The PVC request is 50 GiB to allow room for both retained originals and generated output. It omits `storageClassName` and therefore uses the cluster default; set it explicitly in `infra/exhib/pvc.yaml` if required. Adjust capacity for your library and Talos storage setup.

`infra/exhib/` contains the app manifests and SWS TOML config, following the `glob/infra` layout. Copy that directory to `kubernetes/applications/exhib/` in `bfeitknecht/infra`, then append `infra/applications-entry.yaml` to `kubernetes/cluster/applications.yaml`. The route is `gallery.0xbf.ch`, matching `baseURL` in `hugo.toml`. The reusable GitHub workflow (`.github/workflows/publish-image.yaml`, calling `bfeitknecht/infra/.github/workflows/publish-image.yaml@master`) builds the root `Dockerfile` to `ghcr.io/bfeitknecht/exhib` on `v*` tags; make the GHCR package public or configure an image pull secret before deploying.

### Shortlist: going live on `bfeitknecht/infra`

One-time steps to gallery.0xbf.ch, mirroring the glob/blog rollout:

1. **Tag and publish the image** — `git tag -a v0.1.0 -m "exhib v0.1.0" && git push origin v0.1.0`. The reusable workflow builds `ghcr.io/bfeitknecht/exhib` (multi-arch). Watch it with `gh run watch` or on the Actions tab.
2. **Registry visibility** — either make the `exhib` GHCR package public (org/user → Packages → exhib → Package settings → Change visibility), **or** mirror the blog's private pull: create `kubernetes/applications/exhib/ghcr.sops.yaml` from apex's (`sops -d kubernetes/applications/apex/ghcr.sops.yaml | sed 's/namespace: apex/namespace: exhib/' | sops -e > kubernetes/applications/exhib/ghcr.sops.yaml`), add it to `infra/exhib/kustomization.yaml`, and add a `serviceaccount.yaml` (default SA with `imagePullSecrets: [{name: dockerconfigjson}]`, like `infra/glob/serviceaccount.yaml`). As shipped, the deployment pulls `:latest` anonymously and expects a public package.
3. **Copy the manifests** — `cp -r infra/exhib <infra-clone>/kubernetes/applications/exhib`.
4. **Append the Flux entry** — append `infra/applications-entry.yaml` to `kubernetes/cluster/applications.yaml` (declares the `exhib` Kustomization: dependsOn `traefik`, sops decryption, and the Keel `ignore:` on the processor image path `/spec/template/spec/containers/2/image`).
5. **Storage class** — confirm the Talos cluster's default StorageClass suits the 50 GiB PVC in `infra/exhib/pvc.yaml`; set `storageClassName` explicitly if not. Wildcard DNS/TLS for `*.0xbf.ch` already covers `gallery.0xbf.ch` (same as glob/blog).
6. **Push and watch Flux** — in `bfeitknecht/infra`: commit, push; then `flux reconcile kustomization exhib` (optional) and `flux get kustomizations -n flux-system exhib`; `kubectl -n exhib get pods,pvc`.
7. **Check the first boot** — `kubectl -n exhib logs -f deploy/exhib -c processor`. On an empty PVC it seeds the repo's demo gallery into `/data/content` and builds `/data/public`; then it idles, polling `/data/incoming` every 3 s (`EXHIB_POLL_SECONDS` overrides).
8. **Verify the site** — `curl -I https://gallery.0xbf.ch/` (200), probes on `/health`, `/rss.xml` + `/atom.xml` + `/sitemap.xml`, dark/light rendering, and one fullscreen detail overlay.
9. **Upload something real** — `./scripts/upload-item.sh /path/to/package`; watch the processor log; confirm the bundle in `/data/content/`, originals in `/data/originals/`, and new card on the home page.
10. **Privacy pass first** — for camera files with GPS, strip before upload (`exiftool -GPS:all= ...`). The lossless-WebP derivative carries source metadata by design; there is no publish-time scrubbing step.
11. **Housekeeping** — replace or remove the demo collections (`content/collections/2026-10`, `content/collections/placeholders`) and the placeholder piece once real content exists. Note the seed only applies to an empty `/data/content`; deleting bundles later means removing them on the PVC (or `kubectl -n exhib exec deploy/exhib -c processor -- rm -rf /data/content/pieces/placeholder-study` followed by a processor restart).
12. **Keel caveat** — the `keel.sh/*` annotations on the Deployment and the `ignore:` block in the applications entry only matter if the cluster runs Keel; delete both otherwise. Either way, `kubectl -n exhib rollout restart deploy/exhib` re-pulls `:latest`.

### Upload a piece or collection

Make a folder whose name is a lowercase slug. Put `manifest.toml` and all source media files in it. The manifest has `kind = "piece"` or `kind = "collection"`, plus `title`, a TOML `date`, optional `description`, optional `thumbnail`, and one `[[media]]` table per file (`file`, optional `title`, optional `weight`). See `examples/upload-package/manifest.toml` for the schema.

With `kubectl` configured for the Talos cluster, run:

```sh
./scripts/upload-item.sh path/to/my-new-collection
```

The script streams the complete folder to a temporary directory on the PVC, then moves it into the processor inbox. The processor detects it, converts the media, generates the Hugo bundle and rebuilds the gallery automatically. A build/conversion failure is logged by the processor and the upload is retained under a hidden `.failed-*` inbox name for inspection; originals are kept under `/data/originals/` after processing.

Still images in JPEG, PNG, WebP, AVIF, TIFF, HEIC or HEIF are converted to **lossless WebP** (`cwebp -lossless -exact`). EXIF/IPTC/XMP is copied from the source into the WebP so Hugo can publish all available image metadata automatically. Videos in MOV/MP4/M4V/3GP/MKV/WebM are converted to WebM with **lossless VP9 video** and an Opus audio track; Opus audio is lossy because WebM's normal audio codec is not lossless. No video resizing is applied. A lossless WebP poster is generated for each video. The generated site uses native HTML `<video controls>`. Video metadata is passed through FFmpeg where supported; image metadata publishing remains automatic and publish-by-default, including GPS. Strip anything you do not want public from the source asset before upload. Lossless conversion preserves decoded pixels but may produce larger files than the iPhone's HEIC/HEVC originals; the originals remain privately stored on the PVC.

The processor writes one generated Hugo page bundle per upload. For a collection, each `[[media]]` entry becomes one item in the grid and CSS-only detail navigation. For a standalone piece, the first ordered media item is shown, with videos opened in the same closeable detail overlay. No JavaScript admin UI or network upload service is exposed.

Hugo configuration, SWS configuration, manifests and generated page front matter use TOML. Kubernetes resources remain YAML, as required by Kubernetes/Kustomize. The serving image is still the upstream SWS image; the processor image only needs rebuilding when templates, conversion logic or dependencies change—not when gallery content changes.

