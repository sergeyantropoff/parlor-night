(function () {
  const title = document.querySelector("[data-greeting]");
  if (!title) return;
  const name = title.getAttribute("data-greeting") || "";
  const hour = new Date().getHours();
  let phrase = "Добрый вечер";
  if (hour < 5 || hour >= 23) phrase = "Доброй ночи";
  else if (hour < 12) phrase = "Доброе утро";
  else if (hour < 17) phrase = "Добрый день";
  title.textContent = name ? `${phrase}, ${name}` : phrase;
  title.title = title.textContent;
})();
