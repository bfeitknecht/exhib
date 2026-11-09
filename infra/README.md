# infra/ — staging for the exhib go-live

This directory is **not part of the running repository**. It holds the exact
files and edits needed to land exhib on `bfeitknecht/infra`, staged so the
go-live requires no improvisation. **Delete this whole directory as part of
the go-live** (see "Remove the staging directory" below).

Everything in `infra/kubernetes/**` mirrors the target layout of
`bfeitknecht/infra` (master @ `4e7c2e1da0b443ca8975c3a31bcc055502c3ee10`,
2026-11-08). Paths and filenames below are repo-relative to that repo's root.

## What lands where

| Staging file | Destination in `bfeitknecht/infra` | Action |
|---|---|---|
| `infra/kubernetes/applications/exhib/**` | `kubernetes/applications/exhib/` | copy as-is (create dir; see ghcr.sops.yaml step) |
| `infra/kubernetes/cluster/applications.yaml` | `kubernetes/cluster/applications.yaml` | **replace** — it is upstream master verbatim plus the `exhib` Kustomization appended at EOF |

Nothing else changes in `bfeitknecht/infra`. No DNS or certificate work is
needed: `wildcard-domain-tls` on `traefik-gateway` (`websecure`) and the
`*.0xbf.ch` wildcard already cover `gallery.0xbf.ch`.

## Preconditions (owner actions — agents may not do these)

1. **SOPS**: `applications.yaml` gives the exhib Kustomization
   `decryption: { provider: sops, secretRef: { name: sops-age } }` and
   `applications/exhib/kustomization.yaml` lists `ghcr.sops.yaml`. The file is
   intentionally absent — it holds the `dockerconfigjson` GHCR pull secret and
   must be created by the owner, exactly like glob:

   ```sh
   sops -d kubernetes/applications/glob/ghcr.sops.yaml \
     | sed 's/namespace: glob/namespace: exhib/' \
     | sops -e > kubernetes/applications/exhib/ghcr.sops.yaml
   ```

   Flux then decrypts it in-cluster with `sops-age` (`flux-system`). If the
   file is missing or undecryptable, the exhib Kustomization fails its dry-run
   and nothing of it applies. Agents: never read, decrypt, edit or create SOPS
   files; ask the owner to run the snippet.

   **Alternative (owner decision)**: make the `exhib` GHCR package public and
   skip the secret entirely. Then, before copying: delete
   `kubernetes/applications/exhib/ghcr.sops.yaml` from the kustomization
   resources list, delete `imagePullSecrets` from `deployment.yaml` (both the
   pod template entry); keep or delete `serviceaccount.yaml` freely (it only
   re-points the default SA at a non-existent secret — drop it too if going
   public). Tier-2 apps on `bfeitknecht/infra` are private-GHCR + Keel by
   convention (apex, glob); prefer the sops route unless the owner says
   otherwise.

2. **Publish the image from the exhib repo**: tag `v0.1.0`
   (`git tag -a v0.1.0 -m "exhib v0.1.0" && git push origin v0.1.0`). The
   `Publish Image` workflow calls `bfeitknecht/infra/.github/workflows/publish-image.yaml@master`
   and pushes `ghcr.io/bfeitknecht/exhib`. Until that first tag is published,
   the Deployment references a nonexistent image.

## Integration steps (agent or owner)

1. Verify `infra/kubernetes/cluster/applications.yaml` in this staging area
   still applies cleanly: everything before the last `---` must equal upstream
   `master` verbatim (it was diffed clean when staged). If `master` moved
   since `4e7c2e1`, re-apply by hand: append the trailing `exhib` Kustomization
   block to the new upstream file. Keep every existing block untouched — glob
   and apex are being onboarded in the same wave and share this file; the
   result must contain all of `dns, agh, homepage, ddns, apex, forgejo, pds,
   atuin, devil, glob, exhib`, each exactly once.
2. `cp -a infra/kubernetes/applications/exhib /path/to/infra-clone/kubernetes/applications/exhib`
3. Copy staging's `applications.yaml` to `kubernetes/cluster/applications.yaml`
   (or hand-applied per step 1).
4. Validate before tagging (per `AGENTS.md`):
   `kubectl kustomize kubernetes/applications/exhib` — must render Namespace,
   PVC, Deployment (3 containers, Keel annotations on the pod's
   `ghcr.io/bfeitknecht/exhib:latest` container = `containers[2]`, with
   `imagePullSecrets: [dockerconfigjson]`), Service, HTTPRoute, ServiceAccount
   and the `exhib-sws` ConfigMap; requires the ghcr.sops.yaml to exist.
   `kubectl kustomize kubernetes/cluster` is not required — the cluster
   directory is consumed by the root Kustomization.
5. Commit, push, tag `vX.Y.Z` in `bfeitknecht/infra`; CI publishes the OCI
   artifact; Flux reconciles (OCIRepository tracks `semver >=1.0.0`). Never
   `kubectl apply`.
6. Verify: `flux get kustomizations -n flux-system exhib`;
   `kubectl -n exhib get pods,pvc` (PVC binds via `local-path` on `rbpi`);
   `kubectl -n exhib logs -f deploy/exhib -c processor` (first boot seeds the
   demo gallery into `/data/content` and builds `/data/public`);
   `curl -fsS https://gallery.0xbf.ch/` (200), plus `/rss.xml`, `/atom.xml`,
   `/sitemap.xml`; probes already cover `/health`.

## Delete the staging directory (part of the go-live)

Once the infra PR is merged and the site is verified:

```sh
git rm -r infra
git commit -m "chore: drop infra staging (go-live complete)"
```

Removing it keeps the exhib repo free of duplicated manifests; the infra repo
is the single source of truth afterwards.

## Notes for the go-live

- **Keel (tier-2)**: `deployment.yaml` carries `keel.sh/trigger: poll`,
  `policy: force`, `match-tag: "true"` and `imagePullPolicy: Always` on the
  processor only; SWS and the uploader stay pinned. `applications.yaml` grants
  the `ignore:` on `/spec/template/spec/containers/2/image` (index 2 = the
  processor; apex/glob use 0 because they are single-container). Without that
  ignore, Flux drift correction reverts Keel's digest updates and the two
  fight over the field. Do not add Keel annotations to Tier 1/3 workloads.
- **Processor root fs**: the processor is intentionally not
  `readOnlyRootFilesystem` — the Hugo build writes `.hugo_build.lock` and
  `resources/_gen` under `/app`. SWS and the uploader are read-only.
- **Image pull on every pod**: the `dockerconfigjson` secret must exist in
  namespace `exhib` (it is namespace-scoped); the pod template lists
  `imagePullSecrets` again because Keel resolves registry credentials from the
  workload only, never from the SA.
- **storageClassName: `local-path`** is set explicitly (matches atuin /
  agh / forgejo); the cluster does not rely on a default StorageClass.
- **Backup**: `/data/originals` holds the only copies of uploaded originals.
  Tier-2 apps carry no k8up schedule; atuin/forgejo (tier-1) get one via
  `backup-schedule.yaml`. Decide at go-live whether exhib originals warrant
  the same (owner decision — adds a `backup-schedule.yaml` + credential wiring,
  not included here on purpose).
- **Demo content**: the PVC seeds the in-repo demo gallery on first boot
  (`content/collections/2026-10`, `placeholders`, `pieces/placeholder-study`).
  Remove those directories from the exhib repo before the first real upload if
  the demo should not ship.
- **`exhib` vs `glob` publication cadence**: the site content is rebuilt
  in-cluster from uploads; image rebuilds only ship templates/processor
  changes. Publishing a new image is `git tag v0.x.y` on the exhib repo.
