(function () {
  var bar = document.getElementById("phone-bar");
  if (!bar) return;
  var links = bar.querySelectorAll("[data-phone]");
  var phone = window.matchMedia("(max-width: 719px)");

  function key() {
    var path = location.pathname;
    if (path === "/more" || path === "/about" || path === "/rules" || path === "/privacy" || path === "/contact") return "more";
    if (path.indexOf("/news") === 0 || (path === "/" && location.hash === "#news")) return "news";
    if (path === "/" && location.hash === "#games") return "games";
    if (path === "/") return "home";
    return "";
  }

  function paint() {
    var current = key();
    links.forEach(function (link) {
      var on = link.getAttribute("data-phone") === current;
      link.classList.toggle("is-on", on);
      if (on) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function motion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
  }

  function here() {
    return location.pathname + location.hash;
  }

  function rememberSection() {
    try { sessionStorage.setItem("pn-section", "1"); } catch (e) {}
  }

  function smoothTo(id, url) {
    var behavior = motion();
    var el = id ? document.getElementById(id) : null;
    if (id && !el) return;
    if (behavior === "auto") {
      if (el) el.scrollIntoView({ block: "start" });
      else window.scrollTo(0, 0);
      if (here() !== url) history.pushState(null, "", url);
      paint();
      return;
    }
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    else window.scrollTo({ top: 0, behavior: "smooth" });
    var started = performance.now();
    var timer = setInterval(function () {
      var top = el ? el.getBoundingClientRect().top : 0;
      var settled = el ? Math.abs(top - 66) < 4 : window.scrollY <= 1;
      if (settled || performance.now() - started > 1400) {
        clearInterval(timer);
        if (here() !== url) history.pushState(null, "", url);
        paint();
      }
    }, 40);
  }

  paint();
  window.addEventListener("hashchange", paint);

  var home = bar.querySelector('[data-phone="home"]');
  if (home) {
    home.addEventListener("click", function (event) {
      if (!phone.matches || location.pathname !== "/") return;
      event.preventDefault();
      smoothTo(null, "/");
    });
  }

  var games = bar.querySelector('[data-phone="games"]');
  if (games) {
    games.addEventListener("click", function (event) {
      if (!phone.matches) return;
      if (location.pathname !== "/") {
        rememberSection();
        return;
      }
      if (!document.getElementById("games")) return;
      event.preventDefault();
      smoothTo("games", "/#games");
    });
  }

  var news = bar.querySelector('[data-phone="news"]');
  if (news) {
    news.addEventListener("click", function (event) {
      if (!phone.matches) return;
      if (location.pathname.indexOf("/news") === 0) {
        event.preventDefault();
        window.scrollTo({ top: 0, behavior: motion() });
        paint();
        return;
      }
      if (location.pathname !== "/") {
        rememberSection();
        return;
      }
      if (!document.getElementById("news")) return;
      event.preventDefault();
      smoothTo("news", "/#news");
    });
  }

  var more = bar.querySelector('[data-phone="more"]');
  if (more) {
    more.addEventListener("click", function (event) {
      if (!phone.matches) return;
      var path = location.pathname;
      if (path === "/about" || path === "/rules" || path === "/privacy" || path === "/contact") {
        event.preventDefault();
        location.href = "/more";
        return;
      }
      if (path !== "/more") {
        try { sessionStorage.setItem("pn-more-from", path + location.search + location.hash); } catch (e) {}
        return;
      }
      event.preventDefault();
      var back = "/";
      try { back = sessionStorage.getItem("pn-more-from") || "/"; } catch (e) {}
      if (!back || back.indexOf("/") !== 0 || back.indexOf("/more") === 0 || back.indexOf("/about") === 0 || back.indexOf("/rules") === 0 || back.indexOf("/privacy") === 0 || back.indexOf("/contact") === 0) back = "/";
      if (back.indexOf("/#") === 0) rememberSection();
      location.href = back;
    });
  }

  document.addEventListener("click", function (event) {
    if (!phone.matches) return;
    var link = event.target.closest ? event.target.closest("a[href]") : null;
    if (!link || link.closest("#phone-bar")) return;
    var href = link.getAttribute("href") || "";
    if (location.pathname === "/" && href.charAt(0) === "#") {
      var id = href.slice(1);
      if (!document.getElementById(id)) return;
      event.preventDefault();
      smoothTo(id, "/#" + id);
      return;
    }
    if (location.pathname !== "/" && href.indexOf("/#") === 0) rememberSection();
  });
})();
