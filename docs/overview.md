---
type: Architecture
title: rook-ceph-blueprint architecture
description: Why the operator is vendored and the cluster is CRs only, what each chart renders, and the contract with the OpenStack blueprint.
resource: rook-ceph
tags:
  - krateo
  - blueprint
  - rook
  - ceph
  - architecture

timestamp: 2026-11-19T00:00:00+00:00
---
# Architecture

## rook-operator: Rook's release manifests, vendored

Rook publishes no release assets. Its install manifests are files in its tree at each tag. `hack/upstream.yaml` pins
the tag, each file's path and its SHA-256. `hack/validate-vendored.py --live` compares each file with
`raw.githubusercontent.com/rook/rook/<tag>/<path>`.

The changes are applied at render time, in `templates/manifests.yaml`:
- no Namespace object, and the namespace fields rewritten;
- keep on every CRD;
- CSI off;
- the operator's image and placement from values.

`hack/validate-render.py` applies the same changes to the vendored files itself and compares the render object for
object.

## rook-ceph-cluster: custom resources only

- **A CephCluster.** Its OSDs come from raw block devices on labelled nodes (`useAllNodes`, `deviceFilter`, and the
  osd and prepareosd placements requiring the label), or from block-mode claims of a StorageClass. It has 3 mons, 2
  mgrs and Rook-managed PodDisruptionBudgets.
- **One CephBlockPool per enabled pool:** `spec.name` is the Ceph name, so dotted names such as `cinder.volumes` work.
  Size 3 on failure domain host by default.
- **One CephClient per consumer**, with the caps the Ceph documentation gives OpenStack ("Block Devices and
  OpenStack"):
  - `client.cinder`: `profile rbd` on volumes (and vms), `profile rbd-read-only` on images;
  - `client.glance`: `profile rbd` on images.

  No osd or mgr cap is a bare `profile rbd`. Rook writes each key to Secret `rook-ceph-client-<name>`, key `userKey`.
- **A Role and RoleBinding** granting the OpenStack install's copy store ServiceAccount `get` on exactly those Secrets
  and `rook-ceph-config` (`mon_host`), plus the SelfSubjectRulesReview ESO validates with.

The cluster must be in the operator's namespace: Rook's per-cluster RBAC (common.yaml) is rendered there.

## The contract with krateo-openstack-blueprint

`hack/openstack-contract.yaml` records what that umbrella reads, at a commit: pool and client names, Rook's Secret
names and keys, and the copy store's ServiceAccount. `hack/validate-consumer-contract.py` checks this chart's defaults
against it, and `--live` checks the record against the umbrella's main.

## Preconditions refused, not documented

On a live cluster (core-provider's CRD present), rook-ceph-cluster refuses while:
- Rook's CRDs are not served;
- the namespace has no `rook-ceph-osd` ServiceAccount.

Each refusal is on the Composition's status. It also refuses values that cannot make a working cluster: no consumer,
no OSD source, size or mon count below 3 without `testOnly`, an even mon count, no pool.

## Admission

`hack/validate-admission.py` (CI job `admission`) applies Rook's CRDs to a kind API server and dry-runs every rendered
object server-side. Three broken objects must be refused.
