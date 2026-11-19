#!/usr/bin/env python3
"""Both charts render what they say, and refuse what cannot work.

    hack/validate-render.py [repo-root]

rook-operator (Rook's release manifests, rendered with the changes templates/manifests.yaml documents):
  R1. DERIVED, NOT TRUSTED. This script applies the documented changes to the vendored files itself -- drop the
      Namespace, the csi.ceph.io objects and the CSI image ConfigMap; every `namespace: rook-ceph` field to the release's
      namespace; helm.sh/resource-policy: keep on every CRD; ROOK_CREATE_CSI_OPERATOR_RESOURCES "false" and
      ROOK_LOG_LEVEL in the operator config; the operator container's image, pull policy and resources, the pod's
      nodeSelector and added tolerations -- and the chart's render must equal it object for object, at the defaults and
      with every value set to a non-default. A namespace other than rook-ceph is used, so a missed rewrite shows.
  R2. NO CSI. No rendered object is of a csi.ceph.io kind, and the operator config says not to create them.

rook-ceph-cluster (Rook custom resources only):
  C1. REFUSALS, each naming the value: no consumer.namespace; osd.source devices without a node label or a device
      filter; storageClass without a name; an unknown source; replication.size or mon.count below 3 without testOnly;
      an even mon.count; no pool enabled; a pool name that is not a Kubernetes object name; two roles
      on one pool name.
  C2. A devices cluster: exactly one CephCluster (useAllNodes, useAllDevices false, the deviceFilter, the osd and
      prepareosd placements requiring the storage-node label, managePodBudgets), one CephBlockPool per enabled pool
      (metadata.name the pool's Ceph name and no spec.name, which Rook's CRD admits only for Ceph's built-in pools;
      size, failure domain, requireSafeReplicaSize), one CephClient per enabled role
      with exactly the Ceph documentation's caps for OpenStack (every osd and mgr cap names a pool; none is a bare
      `profile rbd`), and the read grant: a Role allowing get on exactly rook-ceph-client-<client>... and
      rook-ceph-config, bound to the consumer's ServiceAccount in the consumer's namespace. Nothing else: no Job, no
      Pod, no workload.
  C3. A storageClass cluster: storageClassDeviceSets of block-mode claims from the named class; useAllNodes false.
  C4. Pool roles move the caps: vms on adds it to cinder's osd and mgr caps; images off renders no glance client and no
      read-only cap on images.
  C5. PRECONDITIONS, driven with stand-in lookups (the GATE-LOOKUP lines): on a live cluster (core-provider's CRD
      present), a missing Rook CRD refuses naming it, and a namespace without Rook's rook-ceph-osd ServiceAccount
      refuses; with both present it renders; offline nothing is refused.
  C6. testOnly: replication.size 1 and mon.count 1 render, with requireSafeReplicaSize false and allowMultiplePerNode.

Fails when helm or PyYAML is missing, and when a render it needs does not happen.
"""
import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
NS = "storage"


def measurement_failed(msg):
    print("FAILED MEASUREMENT: " + msg)
    sys.exit(2)


try:
    import yaml
except ImportError:
    measurement_failed("PyYAML unavailable, so nothing was rendered")
if shutil.which("helm") is None:
    measurement_failed("helm not on PATH, so nothing was rendered")

failures = []
counts = {}


def fail(m):
    failures.append(m)


def count(k):
    counts[k] = counts.get(k, 0) + 1


def stage(chart, tmp, name, edit=None):
    w = os.path.join(tmp, name)
    shutil.copytree(os.path.join(ROOT, "blueprints", chart, "chart"), w)
    cy = os.path.join(w, "Chart.yaml")
    body = open(cy).read()
    open(cy, "w").write(body.replace("CHART_VERSION", "0.0.0-gate"))
    if edit:
        edit(w)
    return w


def render(w, values):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(values or {}, f)
    try:
        r = subprocess.run(["helm", "template", "gate", w, "--namespace", NS, "--kube-version", "1.36.0", "-f", f.name],
                           capture_output=True, text=True)
    finally:
        os.unlink(f.name)
    return r.returncode, r.stdout, r.stderr


def docs_of(out):
    return [d for d in yaml.safe_load_all(out) if isinstance(d, dict)]


def key(d):
    return (d.get("kind"), (d.get("metadata") or {}).get("namespace"), (d.get("metadata") or {}).get("name"))


# --- rook-operator ---------------------------------------------------------------------------------------------------

NS_FIELD = re.compile(r"(?m)^(\s*namespace:\s*)rook-ceph(\s*#.*)?$")


def derive(values):
    up = os.path.join(ROOT, "blueprints", "rook-operator", "chart", "files", "upstream")
    out = []
    for f in ("crds.yaml", "common.yaml", "operator.yaml"):
        raw = open(os.path.join(up, f)).read()
        for doc in re.split(r"(?m)^---[ \t]*$", raw):
            o = yaml.safe_load(NS_FIELD.sub(lambda m: m.group(1) + NS, doc))
            if not isinstance(o, dict) or not o.get("kind"):
                continue
            if o["kind"] == "Namespace" or str(o.get("apiVersion", "")).startswith("csi.ceph.io/") or \
                    (o["kind"] == "ConfigMap" and o["metadata"]["name"] == "rook-csi-operator-image-set-configmap"):
                continue
            if o["kind"] == "CustomResourceDefinition":
                o["metadata"].setdefault("annotations", {})["helm.sh/resource-policy"] = "keep"
            if o["kind"] == "ConfigMap" and o["metadata"]["name"] == "rook-ceph-operator-config":
                o["data"]["ROOK_CREATE_CSI_OPERATOR_RESOURCES"] = "false"
                o["data"]["ROOK_LOG_LEVEL"] = str(values["logLevel"])
            if o["kind"] == "Deployment" and o["metadata"]["name"] == "rook-ceph-operator":
                pod = o["spec"]["template"]["spec"]
                for c in pod["containers"]:
                    if c["name"] == "rook-ceph-operator":
                        c["image"] = "%s:%s" % (values["image"]["repository"], values["image"]["tag"])
                        if values["image"]["pullPolicy"]:
                            c["imagePullPolicy"] = values["image"]["pullPolicy"]
                        if values["resources"]:
                            c["resources"] = values["resources"]
                if values["nodeSelector"]:
                    pod["nodeSelector"] = values["nodeSelector"]
                if values["tolerations"]:
                    pod["tolerations"] = (pod.get("tolerations") or []) + values["tolerations"]
            out.append(o)
    return out


def check_operator(tmp):
    defaults = yaml.safe_load(open(os.path.join(ROOT, "blueprints", "rook-operator", "chart", "values.yaml")))
    custom = copy.deepcopy(defaults)
    custom.update({"logLevel": "DEBUG", "nodeSelector": {"node-role.example/storage": "true"},
                   "tolerations": [{"key": "storage", "operator": "Exists", "effect": "NoSchedule"}],
                   "resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}})
    custom["image"] = {"repository": "registry.example/rook/ceph", "tag": "v1.21.1-gate", "pullPolicy": "IfNotPresent"}
    w = stage("rook-operator", tmp, "rook-operator")
    for label, vals in (("defaults", None), ("every value set", custom)):
        rc, out, err = render(w, vals)
        if rc != 0:
            fail("R1: rook-operator (%s) does not render: %s" % (label, err.strip()[-300:]))
            continue
        got = {key(d): d for d in docs_of(out)}
        want = {key(d): d for d in derive(vals or defaults)}
        for k in sorted(set(want) - set(got), key=str):
            fail("R1: rook-operator (%s) does not render %s/%s/%s" % ((label,) + k))
        for k in sorted(set(got) - set(want), key=str):
            fail("R1: rook-operator (%s) renders %s/%s/%s, which the documented changes do not produce" % ((label,) + k))
        for k in sorted(set(got) & set(want), key=str):
            if got[k] != want[k]:
                fail("R1: rook-operator (%s): %s/%s/%s differs from upstream with the documented changes"
                     % ((label,) + k))
        if not got:
            fail("R1: rook-operator (%s) renders nothing" % label)
        if "namespace: rook-ceph" in out:
            fail("R1: rook-operator (%s) still renders a `namespace: rook-ceph` in release namespace %s" % (label, NS))
        csi = [k for k, d in got.items() if str(d.get("apiVersion", "")).startswith("csi.ceph.io/")]
        cfg = [d for d in got.values() if d.get("kind") == "ConfigMap"
               and d["metadata"]["name"] == "rook-ceph-operator-config"]
        if csi or len(cfg) != 1 or cfg[0]["data"].get("ROOK_CREATE_CSI_OPERATOR_RESOURCES") != "false":
            fail("R2: rook-operator (%s) renders CSI objects %s or does not switch CSI off in its config" % (label, csi))
        count("R")


# --- rook-ceph-cluster ----------------------------------------------------------------------------------------------------

VALID_DEVICES = {"consumer": {"namespace": "openstack"},
                 "osd": {"source": "devices", "devices": {"nodeLabel": {"key": "storage-node", "value": "true"},
                                                          "deviceFilter": "^nvme[0-9]+n[1-9]$"}}}
VALID_SC = {"consumer": {"namespace": "openstack"},
            "osd": {"source": "storageClass", "storageClass": {"name": "local-block", "count": 3, "size": "200Gi"}}}


def merged(base, add):
    out = copy.deepcopy(base)

    def rec(a, b):
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                rec(a[k], v)
            else:
                a[k] = v
    rec(out, add)
    return out


def caps_want(values, who):
    p = values["pools"]
    osd, mgr = [], []
    if who == "cinder":
        if p["volumes"]["enabled"]:
            osd.append("profile rbd pool=%s" % p["volumes"]["name"])
            mgr.append("profile rbd pool=%s" % p["volumes"]["name"])
        if p["vms"]["enabled"]:
            osd.append("profile rbd pool=%s" % p["vms"]["name"])
            mgr.append("profile rbd pool=%s" % p["vms"]["name"])
        if p["images"]["enabled"]:
            osd.append("profile rbd-read-only pool=%s" % p["images"]["name"])
    else:
        osd.append("profile rbd pool=%s" % p["images"]["name"])
        mgr.append("profile rbd pool=%s" % p["images"]["name"])
    return {"mon": "profile rbd", "osd": ", ".join(osd), "mgr": ", ".join(mgr)}


def check_cluster_objects(label, docs, values):
    kinds = sorted({d["kind"] for d in docs})
    if kinds != ["CephBlockPool", "CephClient", "CephCluster", "Role", "RoleBinding"]:
        fail("C2: rook-ceph-cluster (%s) renders kinds %s, want only CephCluster, CephBlockPool, CephClient, Role and "
             "RoleBinding" % (label, kinds))
    cl = [d for d in docs if d["kind"] == "CephCluster"]
    if len(cl) != 1:
        fail("C2: rook-ceph-cluster (%s) renders %d CephCluster(s), want 1" % (label, len(cl)))
        return
    spec = cl[0]["spec"]
    st = spec.get("storage") or {}
    if values["osd"]["source"] == "devices":
        lab = values["osd"]["devices"]["nodeLabel"]
        want_aff = {"requiredDuringSchedulingIgnoredDuringExecution": {"nodeSelectorTerms": [{"matchExpressions": [
            {"key": lab["key"], "operator": "In", "values": [lab["value"]]}]}]}}
        if st.get("useAllNodes") is not True or st.get("useAllDevices") is not False or \
                st.get("deviceFilter") != values["osd"]["devices"]["deviceFilter"] or st.get("storageClassDeviceSets"):
            fail("C2: rook-ceph-cluster (%s): storage %s, want useAllNodes, no useAllDevices, deviceFilter %r" % (
                label, st, values["osd"]["devices"]["deviceFilter"]))
        for role in ("osd", "prepareosd"):
            if ((spec.get("placement") or {}).get(role) or {}).get("nodeAffinity") != want_aff:
                fail("C2: rook-ceph-cluster (%s): placement.%s does not require the storage-node label %s" % (label, role, lab))
    else:
        sets = st.get("storageClassDeviceSets") or []
        sc = values["osd"]["storageClass"]
        ok = len(sets) == 1 and sets[0].get("count") == sc["count"] and st.get("useAllNodes") is False
        if ok:
            t = (sets[0].get("volumeClaimTemplates") or [{}])[0].get("spec") or {}
            ok = t.get("storageClassName") == sc["name"] and t.get("volumeMode") == "Block" and \
                ((t.get("resources") or {}).get("requests") or {}).get("storage") == sc["size"]
        if not ok:
            fail("C3: rook-ceph-cluster (%s): storage %s, want one block-mode device set of %d from %s at %s" % (
                label, st, sc["count"], sc["name"], sc["size"]))
    if ((spec.get("disruptionManagement") or {}).get("managePodBudgets")) is not True:
        fail("C2: rook-ceph-cluster (%s): managePodBudgets is not on" % label)
    if (spec.get("mon") or {}).get("count") != values["mon"]["count"] or \
            (spec.get("mon") or {}).get("allowMultiplePerNode") != values["testOnly"]:
        fail("C2: rook-ceph-cluster (%s): mon %s" % (label, spec.get("mon")))
    pools = {d["metadata"]["name"]: d for d in docs if d["kind"] == "CephBlockPool"}
    want_pools = {p["name"] for p in values["pools"].values() if p["enabled"]}
    if set(pools) != want_pools:
        fail("C2: rook-ceph-cluster (%s): pools %s, want %s" % (label, sorted(pools), sorted(want_pools)))
    for n, d in pools.items():
        s = d["spec"]
        if s.get("failureDomain") != values["replication"]["failureDomain"] or \
                (s.get("replicated") or {}).get("size") != values["replication"]["size"] or \
                (s.get("replicated") or {}).get("requireSafeReplicaSize") != (not values["testOnly"]) or \
                s.get("application") != "rbd" or "name" in s:
            fail("C2: rook-ceph-cluster (%s): pool %s renders %s" % (label, n, s))
    clients = {d["metadata"]["name"]: d for d in docs if d["kind"] == "CephClient"}
    roles = (["cinder"] if values["pools"]["volumes"]["enabled"] else []) + \
        (["glance"] if values["pools"]["images"]["enabled"] else [])
    want_clients = {values["clients"][r]: r for r in roles}
    if set(clients) != set(want_clients):
        fail("C2: rook-ceph-cluster (%s): clients %s, want %s" % (label, sorted(clients), sorted(want_clients)))
    for n, r in want_clients.items():
        if n not in clients:
            continue
        got = clients[n]["spec"].get("caps")
        want = caps_want(values, r)
        if got != want:
            fail("C2: rook-ceph-cluster (%s): client %s caps %s, want %s" % (label, n, got, want))
        for c in (got or {}).get("osd", "").split(", ") + (got or {}).get("mgr", "").split(", "):
            if c.strip() in ("profile rbd", "profile rbd-read-only"):
                fail("C2: rook-ceph-cluster (%s): client %s has a cap that names no pool: %r" % (label, n, c))
    role = [d for d in docs if d["kind"] == "Role"]
    binding = [d for d in docs if d["kind"] == "RoleBinding"]
    want_names = sorted(["rook-ceph-client-%s" % n for n in want_clients] + ["rook-ceph-config"])
    sec = [r for r in (role[0].get("rules") or []) if "secrets" in (r.get("resources") or [])] if len(role) == 1 else []
    if len(sec) != 1 or sorted(sec[0].get("resourceNames") or []) != want_names or sec[0].get("verbs") != ["get"]:
        fail("C2: rook-ceph-cluster (%s): the read grant allows %s, want get on exactly %s" % (label, sec, want_names))
    subj = (binding[0].get("subjects") or []) if len(binding) == 1 else []
    want_subj = [{"kind": "ServiceAccount", "name": values["consumer"]["serviceAccount"],
                  "namespace": values["consumer"]["namespace"]}]
    if subj != want_subj or (binding and binding[0]["roleRef"]["name"] != (role[0]["metadata"]["name"] if role else None)):
        fail("C2: rook-ceph-cluster (%s): the grant binds %s, want %s" % (label, subj, want_subj))
    count("C2")


def check_cluster(tmp):
    defaults = yaml.safe_load(open(os.path.join(ROOT, "blueprints", "rook-ceph-cluster", "chart", "values.yaml")))
    w = stage("rook-ceph-cluster", tmp, "rook-ceph-cluster")
    refusals = [
        ("defaults (no consumer.namespace)", {}, "consumer.namespace"),
        ("devices without a device filter", merged(VALID_DEVICES, {"osd": {"devices": {"deviceFilter": ""}}}),
         "osd.devices.deviceFilter"),
        ("devices without a node label", merged(VALID_DEVICES, {"osd": {"devices": {"nodeLabel": {"key": ""}}}}),
         "osd.devices.nodeLabel.key"),
        ("storageClass without a name", merged(VALID_SC, {"osd": {"storageClass": {"name": ""}}}),
         "osd.storageClass.name"),
        ("replication.size 2", merged(VALID_DEVICES, {"replication": {"size": 2}}), "replication.size"),
        ("mon.count 1", merged(VALID_DEVICES, {"mon": {"count": 1}}), "mon.count"),
        ("mon.count 4", merged(VALID_DEVICES, {"mon": {"count": 4}}), "even"),
        ("no pool", merged(VALID_DEVICES, {"pools": {"volumes": {"enabled": False}, "images": {"enabled": False}}}),
         "No pool"),
        ("a pool name with '_'", merged(VALID_DEVICES, {"pools": {"volumes": {"name": "cinder_volumes"}}}),
         "pools.volumes.name"),
        ("a pool name starting with '.'", merged(VALID_DEVICES, {"pools": {"images": {"name": ".glance"}}}),
         "pools.images.name"),
        ("two roles on one pool", merged(VALID_DEVICES, {"pools": {"vms": {"enabled": True, "name": "cinder.volumes"}}}),
         "also pools.volumes.name"),
    ]
    for label, vals, frag in refusals:
        rc, out, err = render(w, vals)
        if rc == 0:
            fail("C1: rook-ceph-cluster with %s renders; it must refuse" % label)
        elif frag not in err:
            fail("C1: rook-ceph-cluster with %s is refused without naming %r: %s" % (label, frag, err.strip()[-250:]))
        count("C1")
    cases = [("devices", VALID_DEVICES), ("storageClass", VALID_SC),
             ("vms on", merged(VALID_DEVICES, {"pools": {"vms": {"enabled": True}}})),
             ("images off", merged(VALID_DEVICES, {"pools": {"images": {"enabled": False}}})),
             ("testOnly, size 1, one mon", merged(VALID_DEVICES, {"testOnly": True, "replication": {"size": 1},
                                                                  "mon": {"count": 1}}))]
    for label, vals in cases:
        rc, out, err = render(w, vals)
        if rc != 0:
            fail("C2: rook-ceph-cluster (%s) does not render: %s" % (label, err.strip()[-300:]))
            continue
        check_cluster_objects(label, docs_of(out), merged(defaults, vals))

    # C5. preconditions, with stand-in lookups
    tpl = os.path.join("templates", "_preconditions.tpl")
    crd_line = '{{- if lookup "apiextensions.k8s.io/v1" "CustomResourceDefinition" "" . }}true{{ end -}}'
    sa_line = '{{- if lookup "v1" "ServiceAccount" .ns .name }}true{{ end -}}'
    body = open(os.path.join(ROOT, "blueprints", "rook-ceph-cluster", "chart", tpl)).read()
    if body.count(crd_line) != 1 or body.count(sa_line) != 1:
        fail("C5: _preconditions.tpl must look up CRDs and the ServiceAccount with exactly one named GET each")
        return
    for label, served, sa, refuse in (
            ("offline", [], False, None),
            ("live, no Rook CRDs", ["compositiondefinitions.core.krateo.io"], True, "cephclusters.ceph.rook.io"),
            ("live, Rook CRDs, no rook-ceph-osd ServiceAccount",
             ["compositiondefinitions.core.krateo.io", "cephclusters.ceph.rook.io", "cephblockpools.ceph.rook.io",
              "cephclients.ceph.rook.io"], False, "rook-ceph-osd"),
            ("live, everything present",
             ["compositiondefinitions.core.krateo.io", "cephclusters.ceph.rook.io", "cephblockpools.ceph.rook.io",
              "cephclients.ceph.rook.io"], True, None)):
        def patch(wd, served=served, sa=sa):
            p = os.path.join(wd, tpl)
            t = open(p).read()
            t = t.replace(crd_line, '{{- if has . (list %s) }}true{{ end -}}' % " ".join('"%s"' % s for s in served))
            t = t.replace(sa_line, '{{- if %s }}true{{ end -}}' % ("true" if sa else "false"))
            open(p, "w").write(t)
        wd = stage("rook-ceph-cluster", tmp, "rook-ceph-cluster-c5-%d" % abs(hash(label)), patch)
        rc, out, err = render(wd, VALID_DEVICES)
        if refuse is None and rc != 0:
            fail("C5: rook-ceph-cluster (%s) is refused: %s" % (label, err.strip()[-250:]))
        elif refuse is not None and (rc == 0 or refuse not in err):
            fail("C5: rook-ceph-cluster (%s) %s; it must refuse naming %s" % (
                label, "renders" if rc == 0 else "is refused without naming it", refuse))
        count("C5")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        check_operator(tmp)
        check_cluster(tmp)
    for k in ("R", "C1", "C2", "C5"):
        if not counts.get(k):
            fail("%s: measured nothing" % k)
    if failures:
        print("FAIL: %d problem(s)" % len(failures))
        for m in failures:
            print("  " + m)
        sys.exit(1)
    print("OK: " + "; ".join("%s: %d" % (k, v) for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
