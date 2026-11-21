(function () {
  var root = document.documentElement;
  var theme = root.getAttribute("data-theme") || "dark";
  var stored = localStorage.getItem("bm-theme");
  if (root.getAttribute("data-signed-in") !== "1") {
    if (stored === "light" || stored === "dark") theme = stored;
  } else if (theme === "system") {
    if (stored === "light" || stored === "dark") {
      theme = stored;
    } else {
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
  }
  if (theme !== "light" && theme !== "dark") theme = "dark";
  root.setAttribute("data-theme", theme);
})();
