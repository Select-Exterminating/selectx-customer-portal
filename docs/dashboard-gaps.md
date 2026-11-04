# Program dashboard: what's built and what's missing

Written 2026-11-01. Compares each tab of the RAMP portal (`../select-ramp-portal`) with what the customer portal can fill from its own data.

| Tab | Status | What's missing |
|---|---|---|
| Overview | Built | Rollout funnel (needs tracker data). Program-phase filter on Store Watch. |
| Executive Review | Mostly built, from live data | Building-type outcomes, the partnership timeline and committed portfolio. The six-month question counts from the first RAMP order, since the tracker's Phase 2 dates aren't held. Condition ownership uses PestPac's responsibility field, not the Account Review's log. |
| Risk Assessments | Built | Rodent notes as a finding type: GoCanvas records rodent activity as yes or no with no notes field of its own. |
| Store Tracker | Partly built, derived from orders | Launch, inspection requested, proposal submitted, approved, Romeo 2, entomology walk, phase 1 and 2 dates, completed, notes. |
| Rodent Activity | Built | Nothing. |
| Structural | Built | Nothing. Remediation is only as good as the notes: a repair that nobody writes down stays open. |
| Sanitation & Pests | Built | Nothing. |
| Stores | Built | Team director and sub-region columns and search (contacts are held, not yet joined). |
| Risk Model | Partly built | Chipotle's risk score vs. field findings chart and the priority risk lists table. |
| Reports | Built, generated reports only | By decision (2026-11-01), the tab lists the service reports we generate, not invoices or other PestPac documents. The Drive's service report PDFs and Riskgate forms aren't listed. |

The store flyover is built too. It doesn't show: tracker dates (inspection requested, approved, abatement started; first monitoring comes from orders) and the program phase built on them (it shows the stage from service history), Chipotle's risk list and rank, real estate type, sub-region, or the Drive folder and its reports.

## Data we need

| Data | Unlocks | Where it is today | How to get it |
|---|---|---|---|
| Program enrollment and milestones | Store Tracker, rollout funnel, program-phase filter, six-month question | `Chipotle_RAMP_Store_Tracker.csv`, maintained by hand, 127 stores | Add `programs` and `program_enrollments`, import the sheet once, then edit in the app (`dashboard-data-plan.md` D5) |
| Chipotle's priority risk lists | Risk Model chart and table | Two customer spreadsheets (`Rodent_Risk_Assessment_Tekashi_34.csv`, `_66.csv`) | Import per company (D7); a current copy is needed from Chipotle |
| Real estate type and sub-region | Building-type outcomes, Stores columns | Restaurant Leader Report, not all columns imported | Extend `app.import_leader_report` (D6) |
| Drive documents | Past service reports in the Reports tab, if wanted | Shared Google Drive, about 2,660 files | Import from Drive, or link to the folders |
| Partnership facts | Executive Review timeline, committed portfolio | Written by hand into the portal's `exec.js` | Decide whether these belong in the app at all; they're narrative, not data |

## Data problems found

- **Wrong coordinates in PestPac.** Store #3920 (Wareham, MA) is at -34.138, 150.631, in Australia, and store #4832 (Hamburg, NY) is at 0, 0. They zoomed the risk map out to the whole world. The map now leaves them off and names them; they should be corrected in PestPac.
- **RAMP nights with nothing to read.** Early program nights at stores such as #1224, #1686, #1699, and #4181 have no technician comment or service notes, so they have no findings. Their day one moves later than the portal's. Only the PDF reports have those nights.
- **Dates a day apart.** Report dates are often a day off PestPac's work date (overnight work). A store can sit a day either side of the 28-day Stabilized window.
