    # Enrich using only PREVIOUS snapshots. No lookahead or invented OHLC candles.
    observations = [continuation_observation(trend_observation(row, history), history) for row in observations]
    # Keep all observations, including rejects; never infer a trade from an API receipt.
    history = (history + observations)[-MAX_HISTORY:]
    with open(STATE + ".tmp", "w") as f:
        json.dump(history, f, indent=2, allow_nan=False)
    os.replace(STATE + ".tmp", STATE)
    report = {"version": "v13-hunter-r4-persistent-revisit", "at": now.isoformat(), "paper_only": True,
              "execution_verified": False, "trades": 0, "pairs_discovered": len(pairs),
              "observed": len(observations), "revisited_tokens_requested": len(extra_watch), "alerts": sum(r["discovery_alert"] for r in observations),
              "market_gate_passes": sum(r["market_gates_pass"] for r in observations),
              "trend_4h_watches": sum(r["trend_watch"] for r in observations),
              "continuation_watches": sum(r["continuation_watch"] for r in observations),
              "continuation_sufficient_data": sum(r["continuation_data_sufficient"] for r in observations),
              "research_buy_pressure_55pct": sum(r["continuation_buy_pressure_research"] for r in observations),
              "trend_4h_sufficient_data": sum(r["trend_data_sufficient"] for r in observations),
              "trend_4h_method": "timestamped observations; >=4h history required, not OHLC candles",
              "history_observations_24h": len(history),
              "source_coverage": "partial: DEX search + token profiles + manual watch; not a full launch stream",
              "errors": errors,
              "top_continuations": sorted((r for r in observations if r["continuation_watch"]),
                                          key=lambda r: r["continuation_relative_volume"] or 0, reverse=True)[:30],
              "top_trends": sorted((r for r in observations if r["trend_watch"]),
                                   key=lambda r: r["trend_4h_pct_observed"] or 0, reverse=True)[:30],
              "top_alerts": sorted((r for r in observations if r["discovery_alert"]),
                                   key=lambda r: (r["market_gates_pass"], r["trades_5m"] or 0),
                                   reverse=True)[:30]}
    with open(OUTPUT, "w") as f:
        json.dump(report, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k not in ("top_alerts", "top_continuations", "top_trends")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
