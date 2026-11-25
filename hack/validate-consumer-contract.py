#!/usr/bin/env python3
"""rook-ceph-cluster, at its defaults, is what the OpenStack blueprint looks for.

    hack/validate-consumer-contract.py [repo-root] [--live]

hack/openstack-contract.yaml records what krateo-openstack-blueprint's umbrella expects of a Ceph it consumes with
storage.backend ceph-rook: pool and client names, where Rook keeps each client's key and mon_host, and the
ServiceAccount its copy store reads with. Checked:
  1. rook-ceph-cluster's values.yaml defaults name the same pools and clients, and consumer.serviceAccount is that
     ServiceAccount;
  2. what Rook writes is what the umbrella reads: a CephClient's Secret is rook-ceph-client-<CR name> holding userKey
     (this chart never sets spec.secretName or spec.name, so the defaults hold), and the monitors are in
     rook-ceph-config under mon_host, which rook-ceph-cluster's read grant names;
  3. --live (CI): the recorded values equal the umbrella's at krateo-openstack-blueprint main today, so a rename on
     either side fails here instead of on a cluster, as a copy that never syncs.
Fails when PyYAML is missing and, with --live, when GitHub cannot be read.
"""
import os
import re
import sys
import urllib.request

args = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = os.path.abspath(args[0] if args else ".")
LIVE = "--live" in sys.argv


def measurement_failed(msg):
    print("FAILED MEASUREMENT: " + msg)
    sys.exit(2)


try:
    import yaml
except ImportError:
    measurement_failed("PyYAML unavailable, so nothing was read")

c = yaml.safe_load(open(os.path.join(ROOT, "hack", "openstack-contract.yaml")))
v = yaml.safe_load(open(os.path.join(ROOT, "blueprints", "rook-ceph-cluster", "chart", "values.yaml")))
failures = []
for role in ("volumes", "images"):
    if v["pools"][role]["name"] != c["pools"][role]:
        failures.append("pools.%s.name %r, the OpenStack blueprint reads %r" % (role, v["pools"][role]["name"],
                                                                                 c["pools"][role]))
for role in ("cinder", "glance"):
    if v["clients"][role] != c["clients"][role]:
        failures.append("clients.%s %r, the OpenStack blueprint reads %r" % (role, v["clients"][role], c["clients"][role]))
if v["consumer"]["serviceAccount"] != c["serviceAccount"]:
    failures.append("consumer.serviceAccount %r, the OpenStack blueprint's copy store is %r"
                    % (v["consumer"]["serviceAccount"], c["serviceAccount"]))
if c["rook"] != {"clientSecretPrefix": "rook-ceph-client-", "clientKey": "userKey", "monHostSecret": "rook-ceph-config",
                 "monHostKey": "mon_host"}:
    failures.append("the OpenStack blueprint reads Rook's Secrets as %s, which is not where Rook v1.21 writes them "
                    "(rook-ceph-client-<name>/userKey, rook-ceph-config/mon_host)" % c["rook"])
tpl = open(os.path.join(ROOT, "blueprints", "rook-ceph-cluster", "chart", "templates", "clients.yaml")).read()
client_spec = tpl.split("kind: CephClient", 1)[-1].split("\nspec:\n", 1)[-1].split("{{- end }}", 1)[0]
if "secretName" in tpl or [l for l in client_spec.splitlines() if re.match(r"^  (name|secretName):", l)]:
    failures.append("clients.yaml sets a CephClient spec.secretName or spec.name, so Rook's Secret would not be "
                    "rook-ceph-client-<CR name>/userKey")
if '"rook-ceph-config"' not in tpl or 'printf "rook-ceph-client-%s"' not in tpl:
    failures.append("clients.yaml's read grant does not name rook-ceph-client-<client> and rook-ceph-config")
if LIVE:
    s = c["source"]
    url = "https://raw.githubusercontent.com/%s/main/%s" % (s["repo"], s["file"])
    try:
        um = yaml.safe_load(urllib.request.urlopen(url, timeout=60).read())
    except Exception as ex:
        measurement_failed("could not read %s: %s" % (url, ex))
    ceph = ((um.get("storage") or {}).get("ceph") or {})
    live = {"pools": ceph.get("pools"), "clients": ceph.get("clients"), "rook": ceph.get("rook"),
            "serviceAccount": "%s-ceph-reader" % ((um.get("credentials") or {}).get("store"))}
    for k, val in live.items():
        if val != c[k]:
            failures.append("--live: the OpenStack blueprint's main has %s %s, hack/openstack-contract.yaml records %s"
                            % (k, val, c[k]))
if failures:
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("OK: rook-ceph-cluster's defaults are what the OpenStack blueprint reads%s" % (" (checked against its main)" if LIVE else ""))
