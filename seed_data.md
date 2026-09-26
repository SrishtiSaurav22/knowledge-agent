# Seed data: "Orion" vendor evaluation (fictional)

Scenario: Northwind Analytics (fictional) is deciding whether to sign a 3-year contract with
Orion DataWorks (fictional) for a log analytics platform. The data is built so the agent must
chain sources (an email names a Drive doc) and spot a conflict (Notion says Nov 1 go-live,
the latest email says Nov 15).

How to seed:
- **Emails:** send each one from your personal Gmail to the test account. The persona is in
  the signature; that's fine. Send them in this order so the dates make sense.
- **Drive:** create 3 Google Docs in the test account with the exact titles below.
- **Notion:** create the 2 pages below plus an empty page called 
- **Agent Briefs**. Then make sure all 3 are shared with the Swytchcode integration (page menu → Connections).
  Put the Agent Briefs page id in `.env` as `NOTION_PARENT_PAGE_ID` (it's the 32-char
  id at the end of the page URL).

---

## Emails

### 1. Subject: Orion proposal – revised pricing
Hi team,

Following last week's call, we've revised our commercial proposal. The full breakdown is in
the shared doc "Orion Pricing Proposal v3".

Headline: ₹48 lakh per year for up to 2 TB/day ingest with 90-day hot retention. A 3-year
commitment brings a 12% discount.

Happy to walk through it on a call.

Dana Lee
Account Executive, Orion DataWorks

### 2. Subject: Orion POC results
Team,

POC wrapped up yesterday. Summary:
- Sustained 2.1 TB/day ingest without backpressure.
- p95 query latency 1.8s against our 2s target.
- Concern: retention beyond 90 days is billed separately and isn't in the v3 pricing.

Full numbers are in the "Orion POC Report" doc. I'd rate it technically ready.

Arjun Mehta
Engineering Lead, Northwind

### 3. Subject: Orion contract – legal comments
Hi all,

Legal has finished the first pass on the MSA; redlines are in "Orion MSA Redlines". Two items
are still open:
1. Indemnity cap: Orion offers 1x annual fees; we need 2x.
2. SLA credits: Orion offers 5% per breach month; we want 10%.

I'm owning the negotiation on both and expect Orion's response by Oct 1.

Priya Nair
Procurement, Northwind

### 4. Subject: Security review status – Orion
Hi,

Update on the vendor security review:
- SOC 2 Type II report: received and reviewed, no major findings.
- Penetration test report: still pending from Orion.
- Data residency: Orion has not yet confirmed that data stays in the India region.

We can't sign until both pending items are closed. I'm following up with Orion.

Karan Singh
Security, Northwind

### 5. Subject: Orion – target go-live
Hi team,

Given the current timeline, we're now proposing a go-live of November 15 (not Nov 1), provided
the contract is signed by October 10. Onboarding takes about 5 weeks from signature.

Dana Lee
Orion DataWorks

### 6. Subject: Orion decision meeting moved to Oct 3
All,

The Orion go/no-go meeting has moved to October 3. Before then:
- Priya: close the indemnity and SLA points.
- Karan: get the pen test report and the data residency confirmation.
- Arjun: draft the migration plan from our current stack.

Arjun

---

## Google Docs

### Orion Pricing Proposal v3
Orion DataWorks – Commercial Proposal v3 (for Northwind Analytics)

Base plan: ₹48,00,000 per year.
Includes: up to 2 TB/day ingest, 90-day hot retention, 24x7 support, 99.9% uptime SLA.
Extended retention (91–365 days): ₹6,00,000 per year, billed separately.
3-year commitment: 12% discount on the base plan.
Payment terms: annual, in advance.
Price validity: until October 15.

### Orion MSA Redlines
MSA redline summary (Northwind legal, first pass)

Clause 9 – Indemnity: Orion proposes a cap of 1x annual fees. Northwind position: 2x. OPEN.
Clause 11 – SLA credits: Orion proposes 5% of monthly fees per breach month. Northwind position: 10%. OPEN.
Clause 14 – Termination for convenience: agreed at 90 days' notice. AGREED.
Clause 16 – Data processing addendum: agreed, pending data residency confirmation from security. PENDING.

### Orion POC Report
POC report – Orion log analytics (Sep 8–19)

Ingest: sustained 2.1 TB/day, peak 3.4 TB/day for 2 hours, no data loss.
Query: p50 0.6s, p95 1.8s (target 2s), p99 3.9s.
Integrations tested: Kafka source, OpenSearch export, SSO via SAML: all passed.
Gaps: retention beyond 90 days costs extra; alerting API is rate-limited to 60 requests/min.
Recommendation: technically ready to proceed.

---

## Notion pages

### Orion Vendor Evaluation
Project: choose a log analytics vendor to replace our self-managed stack.

Status: Evaluation in progress.
Shortlisted vendor: Orion DataWorks.
Target go-live: November 1.
Decision owner: Arjun Mehta.

Decision criteria:
- Handles 2 TB/day ingest
- p95 query latency under 2s
- Total 3-year cost under ₹1.5 crore
- Passes security review (SOC 2, pen test, India data residency)

### Meeting notes – Orion kickoff (Sep 18)
Attendees: Arjun, Priya, Karan, Dana (Orion).

- Orion to share revised pricing (v3) by Sep 22.
- POC to finish by Sep 19; Arjun to write up results.
- Legal review of MSA to start once pricing is final.
- Karan raised data residency as a hard requirement.
- Tentative go-live: November 1.
