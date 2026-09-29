# Current domain scores

Verified full-dataset scores, via `python test_harness.py --domains <name> --test`
(zero-cost re-scoring of each domain's cached `eval_sops/<name>/workflow.py`
against its complete held-out test set — not a sample). Row counts match each
domain's full `test_set_with_outputs.csv` exactly.

Recorded 2026-09-28, against commit `d92f307`.

| Domain | Rows tested | row_pass_rate |
|---|---|---|
| aircraft_inspection_sop | 112 | 1.00 |
| patient_intake_sop | 66 | 1.00 |
| email_intent_sop | 186 | 0.95 |
| dangerous_goods_sop | 274 | 0.90 |
| customer_service_sop | 156 | 0.83 |
| video_annotation_sop | 125 | 0.83 |
| know_your_business_sop | 90 | 0.60 |
| warehouse_package_inspection_sop | 150 | 0.60 |
| content_flagging_sop | 156 | 0.00 |
| video_classification_sop | 125 | 0.00 |

## Known limitations behind the two 0.00 scores

- **`content_flagging_sop`**: `user_trust_score`'s formula is mathematically
  disconnected from its own ground truth — verified by reverse-engineering
  what `device_consistency_score` would need to be to reproduce the recorded
  values, which comes out well outside its own documented 0-1 range and
  varies for identical device/OS/browser combinations. Not fixable by
  prompt/toolspec changes without inventing new business logic.
- **`video_classification_sop`**: a genuine validator-vs-SOP conflict —
  `validation_agent.py`'s own "every API-plan step must be implemented" bias
  overrides an explicit, SOP-documented conditional skip (calling
  `implementModeration` when no moderator was ever assigned crashes the
  workflow), across 7 regeneration attempts with progressively more forceful
  SOP wording. See `sop_autoresearch.md` Section 0 item 13 for the full
  writeup and the likely real fix (a `validation_agent.py` prompt change,
  not more SOP wording).

Note: `eval_sops/` itself (the fixture data — `tools.py`, `toolspecs.json`,
`sop.txt`, cached `workflow.py` per domain) is gitignored and not committed,
so these scores reflect local, uncommitted fixture fixes layered on top of
the committed agent/harness code.
