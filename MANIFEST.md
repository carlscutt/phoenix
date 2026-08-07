# Module 6 — Studio UI Delivery Manifest
Spec §13's Dashboard section. Last piece of Module 6 (and of Phoenix V1
overall) before release paperwork.

## Files → destination

| Delivered as | Place at |
|---|---|
| `DEST_phoenix_phoenix_actions.py` | `projects/phoenix/phoenix_actions.py` (overwrites — pure additions, see diff below) |
| `DEST_phoenix_routes.py` | `projects/phoenix/routes.py` (overwrites — pure additions) |
| `DEST_dashboard_studio.html` | wherever your real `studio.html` lives (overwrites — pure additions) |

All three are complete files built by copying your real uploads and
applying precise, targeted edits — not retyped from memory. I diffed
every file against your original afterward specifically to confirm
**every line outside the new additions is byte-identical** — nothing
else was touched, nothing removed.

## What's new

**`phoenix_actions.py`** — three thin wrapper functions, same pattern
as every other module: `submit_business_blueprint_generation`,
`get_business_blueprint`, `get_business_blueprint_versions`. One real
fix applied here: `report.py`'s `list_blueprint_versions()` returns
oldest-first (its own internal convention); every other
`list_*_versions()` wrapper in this file returns newest-first, so I
reversed it at this layer rather than touching `report.py` again.

**`routes.py`** — three new routes, deliberately shaped like Module 4's
`/api/phoenix/solutions/<public_id>/approve` (flat, keyed by
`solution_public_id`), not like Modules 3-5's opportunity-nested routes
— because this is a per-blueprint action (Decision 3), not an
opportunity-level listing:

```
POST /api/phoenix/solutions/<public_id>/blueprint       (body: {run_id, cluster_id})
GET  /api/phoenix/solutions/<public_id>/blueprint
GET  /api/phoenix/solutions/<public_id>/blueprint/versions
```

`run_id`/`cluster_id` go in the POST body (same place Approve puts its
`approved` flag) since `generate_business_blueprint()` needs both, but
the URL itself only needs to identify the blueprint.

**`studio.html`** — every validated blueprint card (Module 5's results
view) now gets its own "Generate Business Blueprint" button and result
area — one per card, not one per opportunity, since you might want to
build a blueprint for a candidate other than Module 5's own
"strongest" pick. Results show the 5 sections spec §13 calls out for
prominent display (Executive Summary, Product Roadmap, MVP Definition,
Marketing Strategy, Financial Overview) up top, with all 17 sections
available behind the same collapsible pattern used everywhere else in
this file. Plus Download (client-side `.md` export, no new backend
route needed — the data's already in the browser) and Version History.
Already-generated blueprints auto-load the same way Module 5's own
results do.

**Deliberately untouched:** the `currentRunId` bug in `toggleApproval()`
(Module 4's, re-confirmed present at line 306/`openOpportunityDetail`
while I was in this file) — not part of this delivery, not mine to fix
without you asking, per the Freeze Rule.

## One real spec item I did NOT build, and why — needs your decision

Spec §13 also lists **"Approve Blueprint."** I didn't add it. Reason:
doing it properly means an `approved` boolean column on
`BusinessBlueprintVersion` — and unlike every earlier correction to
that model this session, **this one would no longer be a free, no-
migration change.** You've now generated real Business Blueprints for
clusters 19 and 21 on your actual machine — real rows exist. Adding a
column to `models.py` wouldn't retroactively add it to the already-
created table (same class of issue `blueprint_version` itself hit
earlier), and this time a drop-and-recreate would mean **losing those
real generations**, not an empty table. That's a real trade-off, not
mine to make unilaterally.

Two ways forward, your call:
1. **Skip it for v1** — nothing downstream currently reads an
   "approved" flag anyway (no Module 7 exists yet), so this is
   genuinely optional right now, not a functional gap.
2. **Add it properly** — I write the column addition plus a real `ALTER
   TABLE ... ADD COLUMN approved BOOLEAN NOT NULL DEFAULT 0` migration
   command (safe, additive, preserves your existing rows), you run it,
   then I wire up the button.

## What I verified — real execution, not just reading

- Both Python files: `ast.parse` clean, and `diff` against your
  originals confirms pure additions only.
- The new backend functions: ran them for real in the sandbox against
  actual `business_blueprint/report.py` — full pipeline (generate →
  validate → generate blueprint → read back → regenerate), including a
  test that specifically confirms the newest-first reversal fix works.
- The new JS: for the first time this session, actually **executed**
  (not just syntax-checked) in Node — isolated `renderBusinessBlueprintHtml`,
  `downloadBusinessBlueprint`, and their real `escapeHtml` dependency
  from the rest of the page, and ran them against sample data. Confirmed:
  all 17 sections render, the 5 highlighted sections appear correctly,
  `publicId` wires into the onclick handlers correctly, `download`
  handles both present and missing data without throwing, and —
  worth specifically checking since this renders real model output —
  a deliberately malicious `<script>` payload in section content comes
  out correctly HTML-escaped, not executable.

## Next step

Once you've placed all three and clicked through it in a real browser
(generate a blueprint for a validated candidate, reload to confirm
persistence, check Download and Version History), Module 6's UI is
done. Then it's Release Notes, Handoff, Git Tag, Freeze — closing out
Module 6 and Phoenix V1 entirely.
