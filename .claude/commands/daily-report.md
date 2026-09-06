---
description: Run the daily test-result report and draft the reminder for the team
argument-hint: <path to the downloaded .xlsx>
allowed-tools: Bash(.venv/bin/python -m testmgmt:*), Read
---

Run the daily test reporting flow for the workbook at: $1

1. Run `.venv/bin/python -m testmgmt report "$1"`.
2. Read `output/report-<today>.json` for the structured findings.
3. Show me the Markdown report as-is — do not re-summarise or re-count anything
   in it. The numbers in that file are the answer; your job is not to recompute them.
4. Then draft a reminder message for the team, following these rules:
   - Group by PIC. Each person gets their own short block.
   - For each item give: the test case file, the status, the cell reference, and
     exactly how many cases still need a ticket.
   - Keep it factual and neutral in tone — this is a nudge, not a reprimand.
   - Call out `format_error` findings separately and quote the offending line, so
     the person can see what to fix. The expected format is `TICKET-123: 2`.
   - Call out `over_attributed` findings as "note may be stale", not as an error.
   - If `notes.unreadable` is true in the JSON, STOP and tell me the notes could
     not be read instead of drafting a reminder — the findings would be false.
5. Present the draft for review. Do not post it anywhere.
