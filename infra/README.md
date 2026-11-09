# infra/ — staging for the exhib go-live

This directory is **not part of the running repository**. It holds the exact
files and edits needed to land exhib on `bfeitknecht/infra`, staged so the
go-live requires no improvisation. **Delete this whole directory as the last
step of the go-live** (see "Delete the staging directory" below).

`infra/kubernetes/**` mirrors the target layout of `bfeitknecht/infra`
(upstream master `4e7c2e1da0b443ca8975c3a31bcc055502c3ee10`, 2026-11-08;
re-verified byte-identical on 2026-11-09 — see gate G0). Paths and filenames
below are repo-relative to that repo's root.

Everything needed for the go-live is in this directory plus this exhib repo
(Dockerfile, publish-image workflow, `scripts/upload-item.sh`, `examples/`).
No other context is required.

## Order of operations (TL;DR)

1. Gates G0–G3 below.
2. Publish the image (`git tag v0.1.0 && git push origin v0.1.0` on the exhib
   repo) — multi-arch `linux/amd64,arm64`, pushes
   `ghcr.io/bfeitknecht/exhib:latest` and `:v0.1.0`.
3. Copy the exhib manifests; bring in `kubernetes/cluster/applications.yaml`.
4. `kubectl kustomize kubernetes/applications/exhib` — must render cleanly.
5. Commit + tag `bfeitknecht/infra`; CI publishes the OCI artifact; Flux
   reconciles. Never `kubectl apply`.
6. Verify (commands and expected output below).
7. Delete this `infra/` directory from the exhib repo and commit.

## Gates (owner decisions and checks before anything is copied)

**G0 — Upstream drift.** Everything before the trailing `exhib` Kustomization
in `infra/kubernetes/cluster/applications.yaml` must equal upstream
`bfeitknecht/infra` `master` verbatim (diffed clean both when staged and again
on 2026-11-09). If `master` moved: append the trailing block to the new
upstream file by hand instead of copying staging's version. Keep every
existing block untouched and in place — glob and apex are being onboarded in
the same wave and share this file. The result must contain each of
`dns, agh, homepage, ddns, apex, forgejo, pds, atuin, devil, glob, exhib`
exactly once.

**G1 — exhib `master` contains this change.** The image that goes live must
be built from an exhib `master` that includes the 2026-11-09 go-live review
fixes (XML escaping in the RSS/Atom feeds; nothing in this staging directory
substitutes for tagging the right commit). Tag only after that has merged.

**G2 — Demo content.** The image seeds the demo gallery
(`content/collections/2026-10`, `content/collections/placeholders`,
`content/pieces/placeholder-study`) into an empty `/data/content` on first
boot. Pick one, **before the tag**:

- Ship the demo (fine as a placeholder): nothing to do.
- Ship empty: `git rm -r content/collections/2026-10 content/collections/placeholders content/pieces`
  on exhib `master`, commit, then tag. The PVC starts empty; the first real
  upload through the processor is the first content.
  Note: removing demo content also empties the in-repo gallery build that
  future image builds seed from; that is intended.

**G3 — SOPS pull secret (owner action — agents may not create/read SOPS
files).** The exhib Kustomization decrypts with `sops-age` and
`applications/exhib/kustomization.yaml` lists `ghcr.sops.yaml`, which
intentionally does not exist in staging. The owner creates it exactly like
glob's:

```sh
sops -d kubernetes/applications/glob/ghcr.sops.yaml \
  | sed 's/namespace: glob/namespace: exhib/' \
  | sops -e > kubernetes/applications/exhib/ghcr.sops.yaml
```

If the file is missing or undecryptable, the exhib Kustomization fails its
dry-run and nothing of it applies. If the owner prefers a **public GHCR
package** instead (apex/glob are private + Keel by convention, so the sops
route is preferred): before copying, delete the `ghcr.sops.yaml` line from
`kustomization.yaml`'s resources, delete `imagePullSecrets` from
`deployment.yaml` (pod template), and delete `serviceaccount.yaml` (it only
re-points the default SA at a `dockerconfigjson` secret that would not
exist).

## Preconditions

- Owner available for G1–G3 and for the SOPS step. `kubectl` configured
  against the production cluster; `flux` CLI optional but handy.
- `bfeitknecht/infra` clone, on `master`, clean.
- The exhib image published (step 2) **before** the infra change is applied —
  otherwise the pod sits in `ImagePullBackOff` until the tag exists.

## Integration steps (agent or owner)

1. Re-check gate G0; then `cp -a infra/kubernetes/applications/exhib <infra>/kubernetes/applications/`.
2. Bring `kubernetes/cluster/applications.yaml` over as staged (or
   hand-applied per G0).
3. `kubectl kustomize kubernetes/applications/exhib` — **must** render
   Namespace, PVC, Deployment (3 containers; Keel annotation on the pod's
   `ghcr.io/bfeitknecht/exhib:latest` container, `containers[2]`;
   `imagePullSecrets: [dockerconfigjson]`), Service, HTTPRoute,
   ServiceAccount and the `exhib-sws` ConfigMap. Requires the
   `ghcr.sops.yaml` from G3 (or its public-package alternative) to exist.
   `kubectl kustomize kubernetes/cluster` is not required — the cluster
   directory is consumed by the root Kustomization.
4. Commit and push; tag `vX.Y.Z` on the infra repo; CI publishes the OCI
   artifact; Flux reconciles (`OCIRepository` tracks `semver >=1.0.0`).
   Never `kubectl apply`.
5. Verify:

   ```sh
   flux get kustomizations -n flux-system exhib   # Ready: True, applied revision = new tag
   kubectl -n exhib get pods,pvc                  # pod 1/1 ready (3 containers), PVC Bound
   kubectl -n exhib logs deploy/exhib -c processor | tail
   # First boot: "Published/seeded…" build output, then a clean hugo build into /data/.public-next
   curl -fsS https://gallery.0xbf.ch/ -o /tmp/exhib.html && grep -o '<title>[^<]*</title>' /tmp/exhib.html
   curl -fsS https://gallery.0xbf.ch/rss.xml  | python3 -c 'import sys,xml.etree.ElementTree as ET; ET.parse(sys.stdin)'
   curl -fsS https://gallery.0xbf.ch/atom.xml | python3 -c 'import sys,xml.etree.ElementTree as ET; ET.parse(sys.stdin)'
   curl -fsS -o /dev/null -w '%{http_code}\n' https://gallery.0xbf.ch/sitemap.xml
   curl -fsS https://gallery.0xbf.ch/readyz     # text/plain "OK" (public, harmless)
   ```

6. Optional end-to-end upload round-trip (proves the whole pipeline, not just
   static serving): from an exhib checkout, make a small package —
   `mkdir -p /tmp/first-photo && cp some.jpg /tmp/first-photo/ && cat > /tmp/first-photo/manifest.toml`
   (copy `examples/upload-package/manifest.toml`, fix `file =`), then
   `scripts/upload-item.sh /tmp/first-photo`; watch
   `kubectl -n exhib logs deploy/exhib -c processor` for the transcode + Hugo
   rebuild, and `curl -fsS https://gallery.0xbf.ch/` to see the new item.

## Rollback

- **Bad image / template bug:** the preferred fix is a revert/fix forward in
  the exhib repo + `git tag v0.1.1 && git push origin v0.1.1`. Keel
  (`poll`/`force`) re-pulls the digest; no infra change needed. To freeze
  rollouts temporarily: `kubectl -n exhib annotate deploy/exhib keel.sh/enabled=false`
  (owner) and remove the annotation afterwards.
- **Undo the app entirely:** revert the go-live commit in `bfeitknecht/infra`
  and `flux reconcile ks flux-system`. The Kustomization object disappears
  with the next reconcile, but **resources are not garbage-collected by a
  missing entry** — the app keeps running until torn down. Tear-down deletes
  the `exhib` namespace, which **destroys the PVC and every original in
  `/data/originals`** — only do it intentionally, after copying originals off
  (`kubectl -n exhib exec <pod> -c uploader -- tar -C /data -cf - originals`
  > `originals-backup.tar`). Owner decision; there is no k8up backup (see
  "Backup" below).
- **Bad manifests (before Flux applies):** nothing applied — fix and push;
  the failing Kustomization never half-applies (dry-run gate via `wait: true`
  and `prune: true`).

## Failure triage

| Symptom | Likely cause | Fix |
|---|---|---|
| `flux get ks exhib` not Ready, dry-run error mentions decryption | `ghcr.sops.yaml` missing/undecryptable, or `sops-age` secret absent in `flux-system` | G3 |
| Pod `ImagePullBackOff` | image not published yet, or `dockerconfigjson` secret missing/invalid | publish the tag; check `kubectl -n exhib get secret dockerconfigjson` (values never printed) |
| Pod `0/1 Ready`, no container crash | Probe path wrong or SWS health off | this staging has `/readyz` + `health = true` in `sws.toml` — keep them; SWS has **no** `/health` endpoint |
| SWS serves an image-listing or the SWS placeholder page instead of the gallery | `root` dropped from `sws.toml` (SWS defaults root to `.`, i.e. the image's own home) | restore `[general] root = "/data/public"` in `sws.toml` |
| PVC `Pending` | `storage` Kustomization not applied, or node lacks capacity | `flux get ks storage`; exhib `dependsOn` includes `storage` — do not remove it |
| Processor `CrashLoopBackOff` | invalid upload in `/data/incoming`, Hugo build error | processor logs show the exact failure; offending packages are moved to `/data/incoming/.failed-<slug>` and left for inspection |
| Upload accepted but gallery unchanged | process runs but build failed, or SWS caches aggressively | check processor logs; `Cache-Control: no-cache` on HTML is intentional so content updates appear immediately |

## Notes for the go-live

- **Keel (tier-2)**: `deployment.yaml` carries `keel.sh/trigger: poll`,
  `policy: force`, `match-tag: "true"` and `imagePullPolicy: Always` on the
  processor only; SWS and the uploader stay pinned. Flux ignores
  `/spec/template/spec/containers/2/image` (index 2 = the processor;
  apex/glob use 0 because they are single-container). Do not add Keel
  annotations to Tier 1/3 workloads.
- **Processor root fs**: intentionally not `readOnlyRootFilesystem` — the
  Hugo build writes `.hugo_build.lock` and `resources/_gen` under `/app`.
  SWS and the uploader are read-only.
- **Image pull on every pod**: the `dockerconfigjson` secret must exist in
  namespace `exhib` (it is namespace-scoped); the pod template lists
  `imagePullSecrets` again because Keel resolves registry credentials from
  the workload only, never from the SA.
- **`storageClassName: local-path`** is set explicitly and the Flux
  Kustomization `dependsOn: storage` (the local-path provisioner) — same as
  agh/forgejo/pds/atuin. A PVC cannot bind before the provisioner exists.
- **Pod security**: `fsGroup: 1000` + `OnRootMismatch` gives uid 1000 write
  access to the PVC; the initContainer creates `/data/{public,incoming,
  content,originals}`; SWS mounts the same PVC read-only.
- **SWS health gotcha (fixed in this staging)**: SWS exposes `/livez` and
  `/readyz`, and they are **off by default**. Enabling them requires
  `health = true` in the `[general]` table of `sws.toml`. Probes on `/health`
  answer 404 forever — that was the state before the 2026-11-09 review; the
  staged files are consistent with each other (`sws.toml` `root` + `health`,
  probes on `/readyz`/`/livez`). Do not "clean up" one without the others.
- **SWS root gotcha (fixed in this staging)**: SWS `root` defaults to `.`
  (its working directory, i.e. the image home, not the PVC). `/data/public`
  is set in `sws.toml`; without it the gallery never appears.
- **Backup**: `/data/originals` holds the only copies of uploaded originals.
  Tier-2 apps carry no k8up schedule; atuin/forgejo (tier-1) get one via
  `backup-schedule.yaml`. Decide at go-live whether exhib originals warrant
  the same (owner decision — would add `backup-schedule.yaml` + credential
  wiring; not included here on purpose). If the answer is no, consider
  copying `/data/originals` off the node periodically instead.
- **`exhib` vs `glob` publication cadence**: the site is rebuilt in-cluster
  from uploads; image rebuilds only ship templates/processor changes. A new
  image is just `git tag vX.Y.Z` on the exhib repo.
- **Demo content** is covered by gate G2.
- **Feeds**: RSS (`/rss.xml`, pinned `baseName = "rss"`) and Atom
  (`/atom.xml`) exist on the home output; titles/descriptions are XML-escaped
  as of the 2026-11-09 review.
- **Keyboard viewer**: collection pages ship one tiny JS file
  (`js/viewer-keys.js`) for arrow-key/Esc in the photo viewer; everything else
  is CSS-only. It is served under the default `no-cache` header — only
  `css/**` and `fonts/**` are immutable.

## Delete the staging directory (part of the go-live)

Once the infra PR is merged and the site is verified:

```sh
git rm -r infra
git commit -m "chore: drop infra staging (go-live complete)"
```

Removing it keeps the exhib repo free of duplicated manifests; the infra repo
is the single source of truth afterwards. Do this **after** verification, not
before — it is the only copy of these staged files.

## What the 2026-11-09 review changed in this staging

For the reconciling agent and for the record (exhib PR #2):

1. `sws.toml`: added `[general] root = "/data/public"` (was missing — SWS
   would have served the image home) and `health = true` (SWS health
   endpoints are off by default).
2. `deployment.yaml`: probes `/health` → `/readyz` (readiness) and `/livez`
   (liveness). SWS answers `/health` with 404, so the pod would never have
   become Ready.
3. `cluster/applications.yaml`: exhib `dependsOn` now includes `storage`
   (the local-path provisioner), matching agh/forgejo/pds/atuin; exhib has a
   PVC and cannot bind without it. Upstream prefix re-verified verbatim
   against master on 2026-11-09.
4. exhib repo: RSS/Atom templates now XML-escape titles/descriptions (raw
   `&`/`<` produced invalid feeds otherwise).
5. Confirmed the publish workflow builds `linux/amd64,arm64` and pushes
   `:latest` + `:<tag>`; exhib and infra repos are public, so the reusable
   workflow call from the exhib repo works as written.
