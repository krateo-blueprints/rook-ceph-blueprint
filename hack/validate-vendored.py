#!/usr/bin/env python3
"""Each vendored upstream file is byte for byte what the pinned tag holds.

    hack/validate-vendored.py [repo-root] [--live]

rook-operator renders blueprints/rook-operator/chart/files/upstream/<asset>, each the file at <path> in the upstream
repository's tree at the tag hack/upstream.yaml names (Rook publishes no release assets). Every change this repository
makes is applied at render time, in templates/manifests.yaml, where hack/validate-render.py checks it. So each vendored
file must stay what upstream tagged:
  1. its SHA-256 is the digest recorded in hack/upstream.yaml;
  2. --live (CI): it is byte-equal to https://raw.githubusercontent.com/<repo>/<tag>/<path> today, so a pin to the
     wrong tag, or a file edited after vendoring, cannot pass on a recorded digest alone;
  3. on the entry naming an image and a container: the vendored Deployment has that container, running that image at
     the tag's version, which is the image the chart's values default to (hack/validate-version-mirror.py).
Fails when PyYAML is missing, when hack/upstream.yaml lists nothing, when no entry names an image, and, with --live,
when GitHub cannot be read.
"""
import hashlib
import os
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
    measurement_failed("PyYAML unavailable, so the vendored manifests were never read")

entries = (yaml.safe_load(open(os.path.join(ROOT, "hack", "upstream.yaml"))) or {}).get("upstreams") or []
if not entries:
    measurement_failed("hack/upstream.yaml lists no upstream, so nothing was checked")
if not any(e.get("image") for e in entries):
    measurement_failed("no hack/upstream.yaml entry names the operator image, so the image check would check nothing")
failures = []
for e in entries:
    path = os.path.join(ROOT, "blueprints", e["chart"], "chart", "files", "upstream", e["asset"])
    if not os.path.isfile(path):
        failures.append("%s: %s is missing" % (e["chart"], os.path.relpath(path, ROOT)))
        continue
    data = open(path, "rb").read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != e["sha256"]:
        failures.append("%s: %s has SHA-256 %s, hack/upstream.yaml records %s. Re-vendor it from %s %s:%s unchanged, "
                        "or record the new digest together with the new tag."
                        % (e["chart"], e["asset"], digest, e["sha256"], e["repo"], e["tag"], e["path"]))
    if LIVE:
        url = "https://raw.githubusercontent.com/%s/%s/%s" % (e["repo"], e["tag"], e["path"])
        try:
            served = urllib.request.urlopen(url, timeout=60).read()
        except Exception as ex:
            measurement_failed("could not read %s: %s" % (url, ex))
        if served != data:
            failures.append("%s: %s differs from what %s serves today (SHA-256 %s)"
                            % (e["chart"], e["asset"], url, hashlib.sha256(served).hexdigest()))
    if e.get("image"):
        want_image = "%s:%s" % (e["image"], e["tag"])
        images = []
        for d in yaml.safe_load_all(data):
            if d and d.get("kind") == "Deployment":
                for c in d["spec"]["template"]["spec"].get("containers") or []:
                    if c.get("name") == e["container"]:
                        images.append(c.get("image"))
        if images != [want_image]:
            failures.append("%s: the vendored Deployment's %s container runs %s, want exactly [%s]"
                            % (e["chart"], e["container"], images or "nothing", want_image))

if failures:
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("OK: %d vendored file(s) match their recorded digest%s, and the operator runs the recorded image (%s)"
      % (len(entries), " and what the tag serves" if LIVE else "",
         ", ".join(sorted({"%s %s" % (e["repo"], e["tag"]) for e in entries}))))
