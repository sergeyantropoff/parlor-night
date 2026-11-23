{{- define "parlor.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "parlor.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "parlor.secretName" -}}
{{- if .Values.existingSecret }}
{{- .Values.existingSecret }}
{{- else }}
{{- printf "%s-env" (include "parlor.fullname" .) }}
{{- end }}
{{- end }}

{{- define "parlor.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "parlor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: parlor-night
{{- end }}

{{- define "parlor.selector" -}}
app.kubernetes.io/name: {{ include "parlor.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "parlor.tlsSecret" -}}
{{- $root := .root -}}
{{- if and $root.Values.turn.enabled (eq .host $root.Values.turn.host) -}}
{{- include "parlor.fullname" $root }}-tls
{{- else -}}
{{- include "parlor.fullname" $root }}-tls-{{ .host | replace "." "-" }}
{{- end -}}
{{- end }}

{{- define "parlor.trustedHosts" -}}
{{- $hosts := .Values.web.trustedHosts }}
{{- if .Values.ingress.host }}
{{- $hosts = printf "%s,%s" $hosts .Values.ingress.host }}
{{- end }}
{{- range .Values.ingress.extraHosts }}
{{- $hosts = printf "%s,%s" $hosts . }}
{{- end }}
{{- $hosts }}
{{- end }}
