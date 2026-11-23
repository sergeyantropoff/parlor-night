(function () {
  try {
    if (!window.matchMedia("(max-width: 719px)").matches) return;
    if (location.pathname !== "/" || location.hash.length < 2) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (sessionStorage.getItem("pn-section") !== "1") return;
    sessionStorage.removeItem("pn-section");
    if ("scrollRestoration" in history) history.scrollRestoration = "manual";
    var id = location.hash.slice(1);
    function run() {
      var el = document.getElementById(id);
      window.scrollTo(0, 0);
      if (!el) return;
      requestAnimationFrame(function () {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
    else run();
  } catch (e) {}
})();
