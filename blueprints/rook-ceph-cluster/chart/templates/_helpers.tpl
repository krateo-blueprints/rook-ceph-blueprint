{{/*
ceph.validate: refuse values that cannot make a working cluster, naming the value. Rendered first (cluster.yaml).
*/}}
{{- define "ceph.validate" -}}
{{- $v := .Values -}}
{{- if not $v.consumer.namespace -}}
{{- fail "\n\nconsumer.namespace is empty: name the namespace of the Openstack Composition that consumes this cluster. Its copy store's ServiceAccount (consumer.serviceAccount) is granted get on exactly the client Secrets and rook-ceph-config, and on nothing else.\n" -}}
{{- end -}}
{{- if eq $v.osd.source "devices" -}}
{{- if or (not $v.osd.devices.nodeLabel.key) (not $v.osd.devices.deviceFilter) -}}
{{- fail "\n\nosd.source is devices, and osd.devices.nodeLabel.key or osd.devices.deviceFilter is empty: name the label of the storage nodes and a regular expression over their raw device names (for example ^nvme[0-9]+n[1-9]$). Rook would otherwise consume no disk, or every empty disk on every node.\n" -}}
{{- end -}}
{{- else if eq $v.osd.source "storageClass" -}}
{{- if not $v.osd.storageClass.name -}}
{{- fail "\n\nosd.source is storageClass and osd.storageClass.name is empty: name a StorageClass that serves volumeMode Block.\n" -}}
{{- end -}}
{{- else -}}
{{- fail (printf "\n\nosd.source %q: devices or storageClass.\n" $v.osd.source) -}}
{{- end -}}
{{- if not $v.testOnly -}}
{{- if lt (int $v.replication.size) 3 -}}
{{- fail (printf "\n\nreplication.size %d: below 3 a single lost failure domain stops writes or loses data. Set testOnly: true for a throwaway cluster.\n" (int $v.replication.size)) -}}
{{- end -}}
{{- if lt (int $v.mon.count) 3 -}}
{{- fail (printf "\n\nmon.count %d: below 3 the monitors have no quorum to survive a loss. Set testOnly: true for a throwaway cluster.\n" (int $v.mon.count)) -}}
{{- end -}}
{{- end -}}
{{- if eq (mod (int $v.mon.count) 2) 0 -}}
{{- fail (printf "\n\nmon.count %d is even: an even monitor count tolerates no more failures than one fewer. Use an odd count.\n" (int $v.mon.count)) -}}
{{- end -}}
{{- if not (or $v.pools.volumes.enabled $v.pools.images.enabled) -}}
{{- fail "\n\nNo pool is enabled: enable pools.volumes (cinder) or pools.images (glance).\n" -}}
{{- end -}}
{{- /*
Rook v1.21 names a pool after its CephBlockPool's metadata.name: its CRD admits spec.name only for Ceph's built-in
pools (.mgr, .nfs, .nvmeof, .rgw.root). So each pool name must be a Kubernetes object name, and no two may be equal.
*/ -}}
{{- $seen := dict -}}
{{- range $role := list "volumes" "images" "vms" -}}
{{- $p := index $v.pools $role -}}
{{- if $p.enabled -}}
{{- if or (gt (len $p.name) 253) (not (regexMatch "^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$" $p.name)) -}}
{{- fail (printf "\n\npools.%s.name %q: Rook names the Ceph pool after its CephBlockPool object, so the name must be a Kubernetes object name (lowercase letters, digits, '-' and '.', starting and ending with a letter or digit, at most 253 characters).\n" $role $p.name) -}}
{{- end -}}
{{- if hasKey $seen $p.name -}}
{{- fail (printf "\n\npools.%s.name %q is also pools.%s.name: two roles cannot share one pool object.\n" $role $p.name (get $seen $p.name)) -}}
{{- end -}}
{{- $_ := set $seen $p.name $role -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/* (dict "key" k "value" v): a required node affinity on one label, as YAML, or nothing when key is empty. */}}
{{- define "ceph.nodeAffinity" -}}
{{- if .key -}}
requiredDuringSchedulingIgnoredDuringExecution:
  nodeSelectorTerms:
    - matchExpressions:
        - key: {{ .key | quote }}
          operator: In
          values:
            - {{ .value | quote }}
{{- end -}}
{{- end -}}

{{/*
ceph.clientCaps (list $ "cinder"|"glance"): the caps of that client, as YAML. From the Ceph documentation, "Block
Devices and OpenStack": cinder writes volumes (and vms, nova's ephemeral disks) and reads images, to clone them; glance
writes images. Every osd and mgr cap names a pool: none is a bare `profile rbd`.
*/}}
{{- define "ceph.clientCaps" -}}
{{- $v := (index . 0).Values -}}{{- $who := index . 1 -}}
{{- $osd := list -}}{{- $mgr := list -}}
{{- if eq $who "cinder" -}}
{{- if $v.pools.volumes.enabled -}}{{- $osd = append $osd (printf "profile rbd pool=%s" $v.pools.volumes.name) -}}{{- $mgr = append $mgr (printf "profile rbd pool=%s" $v.pools.volumes.name) -}}{{- end -}}
{{- if $v.pools.vms.enabled -}}{{- $osd = append $osd (printf "profile rbd pool=%s" $v.pools.vms.name) -}}{{- $mgr = append $mgr (printf "profile rbd pool=%s" $v.pools.vms.name) -}}{{- end -}}
{{- if $v.pools.images.enabled -}}{{- $osd = append $osd (printf "profile rbd-read-only pool=%s" $v.pools.images.name) -}}{{- end -}}
{{- else -}}
{{- $osd = append $osd (printf "profile rbd pool=%s" $v.pools.images.name) -}}{{- $mgr = append $mgr (printf "profile rbd pool=%s" $v.pools.images.name) -}}
{{- end -}}
mon: "profile rbd"
osd: {{ join ", " $osd | quote }}
mgr: {{ join ", " $mgr | quote }}
{{- end -}}
