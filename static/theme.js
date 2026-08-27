(() => {
  const STORAGE_KEY = "theme";
  const prefersDark = () => window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;

  function current() {
    return localStorage.getItem(STORAGE_KEY) || (prefersDark() ? "dark" : "light");
  }

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      button.textContent = theme === "dark" ? "Светлая тема" : "Тёмная тема";
      button.setAttribute("aria-label", theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему");
    }
  }

  apply(current());

  window.toggleTheme = () => {
    const next = current() === "dark" ? "light" : "dark";
    localStorage.setItem(STORAGE_KEY, next);
    apply(next);
  };

  document.addEventListener("DOMContentLoaded", () => {
    apply(current());
    for (const button of document.querySelectorAll("[data-theme-toggle]")) {
      button.addEventListener("click", window.toggleTheme);
    }
  });
})();
