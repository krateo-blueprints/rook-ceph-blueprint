#!/usr/bin/env python3
"""A real API server admits every object both charts render, and refuses a broken one.

    hack/validate-admission.py [repo-root]

The offline gates (hack/validate-render.py) render the charts and check this repository's predicates. Only an API
server can say whether Rook's CustomResourceDefinitions admit what they render: krateo-openstack-blueprint's H2 run met a
custom resource every offline gate passed and the API server refused (its #393). So this:
  1. starts a kind cluster with its own kubeconfig (never the caller's current context);
  2. renders rook-operator in namespace rook-ceph and APPLIES its CustomResourceDefinitions (server-side), then dry-runs
     every other object it renders server-side (`kubectl apply --dry-run=server`);
  3. renders rook-ceph-cluster in the same namespace in each shape the charts support (raw devices, a StorageClass,
     testOnly with every pool on) and dry-runs every object server-side: each must be admitted;
  4. NEGATIVE CONTROLS, so an admission that admits anything cannot pass: a CephBlockPool whose replicated.size is a
     string, a CephCluster whose storageClassDeviceSets count is a string, and a CephClient whose caps are a list must
     each be refused, naming the field;
  5. deletes the cluster.
What the API server enforces here is each CRD's structural schema (types, enums, required fields), as on a real
cluster. Rook v1.21 runs no admission webhook, so there is nothing further to install. Fails when kind, kubectl or helm
is missing, and when the cluster cannot be created.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
NS = "rook-ceph"
CLUSTER = "rook-admission"


def measurement_failed(msg):
    print("FAILED MEASUREMENT: " + msg)
    sys.exit(2)


try:
    import yaml
except ImportError:
    measurement_failed("PyYAML unavailable, so nothing was rendered")
for tool in ("kind", "kubectl", "helm"):
    if shutil.which(tool) is None:
        measurement_failed("%s not on PATH, so nothing was admitted" % tool)

failures = []
counts = {}


def fail(m):
    failures.append(m)


def run(cmd, kubeconfig=None, stdin=None):
    env = dict(os.environ)
    if kubeconfig:
        env["KUBECONFIG"] = kubeconfig
    return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env)


def render(chart, values, tmp):
    w = os.path.join(tmp, "%s-%d" % (chart, len(os.listdir(tmp))))
    shutil.copytree(os.path.join(ROOT, "blueprints", chart, "chart"), w)
    cy = os.path.join(w, "Chart.yaml")
    body = open(cy).read()
    open(cy, "w").write(body.replace("CHART_VERSION", "0.0.0-gate"))
    vf = os.path.join(tmp, "values-%d.yaml" % len(os.listdir(tmp)))
    open(vf, "w").write(yaml.safe_dump(values or {}))
    r = run(["helm", "template", "gate", w, "--namespace", NS, "--kube-version", "1.36.0", "-f", vf])
    if r.returncode != 0:
        measurement_failed("%s does not render: %s" % (chart, r.stderr.strip()[-300:]))
    return [d for d in yaml.safe_load_all(r.stdout) if isinstance(d, dict)]


def dry_run(kc, docs):
    return run(["kubectl", "apply", "--dry-run=server", "-f", "-"], kc, yaml.safe_dump_all(docs))


VALID_DEVICES = {"consumer": {"namespace": "openstack"},
                 "osd": {"source": "devices", "devices": {"nodeLabel": {"key": "storage-node", "value": "true"},
                                                          "deviceFilter": "^nvme[0-9]+n[1-9]$"}}}
SHAPES = [
    ("raw devices", VALID_DEVICES),
    ("a StorageClass", {"consumer": {"namespace": "openstack"},
                        "osd": {"source": "storageClass", "storageClass": {"name": "local-block", "count": 3,
                                                                           "size": "200Gi"}},
                        "mon": {"storageClassName": "local-file"}}),
    ("testOnly, every pool", dict(VALID_DEVICES, testOnly=True, replication={"size": 1, "failureDomain": "osd"},
                                  mon={"count": 1}, pools={"vms": {"name": "vms", "enabled": True}})),
]


def main():
    tmp = tempfile.mkdtemp()
    kc = os.path.join(tmp, "kubeconfig")
    created = False
    try:
        r = run(["kind", "create", "cluster", "--name", CLUSTER, "--kubeconfig", kc, "--wait", "120s"])
        if r.returncode != 0:
            measurement_failed("kind could not create a cluster: %s" % r.stderr.strip()[-400:])
        created = True
        rtmp = os.path.join(tmp, "r")
        os.makedirs(rtmp)
        op = render("rook-operator", {}, rtmp)
        crds = [d for d in op if d["kind"] == "CustomResourceDefinition"]
        rest = [d for d in op if d["kind"] != "CustomResourceDefinition"]
        if not crds or not rest:
            measurement_failed("rook-operator rendered %d CRDs and %d other objects" % (len(crds), len(rest)))
        r = run(["kubectl", "apply", "--server-side", "-f", "-"], kc, yaml.safe_dump_all(crds))
        if r.returncode != 0:
            fail("rook-operator's CRDs are not admitted: %s" % r.stderr.strip()[-400:])
        run(["kubectl", "wait", "--for", "condition=Established", "--timeout", "60s", "crd", "--all"], kc)
        r = run(["kubectl", "create", "namespace", NS], kc)
        if r.returncode != 0:
            measurement_failed("could not create namespace %s: %s" % (NS, r.stderr.strip()[-200:]))
        r = dry_run(kc, rest)
        if r.returncode != 0:
            fail("rook-operator: the API server refuses: %s" % r.stderr.strip()[-600:])
        counts["rook-operator objects"] = len(op)
        cluster_docs = []
        for label, vals in SHAPES:
            docs = render("rook-ceph-cluster", vals, rtmp)
            cluster_docs.append(docs)
            r = dry_run(kc, docs)
            if r.returncode != 0:
                fail("rook-ceph-cluster (%s): the API server refuses: %s" % (label, r.stderr.strip()[-600:]))
            counts["rook-ceph-cluster objects"] = counts.get("rook-ceph-cluster objects", 0) + len(docs)
        base = cluster_docs[0]

        def mutant(kind, change, field):
            docs = copy.deepcopy([d for d in base if d["kind"] == kind][:1])
            if not docs:
                fail("negative control: no %s rendered to break" % kind)
                return
            change(docs[0])
            r = dry_run(kc, docs)
            if r.returncode == 0:
                fail("negative control: a %s with a broken %s is admitted, so admission proves nothing" % (kind, field))
            elif field.split(".")[-1] not in r.stderr:
                fail("negative control: the %s is refused without naming %s: %s" % (kind, field, r.stderr.strip()[-300:]))
            counts["negative controls"] = counts.get("negative controls", 0) + 1
        mutant("CephBlockPool", lambda d: d["spec"]["replicated"].__setitem__("size", "three"), "spec.replicated.size")
        sc = render("rook-ceph-cluster", SHAPES[1][1], rtmp)
        base = sc
        mutant("CephCluster", lambda d: d["spec"]["storage"]["storageClassDeviceSets"][0].__setitem__("count", "x"),
               "storageClassDeviceSets.count")
        base = cluster_docs[0]
        mutant("CephClient", lambda d: d["spec"].__setitem__("caps", ["profile rbd"]), "spec.caps")
    finally:
        if created:
            run(["kind", "delete", "cluster", "--name", CLUSTER, "--kubeconfig", kc])
        shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print("FAIL: %d problem(s)" % len(failures))
        for m in failures:
            print("  " + m)
        sys.exit(1)
    print("OK: an API server with Rook v1.21's CRDs admits %s" % json.dumps(counts))


if __name__ == "__main__":
    main()
