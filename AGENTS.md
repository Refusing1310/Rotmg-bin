# Agent instructions — Rotmg-bin

This is a **public** repository preserving an older, upstream Realm of the Mad God GUI-trading bot. All branches and PR content become public immediately. Read [README.md](README.md), [GOVERNANCE.md](GOVERNANCE.md), LICENSE/upstream attribution, current issues and PRs before work. Do not expose account names, usernames, tokens or private game data in prompts, commits or logs. No agent or issue worker is activated by these instructions.

## Current scope and exclusions

- Preserve the original author attribution, licence and upstream history. Do not assume compatibility with the current game client or permission for live automation; no bot execution or unattended gaming-account interaction.
- **Never run `trader.py`**, live GUI/keyboard automation, trading commands, simulated account clicks on genuine clients or game service requests as part of automated tests. Use static checks, isolated mocks and offline synthetic fixtures only. Never bypass game rules, anti-cheat controls or CAPTCHA, and do not add account automation, credential reads or network order execution.
- Current issue [#15](https://github.com/Refusing1310/Rotmg-bin/issues/15) records an unverified/no-enforced-protection risk for `master` at its prior audit. The initial Copilot instructions in [draft PR #2](https://github.com/Refusing1310/Rotmg-bin/pull/2) were based on an older, 32-commits-behind branch and include superseded blanket owner approval wording. This current-`master` refresh supersedes that proposed guidance only **once properly integrated**. Do not auto-merge either PR.

## Issue eligibility and scoped claims

1. Fetch the live task, current comments, recent PRs and branch/file overlap. An issue, label or historical user request does **not** confer new permissions. `blocked`, `needs-review`, `needs-human`, missing rights/CI and competing work are not eligible for unattended implementation.
2. Require a bounded, explicitly authorised task, measurable acceptance, exclusions, exact offline tests, dependencies, risk assessment and rollback; choose planning rather than executing a guessed project feature.
3. A supervised agent uses a topic branch and reviewable PR with temporary owner/UTC issue/branch claim; rechecks for concurrent claims. Labels/comments are not atomic locks. Up to two genuinely nonoverlapping developers per project, with unknown occupancy failing closed. No account-wide unattended dispatcher is enabled.
4. Release the claim on pause or review; document exact head SHA, test results, unresolved controls and next owner action. Draft PRs aren't shipped work.

## Checks and release controls

- This repository has no confirmed current automated exact-head CI or enforced `master` protection at the 11 November checkpoint. Before any merge, an administrator must verify PR-only protections, no force pushes, actual required offline tests/security scanning, legal scope and release triggers; a green optional run is not sufficient. Do not downgrade rules to make integration happen.
- The 9 November Product Owner policy permits **routine non-public code integrations** without separate owner approval only with genuine enforced technical/reviewer controls and verified non-release effects. Because **this repository is public**, never commit sensitive material even on a private-seeming feature branch. Public software releases, package publishing or production/game-service deployment require exact-candidate design/security assessment, applicable independent release review and explicit Product Owner approval.
- Do not enable unattended Copilot assignments, paid models, privileged workflows, network access, new credentials, game accounts, public software distribution or branch/security configuration changes from this Markdown.
- Until **18 November 2026**, N-CODE and the private company website outrank discretionary work in this legacy repo.

No issue is `agent-ready` for unsupervised work unless the real branch protections, permissions, scoped issue acceptance and offline CI are independently verified.
