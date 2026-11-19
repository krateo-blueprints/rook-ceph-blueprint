#!/usr/bin/env python3
"""The release runs this repository's preflight before it publishes anything, and the preflight refuses what it must.

    hack/validate-release-wiring.py [repo-root]

krateo-blueprints/charts PUBLISHING.md rule 12: a release first runs the reusable release-preflight.yaml, which runs
hack/release-preflight with the tag; the publishing job `needs:` it, so a refusal publishes nothing. Checked:
  1. release-tag.yaml: job `preflight` uses release-preflight.yaml and job `publish-index` uses publish-chart.yaml,
     both from krateo-blueprints/charts at the SAME full commit SHA with the same `# X.Y.Z` comment (rule 9);
     preflight passes `version: ${{ github.ref_name }}`; package-and-push needs preflight; publish-index needs
     package-and-push; the channel is blueprints everywhere and the uploaded artifact is the one the publisher reads.
  2. hack/release-preflight is an executable regular file (a hook without its executable bit fails the reusable job).
  3. The hook, RUN: it passes for the version examples/basic serves, and refuses a version with a "v" prefix, a
     two-part version, another version than the examples', examples naming two versions, and a vendored
     manifest whose digest moved.
  4. Every `uses:` in every workflow, actions and reusable workflows alike, is pinned to a full 40-hex commit SHA with
     a `# <version>` comment (Dependabot keeps them current). A movable ref (a branch such as @main, a tag such as
     @v7) can change what runs without a commit here, and the release workflow receives an org-wide write token.
     Local actions (./...) are exempt.

Fails when PyYAML is missing.
"""
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")


def measurement_failed(msg):
    print("FAILED MEASUREMENT: " + msg)
    sys.exit(2)


try:
    import yaml
except ImportError:
    measurement_failed("PyYAML unavailable, so release-tag.yaml was never read")

failures = []
wf_path = os.path.join(ROOT, ".github", "workflows", "release-tag.yaml")
text = open(wf_path).read()
wf = yaml.safe_load(text)
jobs = wf.get("jobs") or {}
USE = re.compile(r"^\s*uses:\s*krateo-blueprints/charts/\.github/workflows/(\S+)@([0-9a-f]{40}) # (\d+\.\d+\.\d+)\s*$", re.M)
uses = {m.group(1): (m.group(2), m.group(3)) for m in USE.finditer(text)}
for want in ("release-preflight.yaml", "publish-chart.yaml"):
    if want not in uses:
        failures.append("1: release-tag.yaml does not use krateo-blueprints/charts %s at a full SHA with a # X.Y.Z "
                        "comment" % want)
if len(set(uses.values())) > 1:
    failures.append("1: the reusables are pinned to different releases: %s" % uses)
pre = jobs.get("preflight") or {}
if "release-preflight.yaml@" not in str(pre.get("uses", "")):
    failures.append("1: job preflight does not use release-preflight.yaml")
if (pre.get("with") or {}).get("version") != "${{ github.ref_name }}":
    failures.append("1: preflight passes version %r, want ${{ github.ref_name }}" % (pre.get("with") or {}).get("version"))
pp = jobs.get("package-and-push") or {}
if "preflight" not in (pp.get("needs") or []):
    failures.append("1: package-and-push does not need preflight, so a refusal would not stop the push")
pi = jobs.get("publish-index") or {}
needs = pi.get("needs") or []
if "package-and-push" not in ([needs] if isinstance(needs, str) else needs):
    failures.append("1: publish-index does not need package-and-push")
if "publish-chart.yaml@" not in str(pi.get("uses", "")):
    failures.append("1: job publish-index does not use publish-chart.yaml")
pw = pi.get("with") or {}
if pw.get("channel") != "blueprints" or (wf.get("env") or {}).get("CHANNELS") != "blueprints":
    failures.append("1: the channel is %r (publish) and %r (CHANNELS), want blueprints for both"
                    % (pw.get("channel"), (wf.get("env") or {}).get("CHANNELS")))
uploads = [s.get("with", {}).get("name") for s in pp.get("steps") or [] if "upload-artifact" in str(s.get("uses", ""))]
if uploads != [pw.get("artifact")]:
    failures.append("1: package-and-push uploads %s, the publisher reads %r" % (uploads, pw.get("artifact")))

hook = os.path.join(ROOT, "hack", "release-preflight")
if not os.path.isfile(hook) or not os.stat(hook).st_mode & stat.S_IXUSR:
    failures.append("2: hack/release-preflight is missing or not executable; release-preflight.yaml would refuse")
else:
    served = None
    for f in sorted(os.listdir(os.path.join(ROOT, "examples", "basic"))):
        if f.endswith(".yaml"):
            m = re.search(r"(?m)^apiVersion: composition\.krateo\.io/v(\d+)-(\d+)-(\d+)$",
                          open(os.path.join(ROOT, "examples", "basic", f)).read())
            if m:
                served = ".".join(m.groups())
    if not served:
        measurement_failed("examples/basic names no composition.krateo.io version, so the hook cannot be exercised")
    major, minor, patch = served.split(".")
    other = "%s.%s.%d" % (major, minor, int(patch) + 1)

    def run(root, version):
        return subprocess.run([os.path.join(root, "hack", "release-preflight"), version], capture_output=True, text=True)

    r = run(ROOT, served)
    if r.returncode != 0:
        failures.append("3: the hook refuses %s, the version examples/basic serves: %s" % (served, r.stdout.strip()[-300:]))
    for bad in ("v" + served, "%s.%s" % (major, minor), other):
        if run(ROOT, bad).returncode == 0:
            failures.append("3: the hook accepts %r; it must refuse it" % bad)
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "repo")
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git"))
        asset = sorted(p for p in __import__("glob").glob(os.path.join(copy, "blueprints", "*", "chart", "files",
                                                                         "upstream", "*")))
        if not asset:
            measurement_failed("no vendored manifest to tamper with")
        with open(asset[0], "a") as f:
            f.write("# tampered\n")
        if run(copy, served).returncode == 0:
            failures.append("3: the hook accepts a vendored manifest whose digest moved")
    with tempfile.TemporaryDirectory() as tmp:
        copy = os.path.join(tmp, "repo")
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git"))
        ex = sorted(f for f in os.listdir(os.path.join(copy, "examples", "basic")) if f.endswith(".yaml"))
        p = os.path.join(copy, "examples", "basic", ex[0])
        t = open(p).read()
        open(p, "w").write(t.replace("composition.krateo.io/v%s" % served.replace(".", "-"),
                                     "composition.krateo.io/v%s" % other.replace(".", "-")))
        if run(copy, served).returncode == 0:
            failures.append("3: the hook accepts examples that name two versions (%s left at %s)" % (ex[0], other))

PIN = re.compile(r"^\s*(?:-\s+)?uses:\s*([^\s#]+)(?:\s+#\s*(\S.*))?$")
wf_dir = os.path.join(ROOT, ".github", "workflows")
pinned = 0
for fn in sorted(os.listdir(wf_dir)):
    if not fn.endswith((".yaml", ".yml")):
        continue
    for n, line in enumerate(open(os.path.join(wf_dir, fn)), 1):
        m = PIN.match(line)
        if not m:
            continue
        ref = m.group(1).strip("'\"")
        if ref.startswith("./"):
            continue
        if not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", ref) or not m.group(2):
            failures.append("4: .github/workflows/%s:%d uses %s%s; pin it to a full commit SHA with a # <version> comment"
                            % (fn, n, ref, "" if m.group(2) else " with no version comment"))
        else:
            pinned += 1
if not pinned:
    measurement_failed("no `uses:` found in .github/workflows, so no pin was checked")

if failures:
    for f in failures:
        print("FAIL: " + f)
    sys.exit(1)
print("OK: %d workflow uses: pinned by full SHA; preflight (%s) runs first and gates the push and the index; the hook passes the served version and refuses "
      "a v-prefix, a two-part version, another version, mixed examples and a moved digest" % (pinned, ", ".join(
          "%s@%s # %s" % (k, v[0][:7], v[1]) for k, v in sorted(uses.items()))))
