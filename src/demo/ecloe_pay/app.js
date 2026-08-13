const DEMO_STATE = Object.freeze({
  sessionId: "sess_pay_demo_001",
  decisionId: "",
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
const recommendationDecision = document.querySelector("#recommendationDecision");
const recommendationOffer = document.querySelector("#recommendationOffer");
const recommendationPolicy = document.querySelector("#recommendationPolicy");
const viewDetailsButton = document.querySelector("#viewDetailsButton");
const quickActionButtons = document.querySelectorAll(".quick-action[data-target]");
const pageLocale = document.documentElement.lang || "en-US";

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
  const suffix = evidence ? ` Evidencia: ${evidence}` : "";
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
    window.location.assign(`/pay/login?lang=${encodeURIComponent(pageLocale)}`);
    return true;
  }
  return false;
}

function setPresentationMode() {
  backendRequiresAuth = false;
  authIdentity.textContent = "Carteira demonstrativa";
  runtimeMode.textContent = "Modo apresentacao - os dados nao sao persistidos.";
  databaseProvider.textContent = "apresentacao";
  databaseSchema.textContent = "nao persistido";
}

function setAuthenticatedMode(auth, security) {
  authIdentity.textContent = auth.user?.email || "Persona demo";
  runtimeMode.textContent = security.database_provider === "azure_sql"
    ? "Demo autenticada com Azure SQL"
    : "Demo local em memoria";
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
          `${action}. Evento de recompensa preparado para ${body.engine_endpoint}.`,
          `${event.event_id}, ${event.event_type}, reward=${event.reward}, decision=${event.decision_id}`,
        );
      })
      .catch((error) => {
        if (!redirectToLoginWhenNeeded(error)) {
          appendTimeline(`Interacao rejeitada pela API Flask: ${error.message}`);
        }
      });
    return;
  }

  const eventId = nextEventId();
  setBenefitState("Previa da apresentacao");
  appendTimeline(
    `Modo apresentacao - os dados nao sao persistidos. ${action} foi apenas pre-visualizado.`,
    `${eventId}, ${eventType}, reward=${reward}, decision=${DEMO_STATE.decisionId}`,
  );
}

document.querySelector("#openTermsButton").addEventListener("click", () => {
  termsDialog.showModal();
});

viewDetailsButton.addEventListener("click", () => {
  termsDialog.showModal();
});

quickActionButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const target = document.querySelector(`#${button.dataset.target}`);
    target?.scrollIntoView({ behavior: "smooth" });
  });
});

termsCheckbox.addEventListener("change", () => {
  acceptTermsButton.disabled = !termsCheckbox.checked;
});

acceptTermsButton.addEventListener("click", () => {
  const finish = () => {
    termsAccepted = true;
    termsDialog.close();
    appendTimeline("Termos da demo aceitos para esta sessao.");
  };

  if (!flaskAvailable) {
    termsAccepted = true;
    termsDialog.close();
    appendTimeline("Modo apresentacao - os dados nao sao persistidos. Termos aceitos apenas para pre-visualizacao.");
    return;
  }

  postJson("/api/terms", { accepted: true })
    .then(finish)
    .catch((error) => {
      if (!redirectToLoginWhenNeeded(error)) {
        appendTimeline(`Termos rejeitados pela API Flask: ${error.message}`);
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
  recordReward("Beneficio visualizado", "click", 0.2);
});

document.querySelector("#dismissBenefitButton").addEventListener("click", () => {
  recordReward("Beneficio dispensado", "dismissal", 0);
});

document.querySelector("#acceptBenefitButton").addEventListener("click", () => {
  recordReward("Beneficio aceito", "conversion", 1);
});

transactionForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!requireTerms()) {
    return;
  }

  const normalizedCode = confirmationCode.value.trim();
  if (transactionLocked && !flaskAvailable) {
    appendTimeline("Modo apresentacao - os dados nao sao persistidos. Previa duplicada ignorada.");
    return;
  }

  if (normalizedCode !== DEMO_STATE.confirmationCode) {
    securityState.textContent = "Somente previa";
    securityState.classList.remove("success");
    appendTimeline("Modo apresentacao - os dados nao sao persistidos. Previa de confirmacao rejeitada.");
    return;
  }

  if (flaskAvailable) {
    postJson(`/api/payment-orders/${DEMO_STATE.paymentOrderId}/simulate`, {
      confirmation_code: normalizedCode,
    })
      .then((body) => {
        transactionLocked = true;
        securityState.textContent = "Verificado";
        securityState.classList.add("success");
        setBenefitState("Pagamento simulado aceito", "success");
        appendTimeline(
          "A API Flask verificou o pagamento simulado e preparou o evento de recompensa.",
          `${body.reward_event.event_id}, provider=${body.database_provider}, schema=${body.database_schema}, bucket=${body.bucket_name}`,
        );
      })
      .catch((error) => {
        if (redirectToLoginWhenNeeded(error)) {
          return;
        }
        securityState.textContent = "Rejeitado";
        securityState.classList.remove("success");
        appendTimeline(`Pagamento simulado rejeitado pela API Flask: ${error.message}`);
      });
    return;
  }

  transactionLocked = true;
  securityState.textContent = "Somente previa";
  securityState.classList.remove("success");
  recordReward("Pagamento simulado aceito", "conversion", 1);
  appendTimeline(
    "Modo apresentacao - os dados nao sao persistidos. Nenhuma ordem de pagamento do Azure SQL foi atualizada.",
    `idempotency=${DEMO_STATE.idempotencyKey}, bucket=${DEMO_STATE.bucketName}`,
  );
});

document.querySelector("#resetButton").addEventListener("click", () => {
  const finish = (body = {}) => {
    eventCounter = 1;
    transactionLocked = false;
    termsAccepted = false;
    confirmationCode.value = "";
    securityState.textContent = flaskAvailable ? "Bloqueado" : "Somente previa";
    securityState.classList.toggle("success", flaskAvailable);
    setBenefitState(flaskAvailable ? "Pronto" : "Previa da apresentacao");
    timeline.replaceChildren();
    sessionId.textContent = body.session_id || DEMO_STATE.sessionId;
    appendTimeline(
      flaskAvailable
        ? "Sessao reiniciada com dados deterministicos da demo."
        : "Modo apresentacao - os dados nao sao persistidos. Estado estatico reiniciado.",
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
        appendTimeline(`Reinicio rejeitado pela API Flask: ${error.message}`);
      }
    });
});

logoutButton.addEventListener("click", () => {
  postJson("/api/auth/logout", {})
    .then((body) => window.location.assign(
      body.logout_url || `/pay/login?lang=${encodeURIComponent(pageLocale)}`,
    ))
    .catch(() => window.location.assign(`/pay/login?lang=${encodeURIComponent(pageLocale)}`));
});

async function bootstrap() {
  try {
    const auth = await getJson("/api/auth/me");
    flaskAvailable = true;
    backendRequiresAuth = Boolean(auth.requires_authentication);
    const body = await getJson("/api/session");
    setAuthenticatedMode(auth, body.security);
    sessionId.textContent = body.session.session_id;
    recommendationDecision.textContent = body.recommendation.decision_id;
    recommendationOffer.textContent = body.benefit.offer_id;
    recommendationPolicy.textContent = body.recommendation.policy;
    termsAccepted = Boolean(body.session.terms_accepted);
    appendTimeline(
      "API Flask da ECloe Pay conectada com dados sinteticos de carteira.",
      `provider=${body.security.database_provider}, schema=${body.security.database_schema}, bucket=${body.security.bucket_name}`,
    );
  } catch (error) {
    if (redirectToLoginWhenNeeded(error)) {
      return;
    }
    setPresentationMode();
    securityState.textContent = "Somente previa";
    securityState.classList.remove("success");
    setBenefitState("Previa da apresentacao");
    appendTimeline("Modo apresentacao - os dados nao sao persistidos.");
  } finally {
    if (!termsAccepted) {
      termsDialog.showModal();
    }
  }
}

bootstrap();
