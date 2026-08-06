# Agent-compiled policy

This folder holds a policy **Kestrel's agentic engine wrote itself**, from a rule
typed in plain English. It is a real artifact of a real run, kept here rather
than in `policies/` so the shipped rule set stays fixed.

## What was typed

```bash
kestrel scan --ask "no dashboard should depend on a deprecated table" \
             --save-policy policies/no-deprecated-behind-bi.yaml
```

## What came back

```
interpreting: "no dashboard should depend on a deprecated table"
compiled to policy `dashboard-no-deprecated-upstream`
saved policies/no-deprecated-behind-bi.yaml
```

…and then, in the same run, the **deterministic** engine evaluated it:

```
1 VIOLATION   dashboard-no-deprecated-upstream    4 subject(s), 12 path(s)

  HIGH  revenue_ops is certified but depends on healthcare.raw.legacy_billing,
        which is tagged Deprecated, 2 hops upstream.

    revenue_ops [Dashboard] -> billing_rollup [Table] -> legacy_billing [Table]
      hop 1 [table-level]  Looker explore: billing_rollup
      hop 2 [table-level]  nightly rollup job

    owner  morgan.diallo
```

## Why this is the interesting part

The agent did not answer a question — it produced
[`dashboard-no-deprecated-upstream.yaml`](dashboard-no-deprecated-upstream.yaml),
a file you can read, edit, put in review and run every night forever. The finding
then came from the same LLM-free traversal that evaluates the shipped policies, so
it carries the same hop-by-hop evidence. The agent's judgement is spent on
*interpreting the rule*, not on deciding what counts as a violation.

For rules the DSL genuinely cannot express, the engine falls back to a second
phase where the model plans its own reads and reports what it finds — with every
tool call recorded, and reported URNs validated against the catalog so an
invented entity is rejected rather than reported.

## One thing worth noticing

Compare this finding with `pii-reaches-bi` in the main run:

| Rule | Direction | Path |
|---|---|---|
| `dashboard-no-deprecated-upstream` (compiled) | upstream from a dashboard | `revenue_ops` → `billing_rollup` → `legacy_billing` |
| `pii-reaches-bi` (shipped) | downstream from a column | `legacy_billing.member_ssn` → `billing_rollup` → `revenue_ops` |

Same three assets, walked from opposite ends. `legacy_billing` is both a
deprecated dependency *and* a live PII source, and the two rules catch it from
different directions. That is what `direction` being a modifier in the policy
language buys you.
