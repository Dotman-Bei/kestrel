*HIGH* policy violation — `pii-reaches-bi`

healthcare.raw.patients.ssn reaches Dashboard/Chart 'patient_overview' via a 4-hop path, with no mask/hash/sha2 (+4 more) step on the way.

Owner: dana.okoro
Path: `patients.ssn -> stg_patients.ssn -> patient_encounters.patient_ssn -> encounter_summary.patient_ssn -> patient_overview`
Asset: http://localhost:9002/dataset/urn%3Ali%3Adataset%3A%28urn%3Ali%3AdataPlatform%3Apostgres%2Chealthcare.raw.patients%2CPROD%29/Schema
Finding: `pii-reaches-bi-82fa8982`