# LGPD Plan - ECloe

> This document describes how ECloe would handle personal data in a real production scenario.
> In the Datathon 7MLET context, **no real personal data is used**: all data is synthetic or derived from a public Kaggle dataset, without identifiers, wealth, income, gender, or race.

---

## 1. Controller Identification

| Field | Value |
|-------|-------|
| Controller | Digital financial institution operating ECloe, to be defined in production |
| Data Protection Officer | To be appointed according to LGPD Art. 41 |
| Contact | dpo@institution.com.br placeholder |

---

## 2. Processing Purpose

ECloe performs adaptive experimentation for eligible marketplace-finance actions across digital channels. In production, personal data processing would have the following purposes:

- Select, in real time, the most appropriate eligible action for the customer context.
- Record interactions for continuous learning of the decision policy.
- Monitor quality, fairness, and drift in the recommendation model.
- Explain recommendations to customers and internal teams through reason codes, model cards, and approved documentation.

Secondary purposes, such as auditing and model improvement, are separated from the primary purpose and documented individually.

---

## 3. Legal Basis

| Purpose | Legal basis under LGPD | Note |
|---------|------------------------|------|
| Offer and action personalization | Art. 7, IX - legitimate interest | Requires a documented Legitimate Interest Assessment; customers must have an opt-out channel |
| Execution of a financial product contract | Art. 7, V - contract execution | Applies when the customer already has an active relationship |
| Audit and regulatory compliance | Art. 7, II - legal obligation | Minimum retention required by Banco Central and CVM rules |
| Model improvement and retraining | Art. 7, IX - legitimate interest | Anonymized or pseudonymized data; periodic necessity assessment |

> **Sensitive decisions remain human-in-the-loop.** No credit, blocking, or eligibility decision is made exclusively by the model.

---

## 4. Processed Data and Minimization

### 4.1 Data Entering the Decision Engine

The model receives only **anonymized behavioral and contextual features**. Direct identifiers never reach the Bandit service.

| Feature | Type | Usage justification |
|---------|------|---------------------|
| Hillstrom campaign segment / coarse history segment | Categorical | Groups profiles without identifying individuals |
| Access channel | Categorical | Provides decision context, such as app or web |
| Recency | Numeric | Captures campaign timing without direct identity |
| Prior channel flags | Numeric | Represents campaign eligibility signals without direct identity |
| Marketplace segment | Categorical | Represents aggregated commerce behavior, not raw item history |
| Purchase habit band | Categorical | Captures coarse behavior such as recurring category or checkout pattern |
| Wallet engagement band | Categorical | Captures digital wallet usage without exposing balance or account identifiers |

### 4.2 Data Excluded from the Model

- Name, national taxpayer ID, email, phone number.
- Income, wealth, balance.
- Raw item-level purchase history, full basket contents, or raw search history.
- Detailed credit score or automated credit decision variables.
- Gender, race, religion, health data.
- Precise location such as GPS coordinates.
- Identifiable browsing data.

### 4.3 Separation Architecture

```text
Identity layer (CRM)                Feature layer (bandit)
--------------------                ----------------------
Tax ID, name, account     --hash--> anonymous session_id
Income, balance                     segment, channel, minimized context
Raw purchase history                purchase habit band, wallet engagement band
Registration data                   binary reward: click/conversion
```

Pseudonymization is applied before any data reaches the bandit service, evaluation layer, or future explainability interface.

---

## 5. Explainability Interface

The Datathon MVP does not require an LLM assistant or RAG index. If an explainability interface is added in a future production scenario:

- It must use **only synthetic data, internal policies, model cards, system cards, and experiment summaries**.
- Any indexed decision logs must be aggregated and anonymized before indexing.
- It must not access CRM systems or databases with identifiers.
- Responses that reference decision data must refer only to anonymous sessions or aggregate cohorts.

---

## 6. Retention Cycle

| Data | Retention | Justification | Disposal |
|------|-----------|---------------|----------|
| Offer events, including impression and click | 2 years | Experiment audit and retraining | Anonymization after 6 months; deletion after 2 years |
| Decision logs, including reason codes and policy version | 5 years | Regulatory obligation | Deletion after the legal period |
| Session features | 90 days | Delayed reward horizon | Automatic deletion |
| Explainability index data, if implemented | Experiment duration plus 1 year | Audit reproducibility | Deletion when the cycle closes |

---

## 7. Identifier and Protected Attribute Mapping

| Attribute | LGPD classification | ECloe handling |
|-----------|---------------------|----------------|
| National taxpayer ID / identity document | Direct personal data | Never enters the model; one-way hash for `session_id` |
| Gender | Sensitive personal data under Art. 11 | Not collected or inferred |
| Race / ethnicity | Sensitive personal data under Art. 11 | Not collected or inferred |
| Income / wealth | Financial personal data | Does not enter the bandit; used only in eligibility rules external to the model |
| Raw purchase history | Personal data | Converted into coarse behavior bands before decisioning |
| Wallet balance | Financial personal data | Does not enter the bandit; eligibility and suitability remain upstream |
| Location | Personal data | Only aggregated region or state; never GPS |

The fairness index monitored by ECloe evaluates relative exposure across **synthetic segments**, not across real protected groups.

---

## 8. Logging and Telemetry Policy

- Decision logs record `session_id`, selected offer, policy and version, reason code, and timestamp.
- Logs **do not record** data subject identifiers, financial data, or sensitive attributes.
- Log access is restricted through Azure RBAC, Managed Identity, and Entra ID.
- Audit logs are immutable and append-only, stored in Blob Storage with configured retention.
- Application Insights telemetry is configured without full IP collection, with the last octet masked.

---

## 9. Data Subject Rights

In production, ECloe would support the rights provided under LGPD Art. 18:

| Right | How it would be addressed |
|-------|---------------------------|
| Access | Customer portal shows offer history and reason codes |
| Correction | Registration data is corrected in CRM; features are recalculated in the next session |
| Deletion | `session_id` and associated events are deleted; the model is retrained without the data |
| Portability | Interaction history is exported in an open JSON format |
| Objection to processing | Customer opts out of adaptive personalization and receives the deterministic baseline |
| Automated decision review | Reason codes and model documentation are available; human escalation is required |

---

## 10. Incident Response Plan

| Phase | Action | Deadline |
|-------|--------|----------|
| Detection | Automatic Azure Monitor alert for anomalous access or exfiltration | Immediate |
| Containment | Revoke compromised Managed Identity and isolate the affected service | Under 1 hour |
| Assessment | Classify whether personal data was affected, volume, and risk to data subjects | Under 4 hours |
| ANPD notification | Formal communication when there is relevant risk to data subjects | 72 hours under Art. 48 |
| Data subject notification | Direct communication when there is relevant risk or harm | According to ANPD guidance |
| Remediation | Fix the vulnerability, review controls, and update the plan | Under 30 days |
| Recordkeeping | Document the incident, actions taken, and lessons learned | Permanent |

---

## 11. Periodic Review

| Item | Cadence | Owner |
|------|---------|-------|
| Legitimate Interest Assessment review | Annually or when the purpose changes | DPO and legal team |
| Data mapping update | For each new component or feature | Engineering and DPO |
| Log and retention audit | Semiannually | Information security |
| Model card and system card review | For each retraining cycle | ML Engineering |
| Incident response test | Annual simulation | Security and operations |

---

## 12. Limitations and Notices

- This plan describes the privacy architecture for a future and hypothetical production scenario.
- In the Datathon 7MLET context, no real personal data is collected, stored, or processed.
- A real implementation would require legal validation, DPO approval, a formal Legitimate Interest Assessment, and Banco Central review when applicable.
- ECloe **must not be deployed in regulated production** without proper risk, suitability, and compliance validation.
