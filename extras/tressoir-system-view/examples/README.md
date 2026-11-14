# Examples

Three invented projects, as patterns for the files in `WORK/SYSTEM_VIEW/`. There is no code behind
them; only the three files an agent and the script keep.

- `tally/` is a small command-line app with one view: nine boxes, two flows, two built changes
  (one of them states a flow again, because it added a step) and one plan that adds a box.
- `marlin/` is a database with boxes inside four of its boxes, two levels and no more: bare names
  that stand for an inner box's function, links and neighbours inside a box, four flows (calls
  through a parent box, calls stated by hand, `parallel for`), six built changes, and a plan in
  two entries, one of which adds a box and the other removes one.
- `pocket/` is a small tool whose code is all in one folder: four regions that share that folder,
  boxes that are single files, links between regions written with the regions' keys, two flows of
  which one calls the other, a built change that moves a box (`moves`) and one that gives a box a
  second path (`also`).

In each, `system.json` is as the script leaves it once the built entries are folded in, and
`changes.json` holds built entries (no `plan` key) and planned ones.
