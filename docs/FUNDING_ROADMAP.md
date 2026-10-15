# Proposed $6,500 Development Roadmap

UHI is a local-first personal AI creator assistant in development. Its current source demonstrates local creator profiles, persistent feedback and history, and an optional validated local briefing adapter. The next work should make that foundation safer and easier for ordinary creators to use.

This is a proposed budget, based on planning estimates. No grant has been received, no application is represented as approved, and no affiliation or endorsement by Tether or another funder is claimed. Effort and sequencing will be refined after security review and user feedback.

| Priority | Proposed amount | Deliverable and evidence |
| --- | ---: | --- |
| Security hardening | $2,000 | Resolve review findings, document the threat boundary, and add targeted regression checks for storage, browser sessions and inference adapters, including safe QVAC provider boundaries, response validation and failure handling. |
| Reliable installation | $1,500 | Develop reproducible macOS setup and recovery instructions tested from a clean checkout, including QVAC runtime dependencies and compatible local model setup on one verified macOS configuration; review packaging feasibility. |
| Creator usability | $1,200 | Simplify the interface around profile, one next action and feedback; test onboarding with consenting nontechnical creators using synthetic or user-owned data, including proposed QVAC-backed workflows that do not require understanding inference infrastructure. |
| Testing and validation | $1,000 | Expand isolated workflow and failure tests; implement and validate actual QVAC local inference and structured creator briefings, then establish supported hardware/model configurations through testing. |
| Documentation | $800 | Improve quick start, troubleshooting, contributor guidance and honest capability reporting, including QVAC setup and integration guidance, verified compatibility, troubleshooting and limitations. |
| **Total** | **$6,500** | |

## Proposed QVAC Integration

UHI intends to develop a Tether QVAC local inference adapter as proposed grant-funded work. This is not an existing or tested UHI capability. Intended deliverables include real local inference validation and a reproducible creator briefing demonstration on a verified macOS, hardware and model setup; compatibility remains to be established.

This work fits within the existing five budget categories, $6,500 total and four milestones below. It adds no funding request and does not imply funding, affiliation or endorsement by Tether.

## Milestones

1. **Release foundation:** finish independent security review and publish a clean source snapshot with its owner-confirmed MIT license.
2. **Repeatable preview:** verify setup on the declared macOS configuration, document data ownership and recovery, and remove unavailable interface paths.
3. **Creator pilot:** evaluate whether people can save a profile, get a useful small task and record feedback. Report observed friction and failures without invented usage numbers.
4. **Expansion decision:** use evidence from the pilot to prioritize packaging, additional operating systems and user-controlled providers.

Funds would support development time and documented deliverables, not unlimited model compute or API subscriptions. Cross-platform support and integrations remain goals until verified. GitHub Sponsors and optional donations are planned separately; payment collection and grant submission are not part of this preparation work.
