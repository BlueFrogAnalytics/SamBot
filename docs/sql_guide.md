# SAMWatch SQL Guide

This guide highlights useful analytical queries against the SAMWatch SQLite database.

## Recently Posted Opportunities

```sql
SELECT notice_id, title, posted_at
FROM opportunities
WHERE datetime(posted_at) >= datetime('now', '-1 day')
ORDER BY datetime(posted_at) DESC;
```

## Opportunities Matching Pursuit Rules

```sql
SELECT o.notice_id, o.title, r.name AS rule_name, rm.matched_at
FROM rule_matches rm
JOIN opportunities o ON o.id = rm.opportunity_id
JOIN rules r ON r.id = rm.rule_id
ORDER BY rm.matched_at DESC
LIMIT 50;
```

## Attachment Counts by Agency

```sql
SELECT o.agency, COUNT(a.id) AS attachment_count
FROM opportunities o
LEFT JOIN attachments a ON a.opportunity_id = o.id
GROUP BY o.agency
ORDER BY attachment_count DESC;
```

## Recent Award Activity

```sql
SELECT o.notice_id, o.title, aw.award_type, aw.amount, aw.date
FROM awards aw
JOIN opportunities o ON o.id = aw.opportunity_id
WHERE datetime(aw.date) >= datetime('now', '-90 days')
ORDER BY datetime(aw.date) DESC;
```

## Full-Text Search

```sql
SELECT o.notice_id, o.title
FROM opportunity_search s
JOIN opportunities o ON o.id = s.rowid
WHERE opportunity_search MATCH 'cybersecurity NEAR/5 training';
```

## Failed Runs

```sql
SELECT id, kind, started_at, finished_at, status, error_message
FROM runs
WHERE status = 'failed'
ORDER BY datetime(started_at) DESC
LIMIT 20;
```

## Run Metrics Summary

```sql
SELECT r.id AS run_id, r.kind, m.metric, m.value, r.started_at
FROM run_metrics m
JOIN runs r ON r.id = m.run_id
ORDER BY datetime(r.started_at) DESC, m.metric;
```

## Recent Rule Matches

```sql
SELECT r.name AS rule_name, o.notice_id, o.title, rm.matched_at
FROM rule_matches rm
JOIN rules r ON r.id = rm.rule_id
JOIN opportunities o ON o.id = rm.opportunity_id
ORDER BY datetime(rm.matched_at) DESC
LIMIT 50;
```
