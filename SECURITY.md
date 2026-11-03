# Security and privacy review

The first milestone is a local CLI for synthetic observation records. Keep the database on a trusted machine: object labels, timestamps and locations can reveal activity even without the source video. Ignore rules help avoid accidents; review the staged changes before pushing.

Before merging a change:

- **Inputs:** Reject malformed records and invalid timestamps. Bind user values as SQL parameters. Treat labels and video identifiers as data; never execute them or automatically fetch their contents.
- **Data handling:** Use invented objects and synthetic fixtures in tests and demos. Keep private recordings, object crops, embeddings, databases, credentials and model checkpoints outside Git. Put local inputs under `local-data/`. Log only outlines, test counts and commit references in Notion.
- **Credentials and CI:** Use read-only CI permissions, pinned action revisions and no secrets for tests. Review changes to workflow triggers, permissions and dependencies. Do not run code from pull requests in a privileged workflow.
- **Network or API milestone:** Before enabling remote ingestion, add request-size limits, validation, access controls and tests for unauthorized reads. Review retention and deletion for raw and derived data before using real footage.
- **Release evidence:** Record tests actually run, findings, fixes, and remaining limitations in the daily log. Use synthetic reproductions when reporting bugs; do not paste secrets or private recordings into issues.
