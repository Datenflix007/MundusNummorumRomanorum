document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-search-form]");
  const status = document.querySelector("[data-search-status]");
  if (!form || !status) return;

  form.addEventListener("submit", () => {
    status.textContent = "Searching the local catalog…";
  });
});
