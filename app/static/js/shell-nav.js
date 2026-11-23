(function () {
  var phone = window.matchMedia("(max-width: 719px)");

  function saved() {
    try { return sessionStorage.getItem("pn-shell-from") || "/"; } catch (error) { return "/"; }
  }

  function backTarget(raw) {
    if (!raw || raw.charAt(0) !== "/") return "/";
    if (raw.indexOf("/menu") === 0 || raw.indexOf("/me") === 0) return "/";
    return raw;
  }

  function remember() {
    var here = location.pathname + location.search + location.hash;
    if (here.indexOf("/menu") === 0 || here.indexOf("/me") === 0) return;
    try { sessionStorage.setItem("pn-shell-from", here); } catch (error) {}
  }

  function toggle(event, path) {
    if (!phone.matches) return;
    if (location.pathname === "/menu" || location.pathname === "/me") {
      if (location.pathname !== path) return;
      event.preventDefault();
      location.href = backTarget(saved());
      return;
    }
    remember();
  }

  var more = document.querySelector('.shell-bar [data-shell="more"]');
  if (more) more.addEventListener("click", function (event) { toggle(event, "/menu"); });
  var account = document.querySelector('[data-shell="account"]');
  if (account) account.addEventListener("click", function (event) { toggle(event, "/me"); });
})();
