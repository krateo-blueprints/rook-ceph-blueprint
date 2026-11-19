---
type: API
title: rook-ceph-blueprint API
description: The kinds core-provider generates from the two charts.
resource: rook-ceph
tags:
  - krateo
  - blueprint
  - rook
  - ceph
  - api

timestamp: 2026-11-19T00:00:00+00:00
---
# API

core-provider generates one kind per CompositionDefinition, from the chart name:

| Chart | Kind | Served at |
|---|---|---|
| rook-operator | `RookOperator` | `composition.krateo.io/v<X-Y-Z>` |
| rook-ceph-cluster | `RookCephCluster` | `composition.krateo.io/v<X-Y-Z>` |

`<X-Y-Z>` is this repository's release version, dots replaced by dashes. Each Composition's `spec` is the chart's
values, typed by its `values.schema.json`.
