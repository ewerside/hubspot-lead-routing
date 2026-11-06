# AI lead qualification and routing for HubSpot

An n8n flow that scores form leads with Claude and routes them into HubSpot without duplicates or lost leads.

## Notes

- Supabase's free plan allows 2 projects, so this repo shares a portfolio project with other work. It connects as its own role, `lead_routing`, whose default schema is also `lead_routing`. That role cannot read or write any other table in the project.
- Slack's "Create New App" dialog no longer has a "From scratch" option. I used "Pick features" and added only the `incoming-webhook` scope.
- In HubSpot, private apps now live under Development > Legacy apps. The plain `tickets` scope is gone, so the app has `crm.objects.tickets.read` and `crm.objects.tickets.write` instead.
