## Monitoring dashboards


- One overview dashboard per service, top to bottom by importance: golden signals / RED at the top, dependencies and saturation below, infra USE at the bottom. The on-call should diagnose from the first screen without scrolling.
- Show SLO state and error-budget remaining on the overview, not a separate hidden board. A dashboard without SLO context cannot tell you whether a spike matters.
- Use template variables (service, region, environment) instead of cloning dashboards. Dashboard sprawl is a maintenance failure mode.
- Annotate deploys, config changes, and feature-flag flips on the time axis so correlation with regressions is immediate.
- Render latency from histograms with `histogram_quantile`, render error rate as `errors/total`, and label panels with the unit and the percentile. No raw averages on a latency panel.
