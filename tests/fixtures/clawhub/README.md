# ClawHub API fixtures

The JSON files in this directory are deliberately small snapshots of fields
consumed by the ClawHub adapter. They are based on the official ClawHub v1 API
and were reduced for deterministic offline tests on 2026-07-22.

Ordinary API payloads may add fields and the adapter must ignore unknown
fields. A future `public-github` download handoff fixture must instead be
strict: it is synthetic, derived from the live OpenAPI schema, and must never
be described as a live observation unless its provenance is independently
captured.
