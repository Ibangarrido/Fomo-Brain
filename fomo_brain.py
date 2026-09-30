from datetime import datetime

MAX_EXPOSURE_EUR = 10.0

def analyze_token(price_change_pct, volume_change_pct, holders_change_pct):

    score = 0

    if price_change_pct > 5:

        score += 1

    if volume_change_pct > 20:

        score += 1

    if holders_change_pct > 2:

        score += 1

    if score >= 3:

        signal = "WATCH"

    elif score == 2:

        signal = "WAIT"

    else:

        signal = "NO SIGNAL"

    return {

        "timestamp": datetime.utcnow().isoformat(),

        "signal": signal,

        "max_exposure_eur": MAX_EXPOSURE_EUR,

        "price_change_pct": price_change_pct,

        "volume_change_pct": volume_change_pct,

        "holders_change_pct": holders_change_pct

    }

print(analyze_token(0, 0, 0))
