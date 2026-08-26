## Approval

`architecture.md` reviewed and approved by the user on 2026-08-26,
after two rounds of corrections during review:
- Custom data type names switched to natural spacing (e.g. "GitHub
  Activity Raw") instead of PascalCase.
- "Notability Signal" corrected from `MomentAnnotation` to
  `NumericAnnotation`, using the real `value` field for the computed
  score, with `note` retained alongside it for baseline-comparison
  detail (value and note are not mutually exclusive on a metric-class
  type).

No further changes requested. Proceeding to Plan.
