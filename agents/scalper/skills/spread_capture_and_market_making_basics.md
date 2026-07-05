# Spread Capture And Market Making Basics

This skill governs the design of quoting strategies that earn the bid-ask spread: how to place and re-center two-sided quotes, how to control inventory risk, how to skew, and — most important — how to recognize the conditions under which spread capture stops paying and quotes must widen or pull. Spread capture looks like free money in a calm backtest; the entire discipline is in the filters that keep it from being a toxicity collector.

## The economics of a quoted round trip

A passive round trip earns the quoted spread plus any maker rebates, and pays fees, adverse selection, and inventory risk. Write it as an expectation per round trip: E = spread + 2 x rebate - fees - adverse_selection - inventory_cost. Adverse selection is measured from markouts on your own fills; inventory cost is the volatility you carry between the two legs. On a large-tick instrument with a one-tick spread, the gross capture is fixed, so the design degrees of freedom are all on the cost side: get filled earlier in the queue (less toxic flow), avoid quoting into toxic conditions, and shed inventory fast. If markout losses exceed spread plus rebate on average, no volume increase fixes it — the strategy is buying losses at scale.

## Reservation price and inventory control (Avellaneda-Stoikov, qualitatively)

The Avellaneda-Stoikov framework gives the right mental model even when its formulas are not implemented literally. Two ideas carry it. First, quote around a reservation price, not the mid: the reservation price is the mid shifted against your inventory, by an amount that grows with inventory size, price variance, and risk aversion, and shrinks as the trading horizon runs out. Long inventory pushes both quotes down, making the sell more likely and the additional buy less likely. Second, the optimal total spread widens with volatility and risk aversion and tightens with the intensity of incoming order flow: quote wide when the market moves a lot per fill opportunity, tight when flow is dense and calm. Practical use: implement inventory-dependent quote centering and volatility-dependent spread width as explicit functions with capped parameters, and expose both as tunables on the hypothesis card rather than burying them in code.

## Skewing

Skew is the asymmetric adjustment of the two quotes and their sizes:

- Inventory skew: tighten and upsize the quote that reduces inventory, widen or downsize the one that grows it. This is the reservation-price idea made discrete and should always be on.
- Signal skew: lean the quotes in the direction of a short-horizon alpha (for example, book imbalance): improve the quote on the side the signal favors, back off the other. Signal skew converts a pure spread-capture strategy into a hybrid, and its added edge must be attributed separately in evaluation.
- Size skew without price skew is often the better first tool on large-tick instruments, where moving price means losing the queue.

Every skew must respect priority mechanics: repricing a quote sends it to the back of the queue, so a skew rule that repositions constantly destroys the queue value it exists to protect. Define a minimum edge threshold before a reprice is allowed.

## When spread capture stops paying

The strategy must know when not to quote. Concrete filters, all cheap to compute:

- Volatility filter: when short-window realized volatility (for example, 30 to 60 seconds of mid returns) exceeds a threshold calibrated so expected adverse selection outruns spread plus rebate, widen quotes proportionally or pull them.
- Toxicity filter: monitor markouts on recent own fills and flow-toxicity proxies (aggressor-volume bursts, VPIN-style imbalance measures). Two or three consecutive toxic fills on the same side is a stand-down trigger, not a coincidence.
- Sweep detection: a single aggressor clearing multiple levels signals informed or forced flow; cancel resting quotes immediately and re-enter only after the book rebuilds.
- Event calendar: pull quotes a defined window before scheduled releases (CPI, FOMC, payrolls, earnings for single names) and re-enter on a defined condition, not on a timer alone.
- Queue evaporation: when the queue ahead of your order shrinks abnormally fast, the level is about to trade through; cancelling costs the queue position but keeps the markout.

Each filter needs a stated threshold, a stated action (widen, pull, one-sided quote), and a stated re-entry condition. "Trader judgment" is not a filter.

## Common pitfalls

- Counting fills as wins: high fill rates with negative markouts is the signature of a toxicity collector.
- Quoting through news events because the backtest window happened to contain none.
- Inventory limits without a shedding mechanism, so the strategy sits at max inventory as a directional bet it never priced.
- Repricing on every signal tick, burning queue priority that was the strategy's actual asset.
- Ignoring rebate-tier assumptions, so the economics silently assume a fee schedule the account does not have.
- Backtesting quotes with instant, certain fills at the touch; passive fill probability must come from a queue model.

## Definition of done

- [ ] The per-round-trip economics are written out with numbers: spread, rebates, fees, measured adverse selection, inventory cost.
- [ ] Quote centering is inventory-dependent and spread width is volatility-dependent, with capped, card-documented parameters.
- [ ] Skew rules respect queue priority, with a minimum-edge threshold for any reprice.
- [ ] Volatility, toxicity, sweep, and event filters exist with explicit thresholds, actions, and re-entry conditions.
- [ ] Inventory has a hard cap and a defined shedding path (passive first, aggressive at a stated limit).
- [ ] The evaluation plan attributes PnL to spread capture, rebates, and signal skew separately, and is handed to quant_trader for tick-level validation.
