{{/*
Expand the name of the chart.
*/}}
{{- define "spheraform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "spheraform.fullname" -}}
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

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "spheraform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "spheraform.labels" -}}
helm.sh/chart: {{ include "spheraform.chart" . }}
{{ include "spheraform.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "spheraform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "spheraform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
PostgreSQL connection string
*/}}
{{- define "spheraform.postgres.connectionString" -}}
postgresql://{{ .Values.postgres.username }}:{{ .Values.postgres.password }}@{{ include "spheraform.fullname" . }}-postgres:5432/{{ .Values.postgres.database }}
{{- end }}

{{/*
Database URL for API (psycopg format)
*/}}
{{- define "spheraform.api.databaseUrl" -}}
postgresql+psycopg://{{ .Values.postgres.username }}:{{ .Values.postgres.password }}@{{ include "spheraform.fullname" . }}-postgres:5432/{{ .Values.postgres.database }}
{{- end }}
