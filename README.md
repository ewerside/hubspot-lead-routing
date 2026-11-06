# AI lead qualification and routing for HubSpot

An n8n flow that scores form leads with Claude and routes them into HubSpot without duplicates or lost leads.

## Test data

`scripts/make_leads.py` builds 200 fake leads for Fieldnote, a made-up SaaS that tracks construction projects. 170 are new people, 20 resend an earlier email with other casing, spaces or message, and 10 are junk (bad email or empty name). Emails and sites use example.com subdomains and phones use ranges reserved for film and TV, so nothing points to a real person.

Each lead has an expected tier in `data/expected.csv`, set by this rule:

| Intent | Expected tier |
| --- | --- |
| demo_request, pricing | hot if the sender is an owner, director, operations manager or project manager at a company with 51+ people, otherwise warm |
| support_existing_customer, partnership | warm at 51+ people, otherwise cold |
| job_seeker, spam | cold |

With seed 42 that gives 29 hot, 86 warm and 55 cold among the 170 new leads.

## Notes

- Supabase's free plan allows 2 projects, so this repo shares a portfolio project with other work. It connects as its own role, `lead_routing`, whose default schema is also `lead_routing`. That role cannot read or write any other table in the project.
- Slack's "Create New App" dialog no longer has a "From scratch" option. I used "Pick features" and added only the `incoming-webhook` scope.
- I create the n8n credentials with `scripts/setup_n8n.py` through the n8n API instead of by hand, so no secret is typed or shown on screen. They are named `portfolio lead-routing ...` because another portfolio project on the same n8n already uses `portfolio Anthropic` and `portfolio Supabase`. The HubSpot and Anthropic credentials only work for their own API domain.
- In HubSpot, private apps now live under Development > Legacy apps. The plain `tickets` scope is gone, so the app has `crm.objects.tickets.read` and `crm.objects.tickets.write` instead.
