# SpatialMind engineering workflow

Start with the latest Git state and the designated Notion project tracker. Pick the smallest unfinished roadmap item that improves a user-visible capability or resolves a measured risk. If blocked on sensor data or GPU access, take the next independent CPU task and document the blocker.

Assign a developer to implementation, a test engineer to independent behavior checks, QA to acceptance criteria and failure modes, and security to input boundaries, dependencies, private footage and permissions. Give parallel editors nonoverlapping files. The lead runs the acceptance case, reviews the diff and integrates only verified work. Distinguish a test run locally from a GitHub Actions result. Never invent model results.

Record actual test outcomes, limitations, review findings, and next step only in the designated Notion daily entry. Do not add daily reports, walkthroughs or agent narratives to GitHub files, issues, PRs or commit messages. Use Toronto dates and one log entry per date, updating it on retry. Publish meaningful tested changes only. Keep Git history intact; never force-push to manufacture activity. Update the existing dated Notion row, preserve user notes, and link to the real commit or PR. If Notion is unavailable, retry there rather than publishing the report elsewhere. Keep secrets and raw private video out of Git and Notion.
