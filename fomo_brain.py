from datetime import datetime, timezone
import json
import urllib.parse
import urllib.request

# FOMO Radar v7 - Graduation + Event Learning Lab
SEARCHES = ["pump", "meme", "doge", "pepe", "cat", "moon", "coin", "graduated", "launchpad"]

# Fase actual: APRENDIZAJE. No compra, no firma, no mueve fondos.
LEARNING_ONLY = True

# EVENT RADAR v7
# Fuentes sociales se activarán únicamente mediante feeds/API autorizados.
# Mientras no exista una fuente conectada, NO se fabrican eventos.
EVENT_RADAR_ENABLED = True
SOCIAL_FEED_CONNECTED = False
EVENT_KEYWORDS = [
    "meme", "memecoin", "coin", "token", "crypto",
    "doge", "pepe", "pump", "moon"
]
EVENT_ACCOUNTS = [
    "realDonaldTrump"
]

# Filtros iniciales
MIN_LIQUIDITY = 5_000
MAX_MARKET_CAP = 5_000_000
MIN_VOLUME_1H = 5_000

# Solo referencia para una futura fase de gestion de riesgo.
# Esta version NO ejecuta compras.
MAX_EXPOSURE_EUR = 10.0

MEMORY_FILE = "fomo_memory.json"
EVENT_MEMORY_FILE = "fomo_event_memory.json"


def pedir_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "FOMO-Brain/5.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def numero(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def variacion(actual, previo):
    try:
        actual = float(actual)
        previo = float(previo)

        if previo == 0:
            return None

        return ((actual - previo) / previo) * 100

    except (TypeError, ValueError):
        return None


def edad_par_minutos(pair):
    creado_ms = numero(pair.get("pairCreatedAt"))

    if creado_ms <= 0:
        return None

    try:
        creado = datetime.fromtimestamp(
            creado_ms / 1000,
            tz=timezone.utc
        )

        return max(
            0.0,
            (
                datetime.now(timezone.utc) - creado
            ).total_seconds() / 60
        )

    except (ValueError, OSError, OverflowError):
        return None


def clasificar_token(token):
    score = token["score"]
    edad = token.get("ageMinutes")
    ratio = token.get("buyRatio5m", 0)
    trades = token.get("trades5m", 0)

    # Candidato especialmente interesante:
    # joven + actividad + dominio comprador.
    if (
        edad is not None
        and edad <= 60
        and trades >= 20
        and ratio >= 0.65
        and score >= 7
    ):
        return "EARLY FUERTE"

    if (
        edad is not None
        and edad <= 180
        and ratio >= 0.55
        and score >= 5
    ):
        return "VIGILAR"

    if score >= 6:
        return "MOMENTUM"

    return "NORMAL"


def analizar_par(pair):
    liquidity = numero(
        (pair.get("liquidity") or {}).get("usd")
    )

    market_cap = numero(
        pair.get("marketCap") or pair.get("fdv")
    )

    volume = pair.get("volume") or {}
    vol_1h = numero(volume.get("h1"))
    vol_5m = numero(volume.get("m5"))

    changes = pair.get("priceChange") or {}
    change_1h = numero(changes.get("h1"))
    change_5m = numero(changes.get("m5"))

    # Compras y ventas recientes
    txns = pair.get("txns") or {}
    tx_5m = txns.get("m5") or {}

    buys_5m = int(numero(tx_5m.get("buys")))
    sells_5m = int(numero(tx_5m.get("sells")))

    trades_5m = buys_5m + sells_5m

    buy_ratio_5m = (
        buys_5m / trades_5m
        if trades_5m > 0
        else 0.0
    )

    age_minutes = edad_par_minutos(pair)

    # Filtros basicos
    if liquidity < MIN_LIQUIDITY:
        return None

    if market_cap <= 0 or market_cap > MAX_MARKET_CAP:
        return None

    if vol_1h < MIN_VOLUME_1H:
        return None

    if change_5m <= 0 and change_1h <= 0:
        return None

    score = 0

    # Liquidez
    if liquidity >= 10_000:
        score += 1

    # Volumen respecto a liquidez
    if liquidity > 0 and vol_1h / liquidity >= 0.10:
        score += 2

    if liquidity > 0 and vol_1h / liquidity >= 0.50:
        score += 2

    # Momentum de precio
    if change_5m > 2:
        score += 1

    if change_1h > 5:
        score += 1

    if change_1h > 10:
        score += 2

    # Actividad compradora reciente
    if trades_5m >= 20 and buy_ratio_5m >= 0.60:
        score += 1

    # Token/par muy joven
    if age_minutes is not None and age_minutes <= 60:
        score += 1

    # Bonus por volumen fuerte en 5 minutos
    if (
        liquidity > 0
        and vol_5m / liquidity >= 0.10
    ):
        score += 1

    # Penalizacion:
    # evitar perseguir una subida que ya sea demasiado vertical
    if change_1h > 150:
        score -= 2

    base = pair.get("baseToken") or {}

    resultado = {
        "symbol": base.get("symbol", "?"),
        "name": base.get("name", "?"),
        "address": base.get("address", "?"),
        "pair": pair.get("pairAddress", "?"),
        "chain": pair.get("chainId", "?"),
        "dex": pair.get("dexId", "?"),
        "price": pair.get("priceUsd", "?"),
        "mc": market_cap,
        "liquidity": liquidity,
        "vol1h": vol_1h,
        "vol5m": vol_5m,
        "change5m": change_5m,
        "change1h": change_1h,
        "buys5m": buys_5m,
        "sells5m": sells_5m,
        "trades5m": trades_5m,
        "buyRatio5m": buy_ratio_5m,
        "ageMinutes": age_minutes,
        "score": score,
        "url": pair.get("url", "")
    }

    resultado["estadoEarly"] = clasificar_token(
        resultado
    )

    return resultado


def cargar_memoria():
    try:
        with open(MEMORY_FILE, "r") as archivo:
            memoria = json.load(archivo)

        if isinstance(memoria, list):
            return memoria

    except (FileNotFoundError, json.JSONDecodeError):
        pass

    return []


def comparar_con_memoria(ranking):
    memoria = cargar_memoria()

    print("")
    print("🧠 EVOLUCION DESDE LA ULTIMA LECTURA")

    for token in ranking[:10]:
        anteriores = [
            x for x in memoria
            if x.get("address") == token["address"]
            and x.get("chain") == token["chain"]
        ]

        if not anteriores:
            print("")
            print(
                f"🆕 {token['symbol']}: NUEVO EN EL RADAR "
                f"| {token['estadoEarly']}"
            )
            continue

        anterior = anteriores[-1]

        precio = variacion(
            token["price"],
            anterior.get("price")
        )

        mc = variacion(
            token["mc"],
            anterior.get("mc")
        )

        liquidez = variacion(
            token["liquidity"],
            anterior.get("liquidity")
        )

        volumen = variacion(
            token["vol1h"],
            anterior.get("vol1h")
        )

        volumen_5m = variacion(
            token["vol5m"],
            anterior.get("vol5m")
        )

        compras = variacion(
            token["buys5m"],
            anterior.get("buys5m")
        )

        score_anterior = int(
            anterior.get("score", 0)
        )

        delta_score = (
            token["score"] - score_anterior
        )

        print("")
        print(
            f"{token['symbol']} | "
            f"ultima lectura: {anterior.get('hora')}"
        )

        if precio is not None and mc is not None:
            print(
                f"precio={precio:+.2f}% "
                f"| MC={mc:+.2f}%"
            )
        else:
            print("precio/MC: sin comparacion")

        if liquidez is not None and volumen is not None:
            print(
                f"liquidez={liquidez:+.2f}% "
                f"| volumen1h={volumen:+.2f}%"
            )
        else:
            print(
                "liquidez/volumen1h: "
                "sin comparacion"
            )

        if volumen_5m is not None:
            print(
                f"volumen5m={volumen_5m:+.2f}%"
            )

        if compras is not None:
            print(
                f"compras5m={compras:+.2f}%"
            )

        print(
            f"score={score_anterior}/12 "
            f"-> {token['score']}/12 "
            f"({delta_score:+d})"
        )

        senales = 0

        if precio is not None and precio > 0:
            senales += 1

        if volumen is not None and volumen > 10:
            senales += 1

        if liquidez is not None and liquidez > 0:
            senales += 1

        if delta_score > 0:
            senales += 1

        if token["buyRatio5m"] >= 0.60:
            senales += 1

        if (
            token["ageMinutes"] is not None
            and token["ageMinutes"] <= 60
        ):
            senales += 1

        if senales >= 5:
            estado = "🔥 ACELERACION FUERTE"
        elif senales >= 3:
            estado = "🚀 ACELERANDO"
        elif senales >= 1:
            estado = "👀 MIXTO / VIGILAR"
        else:
            estado = "📉 PERDIENDO MOMENTUM"

        print(f"estado={estado}")


def guardar_memoria(ranking):
    ahora = datetime.now(
        timezone.utc
    ).isoformat()

    memoria = cargar_memoria()

    for token in ranking[:10]:
        memoria.append({
            "hora": ahora,
            "symbol": token["symbol"],
            "name": token["name"],
            "address": token["address"],
            "chain": token["chain"],
            "price": token["price"],
            "mc": token["mc"],
            "liquidity": token["liquidity"],
            "vol1h": token["vol1h"],
            "vol5m": token["vol5m"],
            "change5m": token["change5m"],
            "change1h": token["change1h"],
            "buys5m": token["buys5m"],
            "sells5m": token["sells5m"],
            "trades5m": token["trades5m"],
            "buyRatio5m": token["buyRatio5m"],
            "ageMinutes": token["ageMinutes"],
            "score": token["score"],
            "estadoEarly": token["estadoEarly"]
        })

    # Limitar crecimiento del historial
    memoria = memoria[-1000:]

    with open(MEMORY_FILE, "w") as archivo:
        json.dump(
            memoria,
            archivo,
            indent=2
        )


def cargar_eventos():
    """Carga eventos sociales ya verificados.

    V7 no hace scraping de X. Cuando conectemos un feed/API autorizado,
    esta función será el punto de entrada. Hasta entonces devuelve [].
    """
    if not EVENT_RADAR_ENABLED or not SOCIAL_FEED_CONNECTED:
        return []

    try:
        with open(EVENT_MEMORY_FILE, "r") as archivo:
            eventos = json.load(archivo)
        return eventos if isinstance(eventos, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def relacion_evento_token(token, eventos):
    """Relaciona por texto un token con eventos verificados recientes."""
    symbol = str(token.get("symbol", "")).lower()
    name = str(token.get("name", "")).lower()
    coincidencias = []

    for evento in eventos:
        texto = str(evento.get("text", "")).lower()
        palabras = evento.get("keywords", []) or []
        if (
            (symbol and len(symbol) >= 3 and symbol in texto)
            or (name and len(name) >= 4 and name in texto)
            or any(str(p).lower() in symbol + " " + name for p in palabras)
        ):
            coincidencias.append(evento)

    return coincidencias


def main():
    ahora = datetime.now(timezone.utc)

    print("🧠 FOMO Radar v7 - GRADUATION + EVENT LEARNING LAB")
    eventos = cargar_eventos()
    print(
        f"Event Radar: {'ACTIVO' if EVENT_RADAR_ENABLED else 'OFF'} "
        f"| feed social: {'CONECTADO' if SOCIAL_FEED_CONNECTED else 'PENDIENTE'} "
        f"| eventos verificados={len(eventos)}"
    )
    print(f"Hora UTC: {ahora.isoformat()}")
    print(
        "Buscando memecoins pequeñas "
        "con actividad temprana..."
    )

    candidatos = {}

    for termino in SEARCHES:
        try:
            query = urllib.parse.quote(termino)

            url = (
                "https://api.dexscreener.com/"
                "latest/dex/search/"
                f"?q={query}"
            )

            datos = pedir_json(url)

            for pair in datos.get("pairs") or []:
                resultado = analizar_par(pair)

                if resultado is None:
                    continue

                clave = (
                    resultado["chain"],
                    resultado["address"]
                )

                anterior = candidatos.get(clave)

                if (
                    anterior is None
                    or resultado["score"]
                    > anterior["score"]
                    or (
                        resultado["score"]
                        == anterior["score"]
                        and resultado["vol1h"]
                        > anterior["vol1h"]
                    )
                ):
                    candidatos[clave] = resultado

        except Exception as error:
            print(
                f"⚠️ Error buscando "
                f"{termino}: {error}"
            )

    candidatos = {
        k: v
        for k, v in candidatos.items()
        if v["score"] >= 2
    }

    ranking = sorted(
        candidatos.values(),
        key=lambda x: (
            x["score"],
            x["buyRatio5m"],
            -(
                x["ageMinutes"]
                if x["ageMinutes"] is not None
                else 999999
            ),
            x["vol5m"],
            x["vol1h"]
        ),
        reverse=True
    )

    print(
        f"Candidatos filtrados: "
        f"{len(ranking)}"
    )

    print("TOP 10 FOMO RADAR v7")

    if not ranking:
        print(
            "Sin candidatos que cumplan "
            "los filtros."
        )
        guardar_memoria(ranking)
        return

    comparar_con_memoria(ranking)
    guardar_memoria(ranking)

    for posicion, token in enumerate(
        ranking[:10],
        start=1
    ):
        print("")

        print(
            f"#{posicion} "
            f"{token['symbol']} "
            f"({token['name']}) "
            f"| score={token['score']}/12 "
            f"| {token['estadoEarly']} "
            f"| graduacion={'SI' if token.get('graduationCandidate') else 'NO'}"
        )

        print(
            f"chain={token['chain']} "
            f"| dex={token['dex']} "
            f"| precio=${token['price']}"
        )

        print(
            f"MC=${token['mc']:.0f} "
            f"| liquidez="
            f"${token['liquidity']:.0f}"
        )

        print(
            f"vol5m=${token['vol5m']:.0f} "
            f"| vol1h=${token['vol1h']:.0f}"
        )

        print(
            f"5m={token['change5m']:.2f}% "
            f"| 1h={token['change1h']:.2f}%"
        )

        edad = token["ageMinutes"]

        edad_txt = (
            f"{edad:.0f} min"
            if edad is not None
            else "desconocida"
        )

        print(
            f"edad={edad_txt} "
            f"| compras5m={token['buys5m']} "
            f"| ventas5m={token['sells5m']}"
        )

        print(
            f"presion compradora="
            f"{token['buyRatio5m']:.1%} "
            f"| netTrades5m={token.get('netTrades5m', 0):+d} "
            f"| vol/liquidez1h={token.get('volumeLiquidity1h', 0):.2f}x"
        )

        print(
            f"eventos_relacionados={token.get('eventMatches', 0)} "
            f"| fuentes={','.join(token.get('eventSources', [])) or '-'}"
        )

        print(
            f"token={token['address']}"
        )

        print(
            f"pair={token['pair']}"
        )

        print(
            f"url={token['url']}"
        )

    print("")
    print("✅ FOMO Radar v7 terminado")

    print(
        "Modo análisis únicamente | "
        f"exposición futura máxima: "
        f"€{MAX_EXPOSURE_EUR:.2f}"
    )


if __name__ == "__main__":
    main()
