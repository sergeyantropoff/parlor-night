for (const dialog of document.querySelectorAll("dialog.confirm-dialog")) {
  if (!(dialog instanceof HTMLDialogElement)) continue;
  if (dialog.dataset.open === "1" && !dialog.open) dialog.showModal();
  dialog.querySelector("[data-close]")?.addEventListener("click", () => dialog.close());
  if (dialog.id === "welcome-dialog") {
    dialog.addEventListener("cancel", (event) => event.preventDefault());
  }
}

const input = document.querySelector("#password");
const peek = document.querySelector("#peek");
if (input && peek) {
  peek.addEventListener("click", () => {
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    peek.setAttribute("aria-pressed", show ? "true" : "false");
    const label = show ? "Скрыть пароль" : "Показать пароль";
    peek.setAttribute("aria-label", label);
    peek.dataset.tip = label;
  });
}

const bornDay = document.querySelector("#born-day");
const bornMonth = document.querySelector("#born-month");
const bornYear = document.querySelector("#born-year");
const ageStatus = document.querySelector("#age-status");
if (bornDay && bornMonth && bornYear && ageStatus) {
  const months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"];
  const paintAge = () => {
    const day = Number(bornDay.value);
    const month = Number(bornMonth.value);
    const year = Number(bornYear.value);
    if (!day || !month || !year) {
      ageStatus.textContent = "Укажите дату рождения.";
      return;
    }
    const born = new Date(year, month - 1, day);
    if (born.getFullYear() !== year || born.getMonth() !== month - 1 || born.getDate() !== day) {
      ageStatus.textContent = "Такой даты не бывает.";
      return;
    }
    const today = new Date();
    let years = today.getFullYear() - year;
    if (today.getMonth() < month - 1 || (today.getMonth() === month - 1 && today.getDate() < day)) years -= 1;
    const tail = years % 10;
    const hundred = years % 100;
    const word = tail === 1 && hundred !== 11 ? "год" : tail >= 2 && tail <= 4 && (hundred < 12 || hundred > 14) ? "года" : "лет";
    ageStatus.textContent = `${day} ${months[month - 1]} ${year} · ${years} ${word}`;
  };
  for (const field of [bornDay, bornMonth, bornYear]) field.addEventListener("change", paintAge);
}

const robot = document.querySelector("#robot");
const robotBox = document.querySelector(".robot");
const robotNote = document.querySelector("#robot-note");
const captchaPayload = document.querySelector("#captcha-payload");
const registerForm = robot?.closest("form");
if (robot && robotBox && robotNote && captchaPayload && registerForm) {
  const sayRobot = (text) => {
    robotNote.hidden = !text;
    robotNote.textContent = text;
  };
  const hex = (buffer) => [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  const solve = async (task) => {
    const encoder = new TextEncoder();
    const ceiling = Number(task.maxnumber);
    for (let number = 0; number <= ceiling; number += 1) {
      const digest = await crypto.subtle.digest("SHA-256", encoder.encode(`${task.salt}${number}`));
      if (hex(digest) === task.challenge) return number;
      if (number % 250 === 0) await new Promise((resolve) => setTimeout(resolve, 0));
    }
    throw new Error("Проверка не сошлась. Отметьте поле ещё раз.");
  };
  robot.addEventListener("change", async () => {
    captchaPayload.value = "";
    sayRobot("");
    if (!robot.checked) return;
    robot.disabled = true;
    robotBox.classList.add("is-busy");
    try {
      const endpoint = `${registerForm.getAttribute("action") || "/register"}/captcha`;
      const response = await fetch(endpoint, { headers: { Accept: "application/json" } });
      const task = await response.json();
      if (!response.ok) throw new Error(task.error?.message || "Проверку сейчас не начать. Подождите минуту.");
      const number = await solve(task);
      captchaPayload.value = btoa(JSON.stringify({
        algorithm: task.algorithm,
        challenge: task.challenge,
        number,
        salt: task.salt,
        signature: task.signature,
      }));
    } catch (error) {
      robot.checked = false;
      sayRobot(error.message || "Подтвердите, что вы не робот.");
    } finally {
      robot.disabled = false;
      robotBox.classList.remove("is-busy");
    }
  });
  registerForm.addEventListener("submit", (event) => {
    if (captchaPayload.value) return;
    event.preventDefault();
    sayRobot("Подтвердите, что вы не робот.");
    robot.focus();
  });
}
