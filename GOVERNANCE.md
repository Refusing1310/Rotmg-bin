# Development governance and release policy

**Approved direction:** 29 October 2026. This is the standing Product Owner policy for this repository.

## Product Owner involvement

- Involve the Product Owner before deciding major product scope, user experience or visual design direction, architecture with lasting product consequences, ethics, privacy, accessibility trade-offs, pricing/licensing, externally visible behaviour, and other consequential choices. Present a concise recommendation and alternatives, then await the relevant decision.
- Continue authorised routine engineering autonomously: implementation, testing, bug fixing, documentation, small refactors, dependency hygiene and review preparation. Do not request approval for each low-risk change within scope.
- Escalate high-risk security changes, significant data-use decisions, material safety risks, irreversible operations and new permissions/integrations before proceeding. A GitHub issue is not itself permission to cross an approval boundary.
- Keep Product Owner reviews focused: group related, compatible changes for review when practical; preserve issue/commit traceability.

## Security review: public-release gate, not a private-development gate

- **Mandatory independent security review applies to public releases only.** Obtain a genuine independent assessment against the exact proposed release commit/artifact, resolve material findings, retest and secure the Product Owner's explicit go/no-go before a public release.
- For internal feature branches, draft or ready PRs, offline testing, and private isolated QA previews, **do not require a separate formal or external security review merely because work is advancing**.
- Private work still requires proportionate security engineering: available CI, automated dependency/secret/static checks, least privilege, review of significant trust-boundary changes, accurate test evidence and no bypass of configured required checks. A passed scanner is not an independent public-release review.
- Public release includes making a service/site available to the public, publishing a distributable software release or shipping a change that users directly consume as a public release. On already-public repositories, source/PR contents are visible immediately: never publish secrets or private data. Public source visibility alone does not waive the security gate for actual releases.
- Maintain any **additional specialist** requirements for sensitive work (for example clinical, human-subject, legal, privacy, financial, or regulated activity); this policy does not authorise that work or waive its necessary safeguards.

## Branches, checks and deployment

- Work on topic branches and draft PRs until reviewable. Do not merge to a protected main/master branch, deploy, release, change credentials, alter branch protections, or publish without existing specific authorisation.
- Do not silently disable required CI/security checks, weaken workflow permissions, or claim a review occurred when it did not. If older reviewer-specific automation conflicts with this policy or is unavailable, propose a safe adjustment separately rather than bypassing the check.
- Verify checks against the current exact PR head; distinguish tested, skipped, pending, failed and untested evidence. Fix ordinary defects autonomously within approved scope.
- A private preview does not itself require the public-release independent assessment, but it must remain private/isolated and respect existing credential, environment, external-access and deployment restrictions.

## Project-specific limits

- This is a public repository: all pushed code and PRs are visible. Keep real account credentials out of branches, and retain approval limits around game automation and account-level actions.

This document governs general decision thresholds. More protective project-specific safety or legal constraints continue to apply.
