window.addEventListener('pywebviewready', async () => {
  const state = await window.pywebview.api.get_state();
  document.getElementById('app').textContent =
    `${state.projects.length} projects, ${state.tasks.length} tasks`;
});
