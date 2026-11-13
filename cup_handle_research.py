"""Fixed-window hypothesis on validated closed 1m bars; observation only."""


def detect(bars):
    result = {"version": "cup-handle-r1", "status": "INSUFFICIENT_DATA",
              "changes_orders": False, "future_outcome_verified": False,
              "required_closed_bars": 31, "timeframe": "1m"}
    if len(bars) < 31:
        return result
    window = bars[-31:]
    if any(b[0] - a[0] != 60 for a, b in zip(window, window[1:])):
        return dict(result, reason="gaps_in_closed_bars")
    if any(r[5] <= 0 for r in window):
        return dict(result, reason="empty_volume_intervals")
    cup, handle, last = window[:25], window[25:30], window[-1]
    resistance = max(r[2] for r in cup[:5])
    bottom = min(r[3] for r in cup)
    bottom_index = min(range(25), key=lambda i: cup[i][3])
    depth = 1 - bottom / resistance
    handle_low = min(r[3] for r in handle)
    baseline = sum(r[5] for r in window[-21:-1]) / 20
    multiple = last[5] / baseline
    shape = (7 <= bottom_index <= 17 and .08 <= depth <= .40
             and .95 * resistance <= cup[-1][4] <= resistance
             and max(r[2] for r in cup[5:] + handle) <= resistance * 1.01
             and .01 <= 1 - handle_low / resistance <= depth / 2
             and handle_low > bottom)
    breakout = last[4] > resistance and last[4] > last[1]
    status = ("BREAKOUT_WITH_VOLUME" if multiple >= 2 else "BREAKOUT_CONTROL") \
        if shape and breakout else "NO_PATTERN"
    return dict(result, status=status, resistance=resistance,
                cup_depth_pct=100 * depth, handle_depth_pct=100 * (1-handle_low/resistance),
                volume_multiple=multiple, signal_closed_at=last[0]+60,
                signal_id=f"cup-handle-r1:{int(last[0])}",
                invalidation_close_below=resistance,
                scope="fixed 31-minute proxy; not proof of a rounded cup or profitable edge")
