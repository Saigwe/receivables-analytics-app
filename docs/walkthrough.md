# 3-minute walkthrough: Receivables & Cash Analytics App

A timed script for a Loom recording of about 3 minutes (screen plus camera bubble, 1080p). Say it in your own words; the lines are a guide, not a teleprompter.

**Open these tabs before you press record:** Streamlit app running locally, README, dbt/models, docs/design_doc.md, GitHub Actions.

| Time | On screen | What to say |
|---|---|---|
| 0:00–0:20 | Portfolio card, then the README title | AR teams work from reports that disagree. This is one live view of receivables, with aging, DSO, CEI, unapplied cash and a collections worklist over 660k invoices. Every screen proves the sub-ledger ties to the general ledger. |
| 0:20–0:45 | README intro and the Data section | It rebuilds, on synthetic data, work I did for a food-delivery marketplace: moving 10+ Tableau AR reports to Streamlit on dbt for one live view of $700M+ of receivables. No employer data is used. |
| 0:45–1:10 | The Streamlit app: KPI trends, then aging | Aging uses the segment each customer had at that month-end, through a point-in-time join to a type-2 customer dimension. |
| 1:10–1:35 | The collections worklist with drill-down | Collectors get a ranked list that puts the money most at risk first. |
| 1:35–2:00 | The tie-out panel and the pipeline-health tab | This panel is the GL tie-out, 54 of 54 month-end and currency checks to the cent. The health tab comes from recorded dbt runs. |
| 2:00–2:30 | dbt test output and a green Actions run | 59 dbt checks run in about 4 seconds, and a script proves the incremental cash-application fact equals a full rebuild across 650k rows. |
| 2:30–2:45 | `docs/design_doc.md`, the options table | The decision I'd defend in an interview: Put the tie-out on every screen, not in a separate report, so trust is visible where decisions are made. |
| 2:45–3:00 | Back to the README top | For a finance team, that means one definition of every AR number, and collectors who start each day with the right calls. The repo, numbers and design doc are linked under the video. |

## Recording checklist
- Close email, chat and notifications. Zoom the browser to 125% so code is readable.
- Run `make fixture-all` once before recording, so CI-style output is fresh if you show it.
- Keep to one take per section; Loom lets you trim. Aim for 2:45 to 3:10.
- Show real numbers on screen as you say them; never estimate on camera.
- Say "synthetic" out loud wherever the README labels data as synthetic.

## After recording
1. Copy the Loom share link.
2. In `README.md`, replace the roadmap line with `- [x] [3-minute Loom walkthrough](<your Loom link>)` and add the link under the title.
3. Add the link to this project's card on saigwe.github.io.
