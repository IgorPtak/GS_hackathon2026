# Trade limit breach

Rejected trade {{payload.tradeId}} on desk {{payload.desk}} ({{payload.currency}} {{payload.notional}}).

1. Check the current limit utilisation for counterparty {{payload.counterparty}} in the limits dashboard.
2. Confirm with trader {{payload.trader}} whether the trade is still required (needs approval from the desk head before the limit is touched).
3. If a temporary limit increase is needed, open a ticket for the risk team. `open-ticket summary="Limit increase for {{payload.counterparty}}" team=risk`
4. Record the decision in the alert before resolving it.
