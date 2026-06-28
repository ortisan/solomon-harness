## SLIs and SLOs


- SLI = good events / valid events, expressed as a ratio. Define the SLI type explicitly: availability, latency, freshness, correctness, or throughput. Write the exact numerator and denominator (for example, latency SLI = requests served under 300 ms / all valid requests).
- Set SLO targets with their error budget stated. Monthly downtime budgets (calendar month, ~30.44 days): 99.9% ≈ 43m 49s; 99.95% ≈ 21m 54s; 99.99% ≈ 4m 23s. Pick the tier the product actually needs; over-tight SLOs waste budget and create false pages.
- Error budget = 1 - SLO. The budget governs release velocity: when it is exhausted, stop shipping risk and spend the budget on reliability work.
- Base SLIs on what the user experiences (server-side request success and latency, or client-side real-user monitoring), not on internal proxies like CPU.
