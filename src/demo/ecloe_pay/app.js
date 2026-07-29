const DEMO_STATE = Object.freeze({
  sessionId: "sess_pay_demo_001",
  decisionId: "dec_demo_001",
  eventPrefix: "evt_pay_demo",
  idempotencyKey: "pay-demo:order_demo_7841:0426",
  confirmationCode: "0426",
  bucketName: "ecloe-pay-demo-artifacts",
  paymentOrderId: "pay_order_demo_7841",
});

const timeline = document.querySelector("#timeline");
const emptyTimeline = document.querySelector("#emptyTimeline");
const termsDialog = document.querySelector("#termsDialog");
const termsCheckbox = document.querySelector("#termsCheckbox");
const acceptTermsButton = document.querySelector("#acceptTermsButton");
const technicalPanel = document.querySelector("#technicalPanel");
const securityState = document.querySelector("#securityState");
const benefitState = document.querySelector("#benefitState");
const transactionForm = document.querySelector("#transactionForm");
const confirmationCode = document.querySelector("#confirmationCode");
const toast = document.querySelector("#toast");
const toastMessage = document.querySelector("#toastMessage");

let eventCounter = 1;
let termsAccepted = localStorage.getItem("ecloePayTermsAccepted") === "true";
let transactionLocked = false;
let flaskAvailable = false;
let toastTimer;

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || body.reason || "Request failed");
  }
  return body;
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  toastMessage.textContent = message;
  toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    toast.hidden = true;
  }, 2800);
}

function appendTimeline(message, evidence = "") {
  emptyTimeline.hidden = true;

  const item = document.createElement("li");
  const time = document.createElement("time");
  time.dateTime = new Date().toISOString();
  time.textContent = new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const messageNode = document.createElement("strong");
  messageNode.textContent = message;
  item.append(time, document.createTextNode(" · "), messageNode);

  if (evidence) {
    const evidenceNode = document.createElement("span");
    evidenceNode.textContent = ` — ${evidence}`;
    item.append(evidenceNode);
  }

  timeline.prepend(item);
}

function setBenefitState(label, variant = "default") {
  benefitState.textContent = label;
  benefitState.classList.toggle("success", variant === "success");
}

function setSecurityState(label, variant = "success") {
  securityState.replaceChildren();
  if (variant === "success") {
    const dot = document.createElement("span");
    dot.className = "pulse-dot";
    dot.setAttribute("aria-hidden", "true");
    securityState.append(dot);
  }
  securityState.append(document.createTextNode(label));
  securityState.classList.toggle("success", variant === "success");
}

function nextEventId() {
  const eventId = `${DEMO_STATE.eventPrefix}_${String(eventCounter).padStart(3, "0")}`;
  eventCounter += 1;
  return eventId;
}

function openTerms() {
  if (!termsDialog.open) {
    termsDialog.showModal();
  }
}

function requireTerms() {
  if (!termsAccepted) {
    openTerms();
    showToast("Accept the demo terms to continue safely.");
  }
  return termsAccepted;
}

function recordReward(action, eventType, reward) {
  if (!requireTerms()) {
    return;
  }

  if (flaskAvailable) {
    const actionByEvent = {
      click: "open",
      dismissal: "dismiss",
      conversion: "accept",
    };
    postJson("/api/benefit-interactions", { action: actionByEvent[eventType] })
      .then((body) => {
        setBenefitState(action, reward === 1 ? "success" : "default");
        const event = body.reward_event;
        appendTimeline(
          `${action}. Reward event prepared for ${body.engine_endpoint}.`,
          `${event.event_id} · ${event.event_type} · reward=${event.reward}`,
        );
        showToast(`${action} recorded in the simulation.`);
      })
      .catch((error) => {
        appendTimeline(`Interaction rejected by Flask API: ${error.message}`);
        showToast("The demo interaction could not be recorded.");
      });
    return;
  }

  const eventId = nextEventId();
  setBenefitState(action, reward === 1 ? "success" : "default");
  appendTimeline(
    `${action}. Reward event prepared for POST /v1/rewards.`,
    `${eventId} · ${eventType} · reward=${reward} · decision=${DEMO_STATE.decisionId}`,
  );
  showToast(`${action} recorded in static demo mode.`);
}

document.querySelector("#openTermsButton").addEventListener("click", openTerms);
document.querySelectorAll("[data-open-terms]").forEach((button) => {
  button.addEventListener("click", openTerms);
});

termsCheckbox.addEventListener("change", () => {
  acceptTermsButton.disabled = !termsCheckbox.checked;
});

acceptTermsButton.addEventListener("click", () => {
  const finish = () => {
    termsAccepted = true;
    localStorage.setItem("ecloePayTermsAccepted", "true");
    termsDialog.close();
    appendTimeline("Demo terms accepted for this browser session.");
    showToast("Welcome to the ECloe Pay demo.");
  };

  if (!flaskAvailable) {
    finish();
    return;
  }

  postJson("/api/terms", { accepted: true })
    .then(finish)
    .catch((error) => {
      appendTimeline(`Terms rejected by Flask API: ${error.message}`);
      showToast("The API could not accept the demo terms.");
    });
});

document.querySelector("#customerModeButton").addEventListener("click", (event) => {
  event.currentTarget.classList.add("active");
  document.querySelector("#technicalModeButton").classList.remove("active");
  technicalPanel.hidden = true;
  showToast("Customer view enabled.");
});

document.querySelector("#technicalModeButton").addEventListener("click", (event) => {
  event.currentTarget.classList.add("active");
  document.querySelector("#customerModeButton").classList.remove("active");
  technicalPanel.hidden = false;
  showToast("Technical evidence is now visible.");
});

document.querySelector("#viewBenefitButton").addEventListener("click", () => {
  recordReward("Benefit viewed", "click", 0.2);
});

document.querySelector("#dismissBenefitButton").addEventListener("click", () => {
  recordReward("Benefit dismissed", "dismissal", 0);
});

document.querySelector("#acceptBenefitButton").addEventListener("click", () => {
  recordReward("Benefit accepted", "conversion", 1);
});

document.querySelectorAll("[data-quick-action]").forEach((button) => {
  button.addEventListener("click", () => {
    const action = button.dataset.quickAction;
    const targetByAction = {
      "Payment simulation": "#benefit",
      "Benefit center": "#benefit",
      "Security center": "#security",
    };
    const target = targetByAction[action];
    if (target) {
      document.querySelector(target).scrollIntoView({ behavior: "smooth", block: "center" });
    }
    showToast(`${action} selected. This remains a safe demo.`);
  });
});

transactionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!requireTerms()) {
    return;
  }

  const normalizedCode = confirmationCode.value.trim();
  const submitButton = transactionForm.querySelector("button[type='submit']");

  if (transactionLocked && !flaskAvailable) {
    appendTimeline("Duplicate simulated payment blocked by idempotency.");
    showToast("Duplicate payment blocked by the demo safeguards.");
    return;
  }

  if (normalizedCode !== DEMO_STATE.confirmationCode) {
    setSecurityState("Rejected", "error");
    appendTimeline("Simulated payment rejected by confirmation validation.");
    showToast("Use the deterministic demo code 0426.");
    confirmationCode.select();
    return;
  }

  if (flaskAvailable) {
    submitButton.disabled = true;
    submitButton.firstChild.textContent = "Verifying ";

    postJson(`/api/payment-orders/${DEMO_STATE.paymentOrderId}/simulate`, {
      confirmation_code: normalizedCode,
    })
      .then((body) => {
        transactionLocked = true;
        setSecurityState("Verified");
        setBenefitState("Payment accepted", "success");
        appendTimeline(
          "Flask API verified simulated payment and prepared reward event.",
          `${body.reward_event.event_id} · schema=${body.postgres_schema}`,
        );
        showToast("Simulated payment verified—no real money moved.");
      })
      .catch((error) => {
        setSecurityState("Rejected", "error");
        appendTimeline(`Simulated payment rejected by Flask API: ${error.message}`);
        showToast(error.message);
      })
      .finally(() => {
        submitButton.disabled = false;
        submitButton.firstChild.textContent = transactionLocked ? "Verified " : "Simulate payment ";
      });
    return;
  }

  transactionLocked = true;
  setSecurityState("Verified");
  recordReward("Simulated payment accepted", "conversion", 1);
  appendTimeline(
    "Pay-owned PostgreSQL transaction would commit payment order and outbox event.",
    `idempotency=${DEMO_STATE.idempotencyKey} · bucket=${DEMO_STATE.bucketName}`,
  );
});

document.querySelector("#resetButton").addEventListener("click", () => {
  const finish = () => {
    eventCounter = 1;
    transactionLocked = false;
    confirmationCode.value = "";
    setSecurityState("Locked");
    setBenefitState("Ready");
    timeline.replaceChildren();
    emptyTimeline.hidden = false;
    appendTimeline("Session reset with deterministic demo data.");
    showToast("The simulated session has been reset.");
  };

  if (!flaskAvailable) {
    finish();
    return;
  }

  postJson("/api/reset", {})
    .then(async () => {
      if (termsAccepted) {
        await postJson("/api/terms", { accepted: true });
      }
      finish();
    })
    .catch((error) => {
      appendTimeline(`Reset rejected by Flask API: ${error.message}`);
      showToast("The demo session could not be reset.");
    });
});

const sections = [...document.querySelectorAll("main section[id]")];
const navItems = [...document.querySelectorAll(".nav-item")];
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((first, second) => second.intersectionRatio - first.intersectionRatio)[0];
      if (!visible) {
        return;
      }
      navItems.forEach((item) => {
        const active = item.getAttribute("href") === `#${visible.target.id}`;
        item.classList.toggle("active", active);
        if (active) {
          item.setAttribute("aria-current", "page");
        } else {
          item.removeAttribute("aria-current");
        }
      });
    },
    { rootMargin: "-20% 0px -60%", threshold: [0.1, 0.4, 0.8] },
  );
  sections.forEach((section) => observer.observe(section));
}

const tiltCard = document.querySelector(".tilt-card");
if (tiltCard && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  tiltCard.addEventListener("pointermove", (event) => {
    const bounds = tiltCard.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width - 0.5;
    const y = (event.clientY - bounds.top) / bounds.height - 0.5;
    tiltCard.style.transform = `perspective(900px) rotateX(${-y * 3}deg) rotateY(${x * 4}deg)`;
  });
  tiltCard.addEventListener("pointerleave", () => {
    tiltCard.style.transform = "";
  });
}

fetch("/api/session")
  .then((response) => {
    if (!response.ok) {
      throw new Error("Flask API unavailable");
    }
    return response.json();
  })
  .then(async (body) => {
    flaskAvailable = true;
    document.querySelector("#sessionId").textContent = body.session.session_id;
    appendTimeline(
      "ECloe Pay Flask API connected with synthetic wallet data.",
      `schema=${body.security.postgres_schema} · bucket=${body.security.bucket_name}`,
    );

    if (termsAccepted) {
      await postJson("/api/terms", { accepted: true });
    }
  })
  .catch(() => {
    appendTimeline("ECloe Pay loaded in static fallback mode with synthetic wallet data.");
  })
  .finally(() => {
    if (!termsAccepted) {
      openTerms();
    }
  });
