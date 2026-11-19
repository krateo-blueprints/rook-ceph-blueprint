{{/*
Preconditions: the CustomResourceDefinitions this chart's objects need before they can work.

ceph.preconditions.crdServed: "true" when the named CRD is served. A named GET per CRD, never a list.
hack/validate-render.py replaces the line marked GATE-LOOKUP with stand-in answers to drive the refusal; keep the
lookup on that one line.
*/}}
{{- define "ceph.preconditions.crdServed" -}}
{{- if lookup "apiextensions.k8s.io/v1" "CustomResourceDefinition" "" . }}true{{ end -}}{{- /* GATE-LOOKUP */ -}}
{{- end -}}

{{/*
ceph.preconditions.require (list $ $needed $why): refuse to render while any CRD in $needed is not served, naming
each absent one and what installs it.

Measured only on a live cluster: core-provider's own CRD (compositiondefinitions.core.krateo.io) is the witness. Where
it is not found the render is offline (helm template, the gates), nothing can be checked there, and nothing is
refused. `fail` rather than a warning: composition-dynamic-controller puts a render error on the Composition's status,
where the operator is already looking, while the objects it would otherwise create (cert-manager Certificates and
Issuers, webhooks whose CA cert-manager injects) fail later and elsewhere.
*/}}
{{- define "ceph.preconditions.require" -}}
{{- $top := index . 0 -}}{{- $needed := index . 1 -}}{{- $why := index . 2 -}}
{{- if include "ceph.preconditions.crdServed" "compositiondefinitions.core.krateo.io" -}}
{{- $absent := list -}}
{{- range $n := $needed -}}
{{- if not (include "ceph.preconditions.crdServed" $n) -}}{{- $absent = append $absent $n -}}{{- end -}}
{{- end -}}
{{- if $absent -}}
{{- fail (printf "\n\n%s needs CustomResourceDefinitions this cluster does not serve: %s.\n\n%s\n\nThis render proceeds by itself on the next reconcile once they are served; nothing has to be re-run.\n" $top.Chart.Name (join ", " $absent) $why) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
ceph.preconditions.requireClusterRBAC: on a live cluster, refuse unless Rook's per-cluster RBAC is in this namespace.
The rook-operator chart renders it in its own namespace (common.yaml's rook-ceph-osd, -mgr, -cmd-reporter and
-purge-osd ServiceAccounts and Roles), so a CephCluster in any other namespace has daemons with no identity. One named
GET of the rook-ceph-osd ServiceAccount. Offline (no core-provider CRD) nothing is checked. The line marked
GATE-LOOKUP-SA is replaced by hack/validate-render.py.
*/}}
{{- define "ceph.preconditions.saServed" -}}
{{- if lookup "v1" "ServiceAccount" .ns .name }}true{{ end -}}{{- /* GATE-LOOKUP-SA */ -}}
{{- end -}}

{{- define "ceph.preconditions.requireClusterRBAC" -}}
{{- if include "ceph.preconditions.crdServed" "compositiondefinitions.core.krateo.io" -}}
{{- if not (include "ceph.preconditions.saServed" (dict "ns" .Release.Namespace "name" "rook-ceph-osd")) -}}
{{- fail (printf "\n\nThis namespace (%s) has no ServiceAccount rook-ceph-osd: Rook's per-cluster RBAC is rendered by the rook-operator chart in its own namespace, and this CephCluster's daemons would have no identity here. Install rook-ceph-cluster in the rook-operator's namespace.\n" .Release.Namespace) -}}
{{- end -}}
{{- end -}}
{{- end -}}
