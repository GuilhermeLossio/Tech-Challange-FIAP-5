from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Protocol

from src.data.legacy_hillstrom import LEGACY_ACTIONS

ACTIONS = LEGACY_ACTIONS


class BanditPolicy(Protocol):
    name: str

    def select_action(self) -> str: ...

    def update(self, action: str, reward: int) -> None: ...

    def snapshot(self) -> dict[str, object]: ...


def _best_action(values: dict[str, float]) -> str:
    return max(ACTIONS, key=lambda action: (values[action], -ACTIONS.index(action)))


@dataclass
class DeterministicBaseline:
    reward_rates: dict[str, float]
    name: str = "baseline"

    def select_action(self) -> str:
        return _best_action(self.reward_rates)

    def update(self, action: str, reward: int) -> None:
        return None

    def snapshot(self) -> dict[str, object]:
        return {
            "policy": self.name,
            "reward_rates": self.reward_rates,
            "selected_action": self.select_action(),
        }


class EpsilonGreedy:
    name = "epsilon_greedy"

    def __init__(self, epsilon: float = 0.1, seed: int = 42) -> None:
        self.epsilon = epsilon
        self._rng = random.Random(seed)
        self.counts = {action: 0 for action in ACTIONS}
        self.values = {action: 0.0 for action in ACTIONS}

    def select_action(self) -> str:
        if self._rng.random() < self.epsilon:
            return self._rng.choice(ACTIONS)

        untried = [action for action in ACTIONS if self.counts[action] == 0]
        if untried:
            return untried[0]

        return _best_action(self.values)

    def update(self, action: str, reward: int) -> None:
        self.counts[action] += 1
        count = self.counts[action]
        self.values[action] += (reward - self.values[action]) / count

    def snapshot(self) -> dict[str, object]:
        return {
            "policy": self.name,
            "epsilon": self.epsilon,
            "counts": self.counts,
            "values": self.values,
        }


class UCB1:
    name = "ucb"

    def __init__(self, confidence: float = 2.0) -> None:
        self.confidence = confidence
        self.counts = {action: 0 for action in ACTIONS}
        self.values = {action: 0.0 for action in ACTIONS}
        self.total_count = 0

    def select_action(self) -> str:
        untried = [action for action in ACTIONS if self.counts[action] == 0]
        if untried:
            return untried[0]

        scores = {
            action: self.values[action]
            + math.sqrt(self.confidence * math.log(self.total_count) / self.counts[action])
            for action in ACTIONS
        }
        return _best_action(scores)

    def update(self, action: str, reward: int) -> None:
        self.total_count += 1
        self.counts[action] += 1
        count = self.counts[action]
        self.values[action] += (reward - self.values[action]) / count

    def snapshot(self) -> dict[str, object]:
        return {
            "policy": self.name,
            "confidence": self.confidence,
            "counts": self.counts,
            "values": self.values,
            "total_count": self.total_count,
        }


class ThompsonSampling:
    name = "thompson_sampling"

    def __init__(self, seed: int = 42, alpha_prior: float = 1.0, beta_prior: float = 1.0) -> None:
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior
        self._rng = random.Random(seed)
        self.alpha = {action: alpha_prior for action in ACTIONS}
        self.beta = {action: beta_prior for action in ACTIONS}

    def select_action(self) -> str:
        samples = {
            action: self._rng.betavariate(self.alpha[action], self.beta[action])
            for action in ACTIONS
        }
        return _best_action(samples)

    def update(self, action: str, reward: int) -> None:
        if reward:
            self.alpha[action] += 1
        else:
            self.beta[action] += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "policy": self.name,
            "alpha_prior": self.alpha_prior,
            "beta_prior": self.beta_prior,
            "alpha": self.alpha,
            "beta": self.beta,
        }
