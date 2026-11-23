for (const dialog of document.querySelectorAll("dialog.confirm-dialog")) {
  if (!(dialog instanceof HTMLDialogElement)) continue;
  if (dialog.dataset.open === "1" && !dialog.open) dialog.showModal();
  dialog.querySelector("[data-close]")?.addEventListener("click", () => dialog.close());
  if (dialog.id === "welcome-dialog") {
    dialog.addEventListener("cancel", (event) => event.preventDefault());
  }
}

const input = document.querySelector("#password");
for (const peek of document.querySelectorAll(".password button")) {
  const field = peek.parentElement?.querySelector("input");
  if (!(field instanceof HTMLInputElement)) continue;
  peek.addEventListener("click", () => {
    const show = field.type === "password";
    field.type = show ? "text" : "password";
    peek.setAttribute("aria-pressed", show ? "true" : "false");
    const label = show ? "Скрыть пароль" : "Показать пароль";
    peek.setAttribute("aria-label", label);
    peek.dataset.tip = label;
  });
}
if (input instanceof HTMLInputElement && !document.querySelector(".password button")) {
  const peek = document.querySelector("#peek");
  if (peek instanceof HTMLElement) {
    peek.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      peek.setAttribute("aria-pressed", show ? "true" : "false");
      const label = show ? "Скрыть пароль" : "Показать пароль";
      peek.setAttribute("aria-label", label);
      peek.dataset.tip = label;
    });
  }
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
  const sha256 = (text) => {
    const rotate = (value, amount) => (value >>> amount) | (value << (32 - amount));
    const words = [];
    const hash = [];
    const k = [];
    let primes = 0;
    const composite = {};
    for (let n = 2; primes < 64; n += 1) {
      if (composite[n]) continue;
      for (let i = n * n; i < 313; i += n) composite[i] = 1;
      if (primes < 8) hash[primes] = (Math.pow(n, 0.5) * 0x100000000) | 0;
      k[primes] = (Math.pow(n, 1 / 3) * 0x100000000) | 0;
      primes += 1;
    }
    const bits = text.length * 8;
    text += "\x80";
    while ((text.length % 64) !== 56) text += "\x00";
    for (let i = 0; i < text.length; i += 1) words[i >> 2] = (words[i >> 2] || 0) | (text.charCodeAt(i) << ((3 - (i % 4)) * 8));
    words.push((bits / 0x100000000) | 0);
    words.push(bits | 0);
    for (let j = 0; j < words.length; j += 16) {
      const w = words.slice(j, j + 16);
      const start = hash.slice();
      for (let i = 0; i < 64; i += 1) {
        const w15 = w[i - 15];
        const w2 = w[i - 2];
        const a = hash[0];
        const e = hash[4];
        const extra = i < 16 ? w[i] : (
          w[i - 16]
          + (rotate(w15, 7) ^ rotate(w15, 18) ^ (w15 >>> 3))
          + w[i - 7]
          + (rotate(w2, 17) ^ rotate(w2, 19) ^ (w2 >>> 10))
        ) | 0;
        w[i] = extra;
        const t1 = (hash[7]
          + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25))
          + ((e & hash[5]) ^ (~e & hash[6]))
          + k[i]
          + extra) | 0;
        const t2 = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22))
          + ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]))) | 0;
        hash.pop();
        hash.unshift((t1 + t2) | 0);
        hash[4] = (hash[4] + t1) | 0;
      }
      for (let i = 0; i < 8; i += 1) hash[i] = (hash[i] + start[i]) | 0;
    }
    return hash.map((word) => (word >>> 0).toString(16).padStart(8, "0")).join("");
  };
  let useSubtle = !!(globalThis.crypto && globalThis.crypto.subtle && typeof globalThis.crypto.subtle.digest === "function");
  const hashHex = async (text) => {
    if (useSubtle) {
      try {
        const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
        return hex(digest);
      } catch (error) {
        useSubtle = false;
      }
    }
    return sha256(text);
  };
  const solve = async (task) => {
    const ceiling = Number(task.maxnumber);
    for (let number = 0; number <= ceiling; number += 1) {
      if (await hashHex(`${task.salt}${number}`) === task.challenge) return number;
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
