## Remediate `stale-upstream-feeds-live`: healthcare.marts.patient_360 -> lab_results

healthcare.marts.patient_360 is certified but depends on healthcare.raw.lab_results, which is tagged Stale/Deprecated/Quality:Failed, 2 hops upstream.

Detected by Kestrel Policy Sentinel (`stale-upstream-feeds-live-f1771ba2`) at 2026-08-06T05:36:58+00:00.

### Path

```
patient_360 -> stg_labs -> lab_results
```

### Proposed change

Refresh or repair the flagged upstream before it feeds a certified asset, or drop the certification until the dependency is healthy. If the upstream is being retired, cut the dependency rather than inheriting its decay.

Asset in DataHub: http://localhost:9002/dataset/urn%3Ali%3Adataset%3A%28urn%3Ali%3AdataPlatform%3Asnowflake%2Chealthcare.marts.patient_360%2CPROD%29

---

_Opened by Kestrel Policy Sentinel. Close this PR to accept the exposure; amend the policy if the rule itself is wrong._