from datetime import datetime, timezone
import json
import urllib.parse
import urllib.request

# FOMO Radar v4
SEARCHES = ["pump", "meme", "doge", "pepe", "cat", "moon", "coin"]

# Filtros iniciales para buscar proyectos pequeños
MIN_LIQUIDITY = 5_000
MAX_MARKET_CAP = 5_000_000
MIN_VOLUME_1H = 5_000
MAX_EXPOSURE_EUR = 10.0


def pedir_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "FOMO-Brain/3.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode())


def numero(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return 0.0


def analizar_par(pair):
    liquidity = numero((pair.get("liquidity") or {}).get("usd"))
    market_cap = numero(pair.get("marketCap") or pair.get("fdv"))

    volume = pair.get("volume") or {}
    vol_1h = numero(volume.get("h1"))

    changes = pair.get("priceChange") or {}
    change_1h = numero(changes.get("h1"))
    change_5m = numero(changes.get("m5"))

    if liquidity < MIN_LIQUIDITY:
        return None

    if market_cap <= 0 or market_cap > MAX_MARKET_CAP:
        return None

    if vol_1h < MIN_VOLUME_1H:
        return None
    if change_5m <= 0 and change_1h <= 0:
        return None
    score = 0

    # Liquidez suficiente
    if liquidity >= 10_000:
        score += 1

    # Actividad de volumen respecto a liquidez
    if liquidity > 0 and vol_1h / liquidity >= 0.10:
        score += 2

    if liquidity > 0 and vol_1h / liquidity >= 0.50:
        score += 2

    # Momentum
    if change_5m > 2:
        score += 1

    if change_1h > 5:
        score += 1

    if change_1h > 10:
        score += 2

    # Evitar premiar una subida ya extremadamente vertical
    if change_1h > 150:
        score -= 2

    base = pair.get("baseToken") or {}

    return {
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
        "change5m": change_5m,
        "change1h": change_1h,
        "score": score,
        "url": pair.get("url", "")
    }


def main():
    ahora = datetime.now(timezone.utc)

    print("🧠 FOMO Radar v3")
    print(f"Hora UTC: {ahora.isoformat()}")
    print("Buscando memecoins pequeñas con actividad...")

    candidatos = {}

    for termino in SEARCHES:
        try:
            query = urllib.parse.quote(termino)
            url = (
                "https://api.dexscreener.com/latest/dex/search/"
                f"?q={query}"
            )

            datos = pedir_json(url)

            for pair in datos.get("pairs") or []:
                resultado = analizar_par(pair)

                if resultado is None:
                    continue

                # Dirección + chain evita duplicados básicos
                clave = (
                    resultado["chain"],
                    resultado["address"]
                )

                anterior = candidatos.get(clave)

                if (
                    anterior is None
                    or resultado["score"] > anterior["score"]
                    or (
                        resultado["score"] == anterior["score"]
                        and resultado["vol1h"] > anterior["vol1h"]
                    )
                ):
                    candidatos[clave] = resultado

        except Exception as error:
            print(f"⚠️ Error buscando {termino}: {error}")
    candidatos = {
        k: v for k, v in candidatos.items() if v["score"] >= 3
    }
    ranking = sorted(
        candidatos.values(),
        key=lambda x: (
            x["score"],
            x["vol1h"],
            x["change1h"]
        ),
        reverse=True
    )

    print(f"Candidatos filtrados: {len(ranking)}")
    print("TOP 10 FOMO RADAR v4")

    if not ranking:
        print("Sin candidatos que cumplan los filtros.")
        guardar_memoria(ranking)
        return
    comparar_con_memoria(ranking)
    guardar_memoria(ranking)
    for posicion, token in enumerate(ranking[:10], start=1):
        print("")
        print(
            f"#{posicion} {token['symbol']} ({token['name']}) "
            f"| score={token['score']}/9"
        )
        print(
            f"chain={token['chain']} | dex={token['dex']} "
            f"| precio=${token['price']}"
        )
        print(
            f"MC=${token['mc']:.0f} "
            f"| liquidez=${token['liquidity']:.0f} "
            f"| vol1h=${token['vol1h']:.0f}"
        )
        print(
            f"5m={token['change5m']:.2f}% "
            f"| 1h={token['change1h']:.2f}%"
        )
        print(f"token={token['address']}")
        print(f"pair={token['pair']}")
        print(f"url={token['url']}")

    print("")
    print("✅ Radar v3 terminado")
    print(
        f"Modo análisis únicamente | "
        f"exposición futura máxima: €{MAX_EXPOSURE_EUR:.2f}"
    )
def comparar_con_memoria(ranking):
    try:
        with open("fomo_memory.json", "r") as archivo:
            memoria = json.load(archivo)
        if not isinstance(memoria, list):
            memoria = []
    except (FileNotFoundError, json.JSONDecodeError):
        memoria = []

    print("")
    print("🧠 EVOLUCION DESDE LA ULTIMA LECTURA")

    for token in ranking[:10]:
        anteriores = [
            x for x in memoria
            if x.get("address") == token["address"]
            and x.get("chain") == token["chain"]
        ]

        if not anteriores:
            print(f"{token['symbol']}: NUEVO EN EL RADAR")
            continue

        anterior = anteriores[-1]

        def variacion(actual, previo):
            if previo in (None, 0):
                return None
            return ((actual - previo) / previo) * 100

        precio = variacion(token["price"], anterior.get("price"))
        mc = variacion(token["mc"], anterior.get("mc"))
        liquidez = variacion(
            token["liquidity"], anterior.get("liquidity")
        )
        volumen = variacion(token["vol1h"], anterior.get("vol1h"))
        score_anterior = anterior.get("score", 0)
        delta_score = token["score"] - score_anterior

        print("")
        print(f"{token['symbol']} | ultima lectura: {anterior.get('hora')}")
        print(
            f"precio={precio:+.2f}% | MC={mc:+.2f}%"
            if precio is not None and mc is not None
            else "precio/MC: sin comparacion"
        )
        print(
            f"liquidez={liquidez:+.2f}% | volumen1h={volumen:+.2f}%"
            if liquidez is not None and volumen is not None
            else "liquidez/volumen: sin comparacion"
        )
        print(
            f"score={score_anterior}/9 -> {token['score']}/9 "
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

        if senales >= 3:
            estado = "ACELERANDO"
        elif senales >= 1:
            estado = "MIXTO"
        else:
            estado = "PERDIENDO MOMENTUM"

        print(f"estado={estado}")

def guardar_memoria(ranking):
    ahora = datetime.now(timezone.utc).isoformat()

    # Recuperar el historial de ejecuciones anteriores
    try:
        with open("fomo_memory.json", "r") as archivo:
            memoria = json.load(archivo)
            if not isinstance(memoria, list):
                memoria = []
    except (FileNotFoundError, json.JSONDecodeError):
        memoria = []

    # Añadir las nuevas observaciones sin borrar las anteriores
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
            "change5m": token["change5m"],
            "change1h": token["change1h"],
            "score": token["score"]
        })

    # Evitar que el archivo crezca indefinidamente
    memoria = memoria[-1000:]

    with open("fomo_memory.json", "w") as archivo:
        json.dump(memoria, archivo, indent=2)
if __name__ == "__main__":
    main()
