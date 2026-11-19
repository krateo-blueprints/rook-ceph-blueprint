#!/usr/bin/env python3
"""Every place that names a version agrees with hack/upstream.yaml and with the release tag.

    hack/validate-version-mirror.py [repo-root]

Versioning here (docs/release.md): both charts carry the repository's one version, stamped from the git tag
(CHART_VERSION), and each chart's appVersion is the Rook release it is written against. Checked:
  1. Both Chart.yaml: version is the CHART_VERSION placeholder; appVersion is the Rook tag without its "v"; sources list
     this repository first and rook/rook. rook-operator's krateo.io/upstream annotation names that repository and tag.
  2. Both compositiondefinition.yaml: install oci://ghcr.io/krateo-blueprints/charts/<chart> at CHART_VERSION.
  3. rook-operator's values.yaml: image.repository and image.tag are the recorded image at the tag.
  4. rook-ceph-cluster's cluster.yaml refuses without exactly the Rook CRDs its objects are (CephCluster, CephBlockPool,
     CephClient), and every one of them is in rook-operator's vendored crds.yaml.
  5. examples/basic: one Composition per chart, all at the same composition.krateo.io/v<X-Y-Z>, each of the kind
     core-provider generates from the chart name. hack/release-preflight refuses a tag other than that version.

Fails when PyYAML is missing and when hack/upstream.yaml lists nothing.
"""
import glob
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
REPO = "https://github.com/krateo-blueprints/rook-ceph-blueprint"
CHARTS = ["rook-ceph-cluster", "rook-operator"]


def measurement_failed(msg):
    print("FAILED MEASUREMENT: " + msg)
    sys.exit(2)


try:
    import yaml
except ImportError:
    measurement_failed("PyYAML unavailable, so nothing was read")

entries = (yaml.safe_load(open(os.path.join(ROOT, "hack", "upstream.yaml"))) or {}).get("upstreams") or []
if not entries:
    measurement_failed("hack/upstream.yaml lists no upstream, so nothing was checked")
failures = []
tags = {(e["repo"], e["tag"]) for e in entries}
if len(tags) != 1:
    failures.append("hack/upstream.yaml pins %s; every vendored file is from one Rook release" % sorted(tags))
repo, tag = sorted(tags)[0]
ver = tag.lstrip("v")
img = [e for e in entries if e.get("image")]


def kind_of(chart):
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[-_]", chart))


charts = sorted(os.path.basename(os.path.dirname(os.path.dirname(p)))
                for p in glob.glob(os.path.join(ROOT, "blueprints", "*", "chart", "Chart.yaml")))
if charts != CHARTS:
    failures.append("blueprints/ holds %s, want %s" % (charts, CHARTS))
if sorted({e["chart"] for e in entries}) != ["rook-operator"]:
    failures.append("hack/upstream.yaml vendors into %s, want rook-operator only" % sorted({e["chart"] for e in entries}))

for c in CHARTS:
    d = os.path.join(ROOT, "blueprints", c, "chart")
    cy = yaml.safe_load(open(os.path.join(d, "Chart.yaml")))
    if cy.get("version") != "CHART_VERSION":
        failures.append("%s: Chart.yaml version is %r, not the CHART_VERSION placeholder the tag stamps" % (c, cy.get("version")))
    if str(cy.get("appVersion")) != ver:
        failures.append("%s: appVersion %r, the pinned Rook release is %s" % (c, cy.get("appVersion"), ver))
    if (cy.get("sources") or [])[:2] != [REPO, "https://github.com/" + repo]:
        failures.append("%s: sources %s, want [%s, https://github.com/%s]" % (c, cy.get("sources"), REPO, repo))
    cd = yaml.safe_load(open(os.path.join(ROOT, "blueprints", c, "compositiondefinition.yaml")))
    spec = (cd.get("spec") or {}).get("chart") or {}
    if spec.get("url") != "oci://ghcr.io/krateo-blueprints/charts/" + c or spec.get("version") != "CHART_VERSION":
        failures.append("%s: its CompositionDefinition installs %s %s" % (c, spec.get("url"), spec.get("version")))

ro = yaml.safe_load(open(os.path.join(ROOT, "blueprints", "rook-operator", "chart", "Chart.yaml")))
if (ro.get("annotations") or {}).get("krateo.io/upstream") != "%s %s" % (repo, tag):
    failures.append("rook-operator: annotation krateo.io/upstream is %r, want %r"
                    % ((ro.get("annotations") or {}).get("krateo.io/upstream"), "%s %s" % (repo, tag)))
v = yaml.safe_load(open(os.path.join(ROOT, "blueprints", "rook-operator", "chart", "values.yaml")))
vi = v.get("image") or {}
if len(img) != 1 or vi.get("repository") != img[0]["image"] or str(vi.get("tag")) != tag:
    failures.append("rook-operator: values image %s:%s, upstream deploys %s:%s"
                    % (vi.get("repository"), vi.get("tag"), img[0]["image"] if img else "?", tag))

tpl = open(os.path.join(ROOT, "blueprints", "rook-ceph-cluster", "chart", "templates", "cluster.yaml")).read()
m = re.search(r'include "ceph\.preconditions\.require" \(list \$ \(list ([^)]*)\)', tpl)
got = re.findall(r'"([^"]+)"', m.group(1)) if m else None
want = ["cephclusters.ceph.rook.io", "cephblockpools.ceph.rook.io", "cephclients.ceph.rook.io"]
if got != want:
    failures.append("rook-ceph-cluster: cluster.yaml requires %s, want %s (the kinds it renders)" % (got, want))
crds = {d["metadata"]["name"] for d in yaml.safe_load_all(open(os.path.join(
    ROOT, "blueprints", "rook-operator", "chart", "files", "upstream", "crds.yaml"))) if d}
for n in want:
    if n not in crds:
        failures.append("rook-ceph-cluster requires %s, which rook-operator's vendored crds.yaml does not define" % n)

versions = {}
for p in sorted(glob.glob(os.path.join(ROOT, "examples", "basic", "*.yaml"))):
    for doc in yaml.safe_load_all(open(p)):
        if doc and str(doc.get("apiVersion", "")).startswith("composition.krateo.io/"):
            versions.setdefault(doc["kind"], []).append(doc["apiVersion"])
want_kinds = sorted(kind_of(c) for c in CHARTS)
if sorted(versions) != want_kinds or any(len(x) != 1 for x in versions.values()):
    failures.append("examples/basic holds Compositions %s, want exactly one each of %s" % (versions, want_kinds))
served = {x[0] for x in versions.values()}
if len(served) > 1:
    failures.append("examples/basic names more than one version: %s. Both charts share one version." % sorted(served))
for s in served:
    if not re.fullmatch(r"composition\.krateo\.io/v\d+-\d+-\d+", s):
        failures.append("examples/basic: apiVersion %s is not composition.krateo.io/v<X-Y-Z>" % s)

if failures:
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("OK: both charts at Rook %s %s; examples at %s" % (repo, tag, ", ".join(sorted(served))))
