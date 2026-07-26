// The IN PROGRESS section: what Claude is working on right now, above NOW
// because it is a higher elevation than "next thing I will start".
//
// It spans every project, because the limit it answers to is about concurrent
// Claude windows and those are not per-project. A banner counting every
// project over a list showing one is how thirteen sessions accumulated
// unnoticed. Rows are split by project heading so no row is ambiguous about
// which project's task 1 it names.

function inProgressTasks() {
  return state.tasks.filter(task => task.status === 'in-progress');
}

// Distinct groups, counting an ungrouped task as a group of one. This is what
// the limit counts and what the section draws, so the two always agree.
function inProgressGroupKeys() {
  return new Set(inProgressTasks().map(
    task => (task.group ? `${task.project}\ngroup:${task.group}`
                        : `${task.project}\ntask:${task.id}`)));
}

function inProgressSection() {
  const running = inProgressTasks();

  const section = document.createElement('section');
  section.id = 'in-progress';
  const groupCount = inProgressGroupKeys().size;
  const heading = document.createElement('h2');
  heading.textContent =
    `IN PROGRESS · ${groupCount} ${groupCount === 1 ? 'GROUP' : 'GROUPS'}`;
  section.append(heading);

  // Drawn even with nothing running, because this section is a drop target now
  // and the FIRST task claimed has to have somewhere to land — with no rows
  // there are no project headings either, so the section's own heading and
  // this line are the whole target. An empty box with nothing in it reads as a
  // render that failed rather than as a state, so it says what it is.
  if (!running.length) {
    const hint = document.createElement('p');
    hint.className = 'wip-empty';
    hint.textContent =
      'Nothing running. Drag a task here to claim it, or hit Spin up.';
    section.append(hint);
    return section;
  }

  // state.projects order, so the section does not reshuffle as tasks change.
  for (const project of state.projects) {
    const mine = running.filter(task => task.project === project.name);
    if (!mine.length) continue;
    const blocks = groupBlocks(mine);
    const folded = isProjectCollapsed(project.name);

    // One wrapper per project, so folding one hides its blocks without
    // touching the next project's.
    const wrapper = document.createElement('div');
    wrapper.className = folded ? 'project-block collapsed' : 'project-block';
    wrapper.dataset.project = project.name;
    wrapper.append(projectHeading(project.name, blocks.length, mine.length, folded));

    // No bucket picker and no disband here: a running session's bucket is not
    // a useful control, and dissolving a group mid-flight is not the gesture
    // anyone reaches for. The header IS draggable, though — it used not to be,
    // on the grounds that this section has nothing to reorder, and that stopped
    // being the whole story when a drag became able to change a bucket and a
    // status: dropping a running group on NEXT moves every member there and
    // releases it, which is the one gesture the ↩ beside it cannot do.
    //
    // It moves every member, including any this header did not draw — a header
    // can read "2 of 5", and a group lives in one bucket (invariant 16), so
    // there is no such thing as moving part of one. That differs from the
    // `done` button next to it, which acts on the two rows it drew, and the
    // difference is the point: done completes tasks, a drag moves the group.
    for (const block of blocks) {
      const element = block.group
        ? groupBlock(block, { showBucket: false, showDisband: false,
                              showReset: true })
        : taskRow(block.tasks[0], { showBucket: false, showReset: true });
      wrapper.append(nameForeignRows(element));
    }
    section.append(wrapper);
  }
  return section;
}

// The heading is also the fold control, and it says what folding away hides —
// a collapsed project that showed only its name would be a row you have to
// open to find out whether it matters.
function projectHeading(name, groupCount, taskCount, folded) {
  const heading = document.createElement('div');
  heading.className = 'project-heading';

  const label = document.createElement('span');
  // Project names are user-authored (they default to a folder name but can be
  // typed) — textContent, never innerHTML.
  label.textContent = name;

  const summary = document.createElement('span');
  summary.className = 'project-count';
  summary.textContent = `${groupCount} ${groupCount === 1 ? 'group' : 'groups'}`
    + ` · ${taskCount} ${taskCount === 1 ? 'task' : 'tasks'}`;

  heading.append(caretButton(folded, () => toggleProjectCollapsed(name)),
                 label, summary);
  // The whole heading folds it, not just the caret. A 9px triangle is a target
  // you have to aim at, and there is nothing else on this row to click.
  heading.onclick = () => toggleProjectCollapsed(name);
  return heading;
}

// A row from a project other than the selected one says which project it is.
// That is all it needs: taskRow hands openEditor the row's OWN project, and
// selectedIds() carries it too, so neither editing nor spin-up ever resolves
// an id against currentProject (invariant 6). Clicking through works from any
// project — editing a running task is bookkeeping and does not reach the
// session, which the editor says on the way in.
function nameForeignRows(element) {
  const rows = element.classList.contains('task')
    ? [element] : [...element.querySelectorAll('.task')];
  for (const row of rows) {
    if (row.dataset.project === currentProject) continue;
    const task = state.tasks.find(candidate => candidate.project === row.dataset.project
      && candidate.id === Number(row.dataset.id));
    if (task) row.querySelector('.title').textContent = `${task.project} · ${task.title}`;
  }
  return element;
}
