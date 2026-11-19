#!/usr/bin/env python3
"""Every chart push goes through the organisation's chart-push action, pinned by commit, and none is bare.

    hack/validate-chart-push.py [repo-root]

krateo-blueprints/charts PUBLISHING.md rule 14: charts are pushed only through
krateo-platformops/.github/.github/actions/chart-push, whose push.sh retries GHCR's tag read-after-write race
(`failed to perform "Tag" on destination: sha256:<digest>: not found` after an accepted PUT) and nothing else, and fails
if the re-push would tag another digest. This repository used to carry its own copy (hack/push-chart.sh, PR #4); one
implementation replaced it. In .github/workflows/*.y*ml:

  1. No bare push: an uncommented line running `helm push` or `oras push` is refused. A YAML or shell comment line is
     not a push.
  2. The action pinned: every `uses:` of that action is a 40-hex commit with `# main YYYY-MM-DD` (the transitional form
     while krateo-platformops/.github is untagged) or `# X.Y.Z`. Never `@main`, a tag or an abbreviated SHA.
  3. Locate mode wired: a step that runs `bash "${CHART_PUSH}"` sets CHART_PUSH to the `path` output of an earlier
     chart-push step in the same job. (Push mode, `with: chart:`, needs no wiring.)
  4. Something pushes through it: no chart-push step at all fails, since a check that found nothing checked nothing.
  5. The copy is gone: a file named push-chart.sh or validate-push-chart.py anywhere in the repository is refused, so
     the old copy (PR #4, deleted in #5) cannot come back beside the one implementation.

Before reading the workflows it runs a self-test: planted workflows that each break one rule must be refused, for that
rule's reason, and the accepted forms (locate mode, push mode, a commented push) must pass.

Fails (exit 2) when PyYAML is missing or there is no workflow.
"""
import glob
import os
import re
import sys

try:
    import yaml
except ImportError:
    print("FAILED MEASUREMENT: PyYAML unavailable, so nothing was read")
    sys.exit(2)

ACTION = "krateo-platformops/.github/.github/actions/chart-push"
SHA = "653ac1e67d761584993a774c76963514968b3650"
PUSH = re.compile(r"""(^|[\s;&|(`'"])(helm|oras)\s+push\b""")
USES = re.compile(r"""^\s*(?:-\s+)?uses:\s*(['"]?)([^'"\s#]+)\1\s*(?:#\s*(.*?))?\s*$""")
COMMENT = re.compile(r"^(main \d{4}-\d{2}-\d{2}|\d+\.\d+\.\d+)$")
CALL = re.compile(r"""bash\s+"?\$\{?CHART_PUSH\}?"?""")


def problems(name, text):
    out = []
    lines = text.split("\n")
    for n, line in enumerate(lines, 1):
        if line.lstrip().startswith("#"):
            continue
        m = PUSH.search(line)
        if m:
            out.append("%s:%d: a bare `%s push`; push through %s (PUBLISHING.md rule 14)" % (name, n, m.group(2), ACTION))
        u = USES.match(line)
        if u and u.group(2).split("@", 1)[0].lower() == ACTION:
            ref = u.group(2).rpartition("@")[2] if "@" in u.group(2) else ""
            if not re.fullmatch(r"[0-9a-f]{40}", ref) or not COMMENT.match((u.group(3) or "").strip()):
                out.append("%s:%d: %s is not pinned `@<40-hex sha> # main YYYY-MM-DD` (or `# X.Y.Z`)" % (name, n, u.group(2)))
    try:
        wf = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        return out + ["%s: does not parse: %s" % (name, e)], 0
    found = 0
    for jname, job in (wf.get("jobs") or {}).items():
        steps = job.get("steps") or []
        located = []
        for i, st in enumerate(steps):
            u = str(st.get("uses") or "")
            if u.split("@", 1)[0].lower() == ACTION:
                found += 1
                if st.get("id"):
                    located.append("${{ steps.%s.outputs.path }}" % st["id"])
            if CALL.search(str(st.get("run") or "")):
                if str((st.get("env") or {}).get("CHART_PUSH")) not in located:
                    out.append("%s: job %s step %d runs ${CHART_PUSH} without CHART_PUSH set from an earlier chart-push "
                               "step's path output" % (name, jname, i))
    return out, found


OLD_COPY = ("push-chart.sh", "validate-push-chart.py")


def check(files, present=()):
    out, found = [], 0
    for path in present:
        if os.path.basename(path) in OLD_COPY:
            out.append("%s is a copy of the chart push; push through %s instead (PUBLISHING.md rule 14)" % (path, ACTION))
    for name, text in files.items():
        p, f = problems(name, text)
        out += p
        found += f
    if not found:
        out.append("no workflow pushes through %s, so no chart push was checked" % ACTION)
    return out


PIN = "%s@%s # main 2026-11-18" % (ACTION, SHA)
LOCATE = """on: push
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - name: Locate the shared chart push
        id: chart-push
        uses: %s
      - name: Push every chart
        env:
          CHART_PUSH: ${{ steps.chart-push.outputs.path }}
        run: |
          for tgz in dist/*.tgz; do
            # was: helm push "$tgz" "${OCI_REPO}"
            bash "${CHART_PUSH}" "$tgz" "${OCI_REPO}"
          done
""" % PIN
PUSH_MODE = """on: push
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      # - run: helm push old.tgz oci://ghcr.io/x/charts
      - name: Push the chart
        uses: %s
        with:
          chart: dist/demo-0.1.0.tgz
          repository: oci://ghcr.io/krateo-blueprints/charts
          registry-username: ${{ github.actor }}
          registry-password: ${{ secrets.GITHUB_TOKEN }}
""" % PIN
REFUSED = [
    ("a planted bare helm push", LOCATE.replace('bash "${CHART_PUSH}" "$tgz"', 'helm push "$tgz"'), "a bare `helm push`"),
    ("a planted bare helm push beside the action", LOCATE + "  other:\n    runs-on: ubuntu-latest\n    steps:\n      - run: helm package . && helm push x.tgz oci://r/p\n",
     "a bare `helm push`"),
    ("a planted bare oras push", LOCATE.replace('bash "${CHART_PUSH}" "$tgz"', 'oras push "$tgz"'), "a bare `oras push`"),
    ("the action at @main", LOCATE.replace("@%s # main 2026-11-18" % SHA, "@main"), "is not pinned"),
    ("the action with no comment", LOCATE.replace(" # main 2026-11-18", ""), "is not pinned"),
    ("the action at an abbreviated sha", LOCATE.replace(SHA, SHA[:7]), "is not pinned"),
    ("CHART_PUSH from nowhere", LOCATE.replace("${{ steps.chart-push.outputs.path }}", "/tmp/push.sh"), "without CHART_PUSH set"),
    ("no chart push at all", "on: push\njobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n", "no workflow pushes through"),
    ("the old copy back", LOCATE, "hack/push-chart.sh is a copy of the chart push", ("hack/push-chart.sh",)),
    ("the old validator back", LOCATE, "hack/validate-push-chart.py is a copy of the chart push", ("hack/validate-push-chart.py",)),
]
ACCEPTED = [("locate mode, a commented push", LOCATE), ("push mode, a commented push", PUSH_MODE)]


def self_test():
    bad = []
    for label, text, why, *present in REFUSED:
        got = check({"planted.yaml": text}, present[0] if present else ())
        if not any(why in g for g in got):
            bad.append("%s: not refused for %r (got %s)" % (label, why, got or "nothing"))
    for label, text in ACCEPTED:
        got = check({"planted.yaml": text})
        if got:
            bad.append("%s: refused: %s" % (label, got))
    return bad


root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
bad = self_test()
if bad:
    for b in bad:
        print("FAIL: self-test: " + b)
    sys.exit(1)
paths = sorted(glob.glob(os.path.join(root, ".github", "workflows", "*.y*ml")))
if not paths:
    print("FAILED MEASUREMENT: no .github/workflows/*.y*ml, so nothing was checked")
    sys.exit(2)
present = [os.path.relpath(os.path.join(d, f), root) for d, ds, fs in os.walk(root) for f in fs
           if ".git" not in os.path.relpath(d, root).split(os.sep)]
fails = check({os.path.relpath(p, root): open(p, encoding="utf-8").read() for p in paths}, present)
if fails:
    for f in fails:
        print("FAIL: " + f)
    sys.exit(1)
print("OK: self-test (%d planted breaks refused, %d accepted forms passed); %d workflow(s), every chart push through %s "
      "pinned by commit, none bare, no copy of it" % (len(REFUSED), len(ACCEPTED), len(paths), ACTION))
