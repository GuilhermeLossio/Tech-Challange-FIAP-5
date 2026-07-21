from __future__ import annotations

from src.bandits.policies import DeterministicBaseline, EpsilonGreedy, ThompsonSampling, UCB1


def test_baseline_selects_highest_reward_rate_action() -> None:
    policy = DeterministicBaseline(
        reward_rates={
            "mens_email": 0.01,
            "womens_email": 0.04,
            "no_email": 0.02,
        }
    )

    assert policy.select_action() == "womens_email"


def test_epsilon_greedy_updates_running_reward_value() -> None:
    policy = EpsilonGreedy(epsilon=0.0, seed=42)

    action = policy.select_action()
    policy.update(action, 1)
    policy.update(action, 0)

    assert policy.counts[action] == 2
    assert policy.values[action] == 0.5


def test_ucb_selects_untried_actions_without_division_by_zero() -> None:
    policy = UCB1()

    assert policy.select_action() == "mens_email"
    policy.update("mens_email", 1)

    assert policy.select_action() == "womens_email"


def test_thompson_sampling_is_deterministic_with_seed() -> None:
    first = ThompsonSampling(seed=7)
    second = ThompsonSampling(seed=7)

    first_actions = [first.select_action() for _ in range(5)]
    second_actions = [second.select_action() for _ in range(5)]

    assert first_actions == second_actions


def test_thompson_sampling_updates_beta_parameters() -> None:
    policy = ThompsonSampling(seed=42)

    policy.update("mens_email", 1)
    policy.update("mens_email", 0)

    assert policy.alpha["mens_email"] == 2.0
    assert policy.beta["mens_email"] == 2.0
