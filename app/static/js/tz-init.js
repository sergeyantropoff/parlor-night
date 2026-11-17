(function () {
  var zone = "";
  try {
    zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch (error) {
    return;
  }
  if (!zone || zone.length > 64 || zone.indexOf("/") < 0) return;
  var match = document.cookie.match(/(?:^|; )pn_tz=([^;]*)/);
  var saved = match ? decodeURIComponent(match[1]) : "";
  if (saved === zone) return;
  document.cookie = "pn_tz=" + encodeURIComponent(zone) + "; Path=/; Max-Age=31536000; SameSite=Lax";
  try {
    if (sessionStorage.getItem("pn_tz_boot") === zone) return;
    sessionStorage.setItem("pn_tz_boot", zone);
  } catch (error) {
    return;
  }
  location.reload();
})();
