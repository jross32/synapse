# Candidate and evidence schema

Store the research artifact as JSON with this shape:

```json
{
  "request": {
    "target": "Example",
    "goal": "source|playable|both|docs|sdk",
    "cutoff_date": "2026-07-31",
    "download_authorized": false,
    "execution_authorized": false
  },
  "candidates": [],
  "evidence": [],
  "failures": []
}
```

## Candidate fields

- `id`: stable kebab-case identifier
- `name`: display name
- `artifact_kind`: `source-code`, `binary-build`, `web-playable`, `documentation`, `sdk-or-tooling`, or `community-project`
- `source_type`: `official-public`, `authorized-private`, `public-mirror`, `community-remake`, `web-build`, `tooling-sdk`, `leaked-source`, or `unknown`
- `access_mode`: `public-web`, `public-git`, `authenticated-git`, `authenticated-web`, `artifact-download`, or `manual-only`
- `upstream_url`: canonical URL
- `version_label`: release, tag, commit, branch, or build identifier
- `release_date`: ISO date when verified
- `license`: SPDX id or explicit proprietary/unknown label
- `engine_or_runtime`: detected runtime
- `source_status`: `public-source-found`, `authorized-source-path-required`, `no-source-found`, `build-only`, or `metadata-only`
- `availability_model`: `free`, `paid`, `owned`, `restricted`, or `unknown`
- `provenance_confidence`: `high`, `medium`, or `low`
- `acquisition_allowed`: boolean
- `acquisition_reason`: concise evidence-backed reason
- `confirmation_required`: boolean
- `confirmation_reason`: reason for pausing
- `user_confirmed`: boolean
- `authorization_claimed`: boolean
- `authorization_basis`: user/team access basis
- `authorized_access_path`: usable authorized Git, portal, artifact, or signed-in-session path
- `playable_potential`: `ready`, `likely`, `unclear`, or `unlikely`
- `checksum`: verified digest when available
- `reproduction_steps`: exact, pinned steps
- `evidence_ids`: links to evidence records
- `fallback_action`: best legal next step
- `notes`: short classification explanation

## Evidence fields

- `id`: stable identifier
- `url`: direct supporting page or API endpoint
- `source_class`: `primary` or `secondary`
- `observed_at`: UTC timestamp
- `claim`: one claim supported by this record
- `observed_fact`: paraphrased fact; avoid excessive quoting
- `version_or_date`: value extracted from the source
- `content_hash`: optional capture hash
- `tool`: tool used to observe it

## Policy invariants

- `leaked-source` is always metadata-only and never acquirable.
- `authorized-private` requires a usable authorized access path.
- Confirmation can allow an already-permitted action; it cannot override `acquisition_allowed: false`.
- Missing/unclear licensing blocks acquisition unless an official distribution or user-owned private path supplies a clear basis.
- Discovery permission does not imply download permission; download permission does not imply execution permission.
