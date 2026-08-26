# Feature: Metadata-only provenance and consent

## Status
done (generator and tests); not connected to a live user session

## Description
For one explicitly opted-in Flow State session, produce a deterministic record
of the transformation from session recording and marker sample to a published
`MusicalIdea`. The evidence contains hashes and bounded processing metadata,
never audio bytes or local audio paths.

This is an optional Maha integration layer. It does not change Flow State's
existing upload of processed session audio and extracted clips to Fulcra, does
not alter Fulcra access enforcement, and does not assert creative ownership.

## Acceptance Criteria
- [x] Refuses to read/hash any audio unless consent has `opted_in: true` and the
      purpose is `metadata_only_transformation_provenance`.
- [x] Hashes the session, marker and selected derived clip with SHA-256 without
      embedding audio or filesystem paths in the record.
- [x] Binds marker timestamp, extraction window, detector, processing version,
      key/BPM estimates and the resulting `MusicalIdea` reference.
- [x] Hashes the full canonical record and detects later metadata changes.
- [x] Produces an optional share-boundary record only when sharing consent is
      not private; that record omits the session and marker digests and binds
      a hashed audience reference.
- [x] Hashes consent and audience references rather than retaining their
      caller-supplied values.
- [x] States non-claims in-band: no Fulcra enforcement attestation, creative
      ownership claim, detection guarantee, or key/BPM guarantee.
- [x] Writes metadata only to `.json`, atomically.
- [x] Has focused automated tests using synthetic byte fixtures; no Fulcra
      account, network call or real creative recording is required.

## Deferred one-session validation
The first real test requires a musician to opt in to one named session and
choose a sharing scope. The generated record should then be compared against
the actual published `MusicalIdea`. That validation must not publish audio,
session/marker digests, or claim that Maha changed Fulcra's storage policy.

## Implementation
`app/provenance.py` exposes:

- `build_musical_idea_provenance`
- `verify_musical_idea_provenance`
- `build_share_boundary_record`
- `verify_share_boundary_record`
- `write_metadata_record`

It is deliberately not invoked automatically by `pipeline.py`: consent must be
captured explicitly before a real session is read for this purpose.
