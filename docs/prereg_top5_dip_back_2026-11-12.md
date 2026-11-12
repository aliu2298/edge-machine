# Top-5 goalless dip: back in Production (2026-11-12)

Olu's call, 2026-11-12: top-5 goalless dip goes back to Production, live at the default stake, on a fresh record.

- **Rule:** version 1, unchanged. Over 1.5 goals in the five big leagues and the Champions League; an hour before kickoff read the YES ask P; from kickoff rest one post-only YES bid at 55% of P; on a fill, a resting sale at P; an unsold position is held to settlement. No change to the engine, the held-fill rule or the 55% bid.
- **Gate:** rule 1 (honest return above zero) passes on its own record: +7.7% on 32. Rule 2 (the evidence test) is waived by Olu on the lane's gate record, dated 2026-11-12, accepting the replay as the evidence: 566 honest fills, +16.0%, score 4.2, both halves up (docs/top5_dip_review_2026-11-12.md).
- **Record:** the live record starts fresh from 2026-11-12. The first Production run (2026-11-05 to 2026-11-08, 12 live fills, -9.4%) stays on the page as history.
- **Stake:** the default. No raised stake.

## Forward check (from the review's build spec)

Top-5 goalless dip, version 1, unchanged, from Nov 20 2026. Read once at 100 honest fills counted from Nov 20.

- Retire if the honest return on those 100 fills is zero or below.
- Keep if it is above zero. A score of 2 is not expected at 100 fills and is not required.
- Also record the share of fills where the price did not fall a further 5c within ten minutes. Under 15% on those 100 fills means the source of the profit has gone, and the lane is reviewed again whatever its return.
- No league or price band is dropped or added before that read.
