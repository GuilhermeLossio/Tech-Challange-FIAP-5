# Glossary - ECloe

| Term | Definition |
|------|------------|
| Adaptive experimentation | Experimentation approach that updates allocation decisions as new evidence arrives |
| Arm | One available option in a bandit problem, such as a financial offer |
| Bandit | Algorithmic framework that balances exploration and exploitation across arms |
| Baseline | Reference policy used to compare policy performance |
| Context | Minimized session information used for decisioning, such as segment and channel |
| Conversion rate | Share of decisions that produce a conversion reward |
| Cumulative regret | Accumulated difference between selected actions and the estimated best action |
| Decision API | Planned API that receives context and returns a selected offer |
| Decision ID | Identifier used to link a decision to later reward events |
| Delayed reward | Reward observed after the initial decision window |
| Drift | Change in data or behavior patterns over time |
| Eligible offer | Offer already allowed by upstream business or compliance rules |
| Epsilon-Greedy | Adaptive policy that explores randomly with probability `epsilon` and otherwise exploits the best known arm |
| Exploration | Selecting an uncertain option to learn about its reward |
| Exploitation | Selecting the option currently estimated to perform best |
| Fairness index | Metric used to compare relative exposure across synthetic or source-derived segments |
| Golden Set | Small curated set of deterministic validation cases used for Demo Day explanation |
| MLflow | Experiment tracking tool planned for local MLOps logging |
| MLOps | Practices for versioning, evaluating, deploying, and monitoring ML systems |
| Policy | Decision strategy used to select an offer |
| Policy version | Version identifier for the active policy configuration or artifact |
| Reason code | Auditable explanation tag attached to a decision |
| Reward | Numeric feedback signal such as click or conversion |
| Thompson Sampling | Bayesian bandit policy planned as ECloe's main candidate policy |
| UCB | Upper Confidence Bound policy that adds an uncertainty bonus to average reward estimates |
