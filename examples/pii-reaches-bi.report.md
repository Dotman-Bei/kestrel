# Kestrel scan report

- **Run:** `kestrel-example-run`
- **Mode:** offline (fixture graph — not a live instance)
- **Started:** 2026-08-06T05:36:58+00:00
- **Policies evaluated:** 4
- **Subjects scanned:** 15
- **Lineage paths walked:** 18
- **Violations:** 6
- **By severity:** high 4, medium 2

## Findings

### `pii-reaches-bi` — healthcare.raw.claims.member_dob -> claims_by_age

**HIGH** · finding `pii-reaches-bi-15dc0b3c`

healthcare.raw.claims.member_dob reaches Dashboard/Chart 'claims_by_age' via a 2-hop path, with no mask/hash/sha2 (+4 more) step on the way.

```
claims.member_dob -> claims_enriched.member_dob -> claims_by_age
```

<details><summary>Evidence</summary>

```
hop 1: claims.member_dob -> claims_enriched.member_dob
    transform: passthrough
    sql: CREATE TABLE healthcare.marts.claims_enriched AS SELECT claim_id, member_dob, amount FROM healthcare.raw.claims
hop 2: claims_enriched.member_dob -> claims_by_age  [table-level]
    transform: Looker explore: claims_enriched
column lineage unavailable at this hop; followed table-level lineage
```

</details>

**Written back to DataHub:**

- `tag` → tagged `claims.member_dob` with `policy-violation` (applied)
- `tag` → tagged exposure point `claims_by_age` with `policy-violation` (applied)
- `structured_property` → recorded `io.kestrel.policy_violation` on `claims.member_dob` (applied)
- `document` → authored incident document "Policy violation: pii-reaches-bi - healthcare.raw.claims.member_dob -> claims_by_age" (applied)
- `notify` → drafted owner ping for sam.reyes -> out/examples-scratch/actions/pii-reaches-bi-15dc0b3c.notify.md (dry-run)

**Fix:** Mask or hash the column at the first transform downstream of the source, or drop it from the downstream model. If the exposure is reviewed and accepted, tag the mitigating step `Masked` so this policy stops reporting the path.

### `pii-reaches-bi` — healthcare.raw.legacy_billing.member_ssn -> revenue_ops

**HIGH** · finding `pii-reaches-bi-6580a708`

healthcare.raw.legacy_billing.member_ssn reaches Dashboard/Chart 'revenue_ops' via a 2-hop path, with no mask/hash/sha2 (+4 more) step on the way.

```
legacy_billing.member_ssn -> billing_rollup -> revenue_ops
```

<details><summary>Evidence</summary>

```
hop 1: legacy_billing.member_ssn -> billing_rollup  [table-level]
    transform: nightly rollup job
    sql: INSERT INTO healthcare.marts.billing_rollup SELECT invoice_id, member_ssn, amount_due FROM healthcare.raw.legacy_billing
hop 2: billing_rollup -> revenue_ops  [table-level]
    transform: Looker explore: billing_rollup
column lineage unavailable at this hop; followed table-level lineage
```

</details>

**Written back to DataHub:**

- `tag` → tagged `legacy_billing.member_ssn` with `policy-violation` (applied)
- `tag` → tagged exposure point `revenue_ops` with `policy-violation` (applied)
- `structured_property` → recorded `io.kestrel.policy_violation` on `legacy_billing.member_ssn` (applied)
- `document` → authored incident document "Policy violation: pii-reaches-bi - healthcare.raw.legacy_billing.member_ssn -> revenue_ops" (applied)
- `notify` → drafted owner ping for morgan.diallo -> out/examples-scratch/actions/pii-reaches-bi-6580a708.notify.md (dry-run)

**Fix:** Mask or hash the column at the first transform downstream of the source, or drop it from the downstream model. If the exposure is reviewed and accepted, tag the mitigating step `Masked` so this policy stops reporting the path.

### `pii-reaches-bi` — healthcare.raw.patients.ssn -> patient_overview

**HIGH** · finding `pii-reaches-bi-82fa8982`

healthcare.raw.patients.ssn reaches Dashboard/Chart 'patient_overview' via a 4-hop path, with no mask/hash/sha2 (+4 more) step on the way.

```
patients.ssn -> stg_patients.ssn -> patient_encounters.patient_ssn -> encounter_summary.patient_ssn -> patient_overview
```

<details><summary>Evidence</summary>

```
hop 1: patients.ssn -> stg_patients.ssn
    transform: passthrough
    sql: INSERT INTO healthcare.staging.stg_patients SELECT patient_id, ssn, full_name FROM healthcare.raw.patients
hop 2: stg_patients.ssn -> patient_encounters.patient_ssn
    transform: join on patient_id
    sql: CREATE TABLE healthcare.marts.patient_encounters AS SELECT e.encounter_id, p.ssn AS patient_ssn, e.provider_id, e.encounter_date FROM encounters e JOIN healthca
hop 3: patient_encounters.patient_ssn -> encounter_summary.patient_ssn
    transform: passthrough into reporting view
    sql: CREATE VIEW healthcare.analytics.encounter_summary AS SELECT patient_ssn, COUNT(*) AS encounters, encounter_date FROM healthcare.marts.patient_encounters GROUP 
hop 4: encounter_summary.patient_ssn -> patient_overview  [table-level]
    transform: Looker explore: encounter_summary
column lineage unavailable at this hop; followed table-level lineage
```

</details>

**Written back to DataHub:**

- `tag` → tagged `patients.ssn` with `policy-violation` (applied)
- `tag` → tagged exposure point `patient_overview` with `policy-violation` (applied)
- `structured_property` → recorded `io.kestrel.policy_violation` on `patients.ssn` (applied)
- `document` → authored incident document "Policy violation: pii-reaches-bi - healthcare.raw.patients.ssn -> patient_overview" (applied)
- `notify` → drafted owner ping for dana.okoro -> out/examples-scratch/actions/pii-reaches-bi-82fa8982.notify.md (dry-run)

**Fix:** Mask or hash the column at the first transform downstream of the source, or drop it from the downstream model. If the exposure is reviewed and accepted, tag the mitigating step `Masked` so this policy stops reporting the path.

### `stale-upstream-feeds-live` — healthcare.marts.patient_360 -> lab_results

**HIGH** · finding `stale-upstream-feeds-live-f1771ba2`

healthcare.marts.patient_360 is certified but depends on healthcare.raw.lab_results, which is tagged Stale/Deprecated/Quality:Failed, 2 hops upstream.

```
patient_360 -> stg_labs -> lab_results
```

<details><summary>Evidence</summary>

```
hop 1: stg_labs <- patient_360  [table-level]
    transform: latest result per patient
hop 2: lab_results <- stg_labs  [table-level]
    transform: cleanse + dedupe
column lineage unavailable at this hop; followed table-level lineage
```

</details>

**Written back to DataHub:**

- `tag` → tagged `patient_360` with `policy-violation` (applied)
- `tag` → tagged exposure point `lab_results` with `policy-violation` (applied)
- `structured_property` → recorded `io.kestrel.policy_violation` on `patient_360` (applied)
- `document` → authored incident document "Policy violation: stale-upstream-feeds-live - healthcare.marts.patient_360 -> lab_results" (applied)
- `pr` → drafted remediation PR -> out/examples-scratch/actions/stale-upstream-feeds-live-f1771ba2.pr.md (dry-run)

**Fix:** Refresh or repair the flagged upstream before it feeds a certified asset, or drop the certification until the dependency is healthy. If the upstream is being retired, cut the dependency rather than inheriting its decay.

### `certified-dashboard-without-owner` — patient_overview

**MEDIUM** · finding `certified-dashboard-without-owner-3f2ac5ca`

patient_overview is marked Certified but has no owner. Nobody is accountable for it.

<details><summary>Evidence</summary>

```
entity: urn:li:dashboard:(looker,patient_overview)
tags: Certified
owners: none
```

</details>

**Written back to DataHub:**

- `tag` → tagged `patient_overview` with `policy-violation` (applied)
- `structured_property` → recorded `io.kestrel.policy_violation` on `patient_overview` (applied)
- `document` → authored incident document "Policy violation: certified-dashboard-without-owner - patient_overview" (applied)

**Fix:** Assign an owner to the dashboard, or drop its certification.

### `certified-without-owner` — healthcare.marts.patient_encounters

**MEDIUM** · finding `certified-without-owner-47a9eab9`

healthcare.marts.patient_encounters is marked Certified / Production but has no owner. Nobody is accountable for it.

<details><summary>Evidence</summary>

```
entity: urn:li:dataset:(urn:li:dataPlatform:snowflake,healthcare.marts.patient_encounters,PROD)
tags: Certified, Production
owners: none
```

</details>

**Written back to DataHub:**

- `tag` → tagged `patient_encounters` with `policy-violation` (applied)
- `structured_property` → recorded `io.kestrel.policy_violation` on `patient_encounters` (applied)
- `document` → authored incident document "Policy violation: certified-without-owner - healthcare.marts.patient_encounters" (applied)

**Fix:** Assign a technical and a business owner in DataHub, or remove the certification until someone will stand behind it.

## Scan notes

- patients.email: path suppressed -- passes through masking step 'stg_patients_masked.email_masked'
- 5 hop(s) used table-level lineage because column-level lineage was not populated there

## Warnings

- generated from fixtures/healthcare.json, not a live DataHub -- the shapes are real, the instance is not
