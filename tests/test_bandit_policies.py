from __future__ import annotations

from src.bandits.policies import UCB1, DeterministicBaseline, EpsilonGreedy, ThompsonSampling


def test_baseline_selects_highest_reward_rate_action() -> None:
    policy = DeterministicBaseline(
        reward_rates={
            "legacy_variant_a": 0.01,
            "legacy_variant_b": 0.04,
            "legacy_control": 0.02,
        }
    )

    assert policy.select_action() == "legacy_variant_b"


def test_epsilon_greedy_updates_running_reward_value() -> None:
    policy = EpsilonGreedy(epsilon=0.0, seed=42)

    action = policy.select_action()
    policy.update(action, 1)
    policy.update(action, 0)

    assert policy.counts[action] == 2
    assert policy.values[action] == 0.5


def test_ucb_selects_untried_actions_without_division_by_zero() -> None:
    policy = UCB1()

    assert policy.select_action() == "legacy_variant_a"
    policy.update("legacy_variant_a", 1)

    assert policy.select_action() == "legacy_variant_b"


def test_thompson_sampling_is_deterministic_with_seed() -> None:
    first = ThompsonSampling(seed=7)
    second = ThompsonSampling(seed=7)

    first_actions = [first.select_action() for _ in range(5)]
    second_actions = [second.select_action() for _ in range(5)]

    assert first_actions == second_actions


def test_thompson_sampling_updates_beta_parameters() -> None:
    policy = ThompsonSampling(seed=42)

    policy.update("legacy_variant_a", 1)
    policy.update("legacy_variant_a", 0)

    assert policy.alpha["legacy_variant_a"] == 2.0
    assert policy.beta["legacy_variant_a"] == 2.0
