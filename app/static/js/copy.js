document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const value = button.getAttribute("data-copy") || "";
    const previous = button.textContent;
    try {
      await navigator.clipboard.writeText(value);
      button.textContent = "Скопировано";
    } catch {
      button.textContent = value;
    }
    window.setTimeout(() => {
      button.textContent = previous;
    }, 1400);
  });
});
