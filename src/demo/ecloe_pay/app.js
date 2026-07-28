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
const sessionId = document.querySelector("#sessionId");
const authIdentity = document.querySelector("#authIdentity");
const logoutButton = document.querySelector("#logoutButton");
const runtimeMode = document.querySelector("#runtimeMode");
const databaseProvider = document.querySelector("#databaseProvider");
const databaseSchema = document.querySelector("#databaseSchema");

let eventCounter = 1;
let termsAccepted = false;
let transactionLocked = false;
let flaskAvailable = false;
let backendRequiresAuth = false;

async function getJson(url) {
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error || "Request failed");
    error.status = response.status;
    throw error;
  }
  return body;
}

function cookieValue(name) {
  return document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(`${name}=`))
    ?.split("=")[1] || "";
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": decodeURIComponent(cookieValue("ecloe_pay_csrf")),
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(body.error || body.reason || "Request failed");
    error.status = response.status;
    throw error;
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

function redirectToLoginWhenNeeded(error) {
  if (error.status === 401) {
    window.location.assign("/pay/login");
    return true;
  }
  return false;
}

function setPresentationMode() {
  backendRequiresAuth = false;
  authIdentity.textContent = "Presentation mode — data is not being persisted.";
  runtimeMode.textContent = "Presentation mode — data is not being persisted.";
  databaseProvider.textContent = "presentation";
  databaseSchema.textContent = "not persisted";
}

function setAuthenticatedMode(auth, security) {
  authIdentity.textContent = auth.user?.email || "Demo persona";
  runtimeMode.textContent = security.database_provider === "azure_sql"
    ? "Azure SQL authenticated demo"
    : "Memory-backed local demo";
  databaseProvider.textContent = security.database_provider;
  databaseSchema.textContent = security.database_schema;
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
      .catch((error) => {
        if (!redirectToLoginWhenNeeded(error)) {
          appendTimeline(`Interaction rejected by Flask API: ${error.message}`);
        }
      });
    return;
  }

  const eventId = nextEventId();
  setBenefitState("Presentation preview");
  appendTimeline(
    `Presentation mode — data is not being persisted. ${action} was previewed only.`,
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
    termsDialog.close();
    appendTimeline("Demo terms accepted for this backend session.");
  };

  if (!flaskAvailable) {
    termsDialog.close();
    appendTimeline("Presentation mode — data is not being persisted. Terms were previewed only.");
    return;
  }

  postJson("/api/terms", { accepted: true })
    .then(finish)
    .catch((error) => {
      if (!redirectToLoginWhenNeeded(error)) {
        appendTimeline(`Terms rejected by Flask API: ${error.message}`);
      }
    });
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
    appendTimeline("Presentation mode — data is not being persisted. Duplicate preview ignored.");
    return;
  }

  if (normalizedCode !== DEMO_STATE.confirmationCode) {
    securityState.textContent = "Preview only";
    securityState.classList.remove("success");
    appendTimeline("Presentation mode — data is not being persisted. Confirmation preview rejected.");
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
          `${body.reward_event.event_id}, provider=${body.database_provider}, schema=${body.database_schema}, bucket=${body.bucket_name}`,
        );
      })
      .catch((error) => {
        if (redirectToLoginWhenNeeded(error)) {
          return;
        }
        securityState.textContent = "Rejected";
        securityState.classList.remove("success");
        appendTimeline(`Simulated payment rejected by Flask API: ${error.message}`);
      });
    return;
  }

  transactionLocked = true;
  securityState.textContent = "Preview only";
  securityState.classList.remove("success");
  recordReward("Simulated payment accepted", "conversion", 1);
  appendTimeline(
    "Presentation mode — data is not being persisted. No Azure SQL payment order was updated.",
    `idempotency=${DEMO_STATE.idempotencyKey}, bucket=${DEMO_STATE.bucketName}`,
  );
});

document.querySelector("#resetButton").addEventListener("click", () => {
  const finish = (body = {}) => {
    eventCounter = 1;
    transactionLocked = false;
    termsAccepted = false;
    confirmationCode.value = "";
    securityState.textContent = flaskAvailable ? "Locked" : "Preview only";
    securityState.classList.toggle("success", flaskAvailable);
    setBenefitState(flaskAvailable ? "Ready" : "Presentation preview");
    timeline.replaceChildren();
    sessionId.textContent = body.session_id || DEMO_STATE.sessionId;
    appendTimeline(
      flaskAvailable
        ? "Session reset with deterministic demo data."
        : "Presentation mode — data is not being persisted. Static state was reset.",
    );
    termsDialog.showModal();
  };

  if (!flaskAvailable) {
    finish();
    return;
  }

  postJson("/api/reset", {})
    .then(finish)
    .catch((error) => {
      if (!redirectToLoginWhenNeeded(error)) {
        appendTimeline(`Reset rejected by Flask API: ${error.message}`);
      }
    });
});

logoutButton.addEventListener("click", () => {
  postJson("/api/auth/logout", {})
    .then(() => window.location.assign("/pay/login"))
    .catch(() => window.location.assign("/pay/login"));
});

async function bootstrap() {
  try {
    const auth = await getJson("/api/auth/me");
    flaskAvailable = true;
    backendRequiresAuth = Boolean(auth.requires_authentication);
    const body = await getJson("/api/session");
    setAuthenticatedMode(auth, body.security);
    sessionId.textContent = body.session.session_id;
    termsAccepted = Boolean(body.session.terms_accepted);
    appendTimeline(
      "ECloe Pay Flask API connected with synthetic wallet data.",
      `provider=${body.security.database_provider}, schema=${body.security.database_schema}, bucket=${body.security.bucket_name}`,
    );
  } catch (error) {
    if (redirectToLoginWhenNeeded(error)) {
      return;
    }
    setPresentationMode();
    securityState.textContent = "Preview only";
    securityState.classList.remove("success");
    setBenefitState("Presentation preview");
    appendTimeline("Presentation mode — data is not being persisted.");
  } finally {
    if (!termsAccepted) {
      termsDialog.showModal();
    }
  }
}

bootstrap();
