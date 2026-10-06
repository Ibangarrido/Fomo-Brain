"""Prospective PAPER comparison: only the five-minute buy-count threshold differs."""


def run(ranking, simulator):
    print("LAB RATIO r1: 60% vs 52%; cuatro carteras nuevas de 100 EUR ficticios. NO sumar.")
    print("LAB RATIO: mismas reglas V10, costes y salidas; sin filtro adicional de velas.")
    for mode in ("early", "impulse"):
        for threshold in (0.60, 0.52):
            arm = str(round(threshold * 100))
            simulator(ranking, "fomo_lab_ratio_" + mode + "_" + arm + "_r1.json",
                      "LAB RATIO " + mode.upper() + " " + arm + "% r1",
                      confirm=True, entry_mode=mode, min_buy_ratio=threshold)
