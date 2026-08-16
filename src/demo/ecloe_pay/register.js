const form = document.querySelector("#registerForm");
const status = document.querySelector("#registerStatus");
const submitButton = form.querySelector("button[type='submit']");

function cookieValue(name) {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split("=")[1] || "";
}

function setPending(pending) {
  submitButton.disabled = pending;
  submitButton.setAttribute("aria-busy", String(pending));
  form.querySelectorAll("input").forEach((input) => {
    input.readOnly = pending;
    input.setAttribute("aria-disabled", String(pending));
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  status.textContent = "";
  setPending(true);
  const payload = {
    email: form.email.value.trim(),
    password: form.password.value,
    password_confirm: form.password_confirm.value,
  };
  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": decodeURIComponent(cookieValue("ecloe_pay_csrf")),
      },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      status.textContent = body.error || form.dataset.registerFailed;
      return;
    }
    const locale = document.documentElement.lang || "en-US";
    const returnTo = form.dataset.returnTo || `/pay?lang=${encodeURIComponent(locale)}`;
    window.location.assign(returnTo);
  } catch (_error) {
    status.textContent = form.dataset.registerFailed;
  } finally {
    setPending(false);
  }
});
