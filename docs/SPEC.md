# Product Spec

## APIs
- `POST /analysis/run`
  - Input: `username`, `scope(public|private|hybrid)`, `honesty_mode(conservative|balanced)`, `output_targets`, `include_private`.
  - Output: `analysis_id`, `status`.
- `GET /analysis/{id}/status`
- `GET /analysis/{id}/signals`
- `GET /analysis/{id}/readme`
- `GET /analysis/{id}/report`

## Contracts

### Signal
- `name`
- `value`
- `confidence` (0..1)
- `evidence_refs[]`
- `timeframe`

### Archetype
- `top_archetype`
- `alternates[]`
- `confidence`
- `supporting_evidence[]`

### README Integrity
- Each generated claim section must include one or more `evidence_refs`.

## Honesty Modes
- Conservative: stricter tone and explicit uncertainty language.
- Balanced: allows mild inference expansion while preserving evidence mapping.

## v1 Defaults
- Honesty mode default is conservative.
- Public data supported by default; private analysis optional via consented mode.
