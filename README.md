# rook-ceph-blueprint

## What is this

Krateo blueprints for [Rook](https://github.com/rook/rook) **v1.21.2** and a Ceph cluster for OpenStack, as two
Compositions:

- **rook-operator**: Rook's CRDs and operator, from Rook's release manifests (`deploy/examples/crds.yaml`,
  `common.yaml`, `operator.yaml` at the tag), vendored unchanged and rendered with a short, gated list of changes.
- **rook-ceph-cluster**: only Rook custom resources. A CephCluster, one CephBlockPool per pool, one CephClient per
  OpenStack consumer with the Ceph documentation's caps, and the read grant that
  [krateo-openstack-blueprint](https://github.com/krateo-blueprints/krateo-openstack-blueprint) needs to copy the
  client keys Rook mints. No Job, no script.

They are published to `oci://ghcr.io/krateo-blueprints/charts/rook-operator` and `.../rook-ceph-cluster` on the
**blueprints** channel. krateo-openstack-blueprint consumes the cluster with `storage.backend: ceph-rook` (#308).

## Install

1. Register both CompositionDefinitions in `rook-ceph`.
2. Apply the operator, then the cluster ([examples/basic](examples/basic)). The cluster refuses to render until Rook's
   CRDs and per-cluster RBAC exist, and then renders on the next reconcile.
3. Point the Openstack Composition at it: `storage.backend: ceph-rook`, `storage.ceph.sourceNamespace: rook-ceph`.

See [docs/usage.md](docs/usage.md).

## Configure

- **rook-operator:** `image`, `logLevel`, `resources`, `nodeSelector`, `tolerations`.
- **rook-ceph-cluster:**
  - `osd.source`: `devices`, with a node label and a device filter, or `storageClass`, with a name, count and size;
  - `mon`, `mgr`, `placement`, `pools`, `replication`, `clients`;
  - `consumer`: the Openstack namespace and its copy store's ServiceAccount;
  - `testOnly`.

Every input is generic: nothing names a cloud provider. See [docs/configuration.md](docs/configuration.md).

## What rook-operator changes about upstream

- No Namespace object; every `namespace: rook-ceph` field becomes the release's namespace.
- `helm.sh/resource-policy: keep` on every CRD, so removing the release never deletes them, nor the CephCluster and
  its data they hold.
- **No CSI.** OpenStack reaches Ceph with librbd, never with Kubernetes volumes, so
  `ROOK_CREATE_CSI_OPERATOR_RESOURCES` is `"false"` and the ceph-csi-operator objects are not rendered.
- `ROOK_LOG_LEVEL`, and the operator's image, pull policy, resources, nodeSelector and added tolerations, come from
  values.

## Versioning

- Both charts share the repository's version, stamped from the tag. `appVersion` is the Rook release, pinned in
  `hack/upstream.yaml`: the newest Rook release at least two weeks old when the pin was written, with the command and
  date recorded there.
- The kinds are `RookOperator` and `RookCephCluster`, at `composition.krateo.io/v<X-Y-Z>`. (Not `CephCluster`, which
  would collide with Rook's own kind in `kubectl get`.)

## Examples

[examples/basic](examples/basic): the operator, and a cluster on raw NVMe devices for an OpenStack install in
`openstack`.

## Docs

[docs/index.md](docs/index.md), [overview](docs/overview.md), [usage](docs/usage.md),
[configuration](docs/configuration.md), [api](docs/api.md), [examples](docs/examples.md),
[release](docs/release.md), [log](docs/log.md).

## Develop & release

The gates are in `.github/workflows/lint.yaml`:
- the vendored files, `--live` against the tag;
- the versions;
- the render, derived independently;
- the OpenStack contract, `--live`;
- **admission:** a kind API server with Rook's CRDs, with negative controls;
- the release wiring;
- block-style YAML.

Release and pre-release are described in [docs/release.md](docs/release.md).
