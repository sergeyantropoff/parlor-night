(function () {
  var root = document.documentElement;
  var theme = root.getAttribute("data-theme") || "system";
  if (theme === "system") {
    var stored = localStorage.getItem("bm-theme");
    if (stored === "light" || stored === "dark") {
      theme = stored;
    } else {
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
  }
  root.setAttribute("data-theme", theme);
})();
