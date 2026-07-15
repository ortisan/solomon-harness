## Tooling


- Backtest engines: vectorbt or backtrader for research, QuantConnect Lean or zipline-reloaded for fuller event-driven simulation.
- Quant ML: mlfinlab-style utilities for purged CV, fractional differentiation, and triple-barrier labels; PyPortfolioOpt for allocation; statsmodels for diagnostics.
- DRL: a Gym-style environment with costs baked into the reward; standard RL libraries for agents.
- Core stack: numpy, pandas with strict dtype and index hygiene; fix seeds across numpy, the ML framework, and the env.
