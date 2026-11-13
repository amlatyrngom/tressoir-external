# Examples

Two invented projects, as patterns for the files in `WORK/SYSTEM_VIEW/`. There is no code behind
them; only the three files an agent and the script keep.

- `tally/` is a small command-line app with one view: nine boxes, one flow, two built changes and
  one plan that adds a box.
- `marlin/` is a database with views inside four of its boxes: bare names that stand for an inner
  box's function, links and neighbours inside a box, two flows, six built changes, and a plan in
  two entries, one of which adds a box and the other removes one.

In each, `system.json` is as the script leaves it once the built entries are folded in, and
`changes.json` holds built entries (no `plan` key) and planned ones.
