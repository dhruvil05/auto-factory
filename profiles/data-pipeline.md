<!-- Profile for ETL/analytics/ML data pipelines. Replace the [bracketed] parts. -->
## Factory profile

### What this project is
- [Pipeline name]: moves [source data] from [sources] into [warehouse/lake/model] for [who uses it].
- Runs on [Airflow/dbt/Spark/cron], [schedule].

### Users and roles
None

### Sensitive areas
Always goes to a human:
- Schema changes to any output table or file other teams read.
- Backfills and reruns over more than [N days / N GB].
- Deleting, truncating or overwriting data.
- PII: new columns, joins or exports containing personal data.
- Anything that raises compute or storage cost (new jobs, larger schedules).
- Model training data or metrics that drive decisions.

### Authorization
- Access: [warehouse roles/IAM] in [infra path]; jobs run as [service account].
- Verify by: [query showing PII columns are masked for the analyst role].

### Data rules
- Runs are idempotent: rerunning a partition replaces it, never duplicates.
- Partition by [date column]; backfills run per partition with [command].
- Schemas: declared in [path]; additive changes only, old columns kept until consumers move.
- Data quality checks in [path]: not-null keys, uniqueness, row counts vs previous run.
- PII: [columns] hashed or masked at ingest; raw kept [N days] in [location].
- Timestamps in UTC.

### UI conventions
No UI

### Verify
- Run: [test command]; [single-partition run on sample data command].
- Check: output row counts and quality checks pass on [sample dataset path].

### Terms
- [Partition]: [one day of data, by event date]
- [Term]: [meaning]
