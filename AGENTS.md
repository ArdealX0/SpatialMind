# SpatialMind engineering workflow

Start with the latest Git state and docs/DAILY_LOG.md. Pick the smallest unfinished roadmap item that improves a user-visible capability or resolves a measured risk. If blocked on sensor data or GPU access, take the next independent CPU task and document the blocker.

Assign a developer to implementation, a test engineer to independent behavior checks, QA to acceptance criteria and failure modes, and security to input boundaries, dependencies, private footage and permissions. Give parallel editors nonoverlapping files. The lead runs the acceptance case, reviews the diff and integrates only verified work. Distinguish a test run locally from a GitHub Actions result. Never invent model results.

Record actual test outcomes, limitations, review findings, and next step in the daily log. Use Toronto dates and one log entry per date, updating it on retry. Publish meaningful tested changes only. Keep Git history intact; never force-push to manufacture activity. When Notion is connected, mirror the daily entry into the approved project page and link to the real commit or PR. Keep secrets and raw private video out of Git and Notion.
