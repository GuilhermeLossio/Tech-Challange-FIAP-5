from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.bandits.policies import BanditPolicy


@dataclass(frozen=True)
class CausalEvaluation:
    policy: str
    estimator: str
    value: float
    ips: float
    snips: float
    observed_rate: float
    support_rate: float
    valid_rows: int
    excluded_rows: int
    clipped_rows: int
    effective_sample_size: float
    propensity_mean: float | None
    confidence_interval: tuple[float, float]
    decisions: list[dict[str, Any]]


def validate_propensity(value: Any, *, minimum: float = 0.01) -> float | None:
    try:
        propensity = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(propensity) or propensity <= 0.0 or propensity > 1.0:
        return None
    return propensity


def evaluate_logged_policy(
    policy: BanditPolicy,
    dataframe: pd.DataFrame,
    q_values: dict[str, float],
    *,
    action_column: str = "action",
    reward_column: str = "reward",
    propensity_column: str = "behavior_propensity",
    subject_column: str = "subject_key",
    propensity_floor: float = 0.01,
    bootstrap_samples: int = 200,
    seed: int = 42,
) -> CausalEvaluation:
    if not 0 < propensity_floor <= 1:
        raise ValueError("propensity_floor must be between zero and one.")

    values: list[float] = []
    ips_values: list[float] = []
    weights: list[float] = []
    observed_rewards: list[float] = []
    subjects: list[str] = []
    decisions: list[dict[str, Any]] = []
    excluded = 0
    clipped = 0
    supported = 0

    for row in dataframe.to_dict("records"):
        propensity = validate_propensity(row.get(propensity_column))
        if propensity is None:
            excluded += 1
            continue
        logged_action = str(row[action_column])
        target_action = policy.select_action()
        reward = float(row[reward_column])
        effective_propensity = max(propensity, propensity_floor)
        clipped += int(propensity < propensity_floor)
        q_target = float(q_values.get(target_action, 0.0))
        q_logged = float(q_values.get(logged_action, 0.0))
        correction = 0.0
        if target_action == logged_action:
            supported += 1
            weight = 1.0 / effective_propensity
            ips_value = weight * reward
            ips_values.append(ips_value)
            weights.append(weight)
            correction = weight * (reward - q_logged)
            policy.update(logged_action, int(reward > 0))
        else:
            ips_values.append(0.0)
        values.append(q_target + correction)
        observed_rewards.append(reward)
        subjects.append(str(row.get(subject_column, row.get("row_id", ""))))
        decisions.append(
            {
                "row_id": row.get("row_id"),
                "logged_action": logged_action,
                "target_action": target_action,
                "reward": reward,
                "propensity": propensity,
                "weight": 1.0 / effective_propensity if target_action == logged_action else 0.0,
            }
        )

    valid = len(values)
    if not valid:
        return CausalEvaluation(
            policy=policy.name,
            estimator="doubly_robust",
            value=0.0,
            ips=0.0,
            snips=0.0,
            observed_rate=0.0,
            support_rate=0.0,
            valid_rows=0,
            excluded_rows=excluded,
            clipped_rows=clipped,
            effective_sample_size=0.0,
            propensity_mean=None,
            confidence_interval=(0.0, 0.0),
            decisions=[],
        )

    snips = sum(ips_values) / sum(weights) if weights else 0.0
    return CausalEvaluation(
        policy=policy.name,
        estimator="doubly_robust",
        value=sum(values) / valid,
        ips=sum(ips_values) / valid,
        snips=snips,
        observed_rate=sum(observed_rewards) / valid,
        support_rate=supported / valid,
        valid_rows=valid,
        excluded_rows=excluded,
        clipped_rows=clipped,
        effective_sample_size=(sum(weights) ** 2 / sum(weight**2 for weight in weights))
        if weights
        else 0.0,
        propensity_mean=sum(1.0 / weight for weight in weights) / valid,
        confidence_interval=_bootstrap_interval(
            values,
            subjects,
            samples=bootstrap_samples,
            seed=seed,
        ),
        decisions=decisions,
    )


def _bootstrap_interval(
    values: list[float],
    subjects: list[str],
    *,
    samples: int,
    seed: int,
) -> tuple[float, float]:
    if len(values) < 2 or samples <= 0:
        mean = sum(values) / max(len(values), 1)
        return mean, mean
    groups: dict[str, list[float]] = {}
    for subject, value in zip(subjects, values, strict=True):
        groups.setdefault(subject, []).append(value)
    group_values = list(groups.values())
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        drawn = [rng.choice(group_values) for _ in group_values]
        means.append(sum(value for group in drawn for value in group) / sum(len(group) for group in drawn))
    means.sort()
    return means[int(0.025 * (len(means) - 1))], means[int(0.975 * (len(means) - 1))]
