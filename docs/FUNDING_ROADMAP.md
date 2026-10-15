# Proposed $6,500 Development Roadmap

UHI is a local-first personal AI creator assistant in development. Its current source demonstrates local creator profiles, persistent feedback and history, and an optional validated local briefing adapter. The next work should make that foundation safer and easier for ordinary creators to use.

This is a proposed budget, based on planning estimates. No grant has been received, no application is represented as approved, and no affiliation or endorsement by Tether or another funder is claimed. Effort and sequencing will be refined after security review and user feedback.

| Priority | Proposed amount | Deliverable and evidence |
| --- | ---: | --- |
| Security hardening | $2,000 | Resolve review findings, document the threat boundary, and add targeted regression checks for storage, browser sessions and inference adapters. |
| Reliable installation | $1,500 | Reproducible macOS setup and recovery instructions tested from a clean checkout; packaging feasibility review. |
| Creator usability | $1,200 | Simplify the interface around profile, one next action and feedback; test onboarding with consenting nontechnical creators using synthetic or user-owned data. |
| Testing | $1,000 | Expand isolated workflow and failure tests; establish a clear supported OS/model test matrix. |
| Documentation | $800 | Improve quick start, troubleshooting, contributor guidance and honest capability reporting. |
| **Total** | **$6,500** | |

## Milestones

1. **Release foundation:** finish independent security review and publish a clean source snapshot with its owner-confirmed MIT license.
2. **Repeatable preview:** verify setup on the declared macOS configuration, document data ownership and recovery, and remove unavailable interface paths.
3. **Creator pilot:** evaluate whether people can save a profile, get a useful small task and record feedback. Report observed friction and failures without invented usage numbers.
4. **Expansion decision:** use evidence from the pilot to prioritize packaging, additional operating systems and user-controlled providers.

Funds would support development time and documented deliverables, not unlimited model compute or API subscriptions. Cross-platform support and integrations remain goals until verified. GitHub Sponsors and optional donations are planned separately; payment collection and grant submission are not part of this preparation work.
