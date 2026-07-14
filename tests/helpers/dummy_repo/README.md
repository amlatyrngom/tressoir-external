# Tressoir External dummy repositories

`make_dummy_repo.sh` creates a disposable, committed Git repository with:

- existing Claude, Codex, and Pi instruction files;
- existing `IB` state, task, canon, artifacts, ignore rules, and unrelated skills;
- deliberate `tressoir-plan` canonical/adapter collisions;
- protected-byte and symlink-target baselines;
- helpers for verifying non-clobbering and complete-tree idempotence; and
- manual commands for exercising Claude + Codex + Pi together.

From this directory:

```bash
./make_dummy_repo.sh
cd dummy_repo
cat TESTING.md
```

Or choose a destination, including one with spaces:

```bash
./make_dummy_repo.sh "/tmp/tressoir dummy repo"
```

The creator refuses to replace an existing destination. Delete a disposable
dummy repository explicitly before recreating it.
