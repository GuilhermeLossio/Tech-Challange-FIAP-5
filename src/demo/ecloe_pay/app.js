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
const termsDialog = document.querySelector("#termsDialog");
const termsCheckbox = document.querySelector("#termsCheckbox");
const acceptTermsButton = document.querySelector("#acceptTermsButton");
const technicalPanel = document.querySelector("#technicalPanel");
const securityState = document.querySelector("#securityState");
const benefitState = document.querySelector("#benefitState");
const transactionForm = document.querySelector("#transactionForm");
const confirmationCode = document.querySelector("#confirmationCode");

let eventCounter = 1;
let termsAccepted = localStorage.getItem("ecloePayTermsAccepted") === "true";
let transactionLocked = false;
let flaskAvailable = false;

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

function appendTimeline(message, evidence = "") {
  const item = document.createElement("li");
  const suffix = evidence ? ` Evidence: ${evidence}` : "";
  item.textContent = `${new Date().toLocaleTimeString()} - ${message}${suffix}`;
  timeline.prepend(item);
}

function setBenefitState(label, variant = "default") {
  benefitState.textContent = label;
  benefitState.classList.toggle("success", variant === "success");
}

function nextEventId() {
  const eventId = `${DEMO_STATE.eventPrefix}_${String(eventCounter).padStart(3, "0")}`;
  eventCounter += 1;
  return eventId;
}

function requireTerms() {
  if (!termsAccepted && !termsDialog.open) {
    termsDialog.showModal();
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
          `${event.event_id}, ${event.event_type}, reward=${event.reward}, decision=${event.decision_id}`,
        );
      })
      .catch((error) => appendTimeline(`Interaction rejected by Flask API: ${error.message}`));
    return;
  }

  const eventId = nextEventId();
  setBenefitState(action, reward === 1 ? "success" : "default");
  appendTimeline(
    `${action}. Reward event prepared for POST /v1/rewards.`,
    `${eventId}, ${eventType}, reward=${reward}, decision=${DEMO_STATE.decisionId}`,
  );
}

document.querySelector("#openTermsButton").addEventListener("click", () => {
  termsDialog.showModal();
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
  };

  if (!flaskAvailable) {
    finish();
    return;
  }

  postJson("/api/terms", { accepted: true })
    .then(finish)
    .catch((error) => appendTimeline(`Terms rejected by Flask API: ${error.message}`));
});

document.querySelector("#customerModeButton").addEventListener("click", (event) => {
  event.currentTarget.classList.add("active");
  document.querySelector("#technicalModeButton").classList.remove("active");
  technicalPanel.hidden = true;
});

document.querySelector("#technicalModeButton").addEventListener("click", (event) => {
  event.currentTarget.classList.add("active");
  document.querySelector("#customerModeButton").classList.remove("active");
  technicalPanel.hidden = false;
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

transactionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!requireTerms()) {
    return;
  }

  const normalizedCode = confirmationCode.value.trim();
  if (transactionLocked && !flaskAvailable) {
    appendTimeline("Duplicate simulated payment blocked by idempotency.");
    return;
  }

  if (normalizedCode !== DEMO_STATE.confirmationCode) {
    securityState.textContent = "Rejected";
    securityState.classList.remove("success");
    appendTimeline("Simulated payment rejected by confirmation validation.");
    return;
  }

  if (flaskAvailable) {
    postJson(`/api/payment-orders/${DEMO_STATE.paymentOrderId}/simulate`, {
      confirmation_code: normalizedCode,
    })
      .then((body) => {
        transactionLocked = true;
        securityState.textContent = "Verified";
        securityState.classList.add("success");
        setBenefitState("Simulated payment accepted", "success");
        appendTimeline(
          "Flask API verified simulated payment and prepared reward event.",
          `${body.reward_event.event_id}, schema=${body.postgres_schema}, bucket=${body.bucket_name}`,
        );
      })
      .catch((error) => {
        securityState.textContent = "Rejected";
        securityState.classList.remove("success");
        appendTimeline(`Simulated payment rejected by Flask API: ${error.message}`);
      });
    return;
  }

  transactionLocked = true;
  securityState.textContent = "Verified";
  securityState.classList.add("success");
  recordReward("Simulated payment accepted", "conversion", 1);
  appendTimeline(
    "Pay-owned PostgreSQL transaction would commit payment order and outbox event.",
    `idempotency=${DEMO_STATE.idempotencyKey}, bucket=${DEMO_STATE.bucketName}`,
  );
});

document.querySelector("#resetButton").addEventListener("click", () => {
  const finish = () => {
    eventCounter = 1;
    transactionLocked = false;
    confirmationCode.value = "";
    securityState.textContent = "Locked";
    securityState.classList.add("success");
    setBenefitState("Ready");
    timeline.replaceChildren();
    appendTimeline("Session reset with deterministic demo data.");
  };

  if (!flaskAvailable) {
    finish();
    return;
  }

  postJson("/api/reset", {})
    .then(finish)
    .catch((error) => appendTimeline(`Reset rejected by Flask API: ${error.message}`));
});

fetch("/api/session")
  .then((response) => response.json())
  .then((body) => {
    flaskAvailable = true;
    appendTimeline(
      "ECloe Pay Flask API connected with synthetic wallet data.",
      `schema=${body.security.postgres_schema}, bucket=${body.security.bucket_name}`,
    );
  })
  .catch(() => {
    appendTimeline("ECloe Pay loaded in static fallback mode with synthetic wallet data.");
  })
  .finally(() => {
    if (!termsAccepted) {
      termsDialog.showModal();
    }
  });
