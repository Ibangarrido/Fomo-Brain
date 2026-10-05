from datetime import datetime, timezone
import json
import urllib.parse
import urllib.request
import os
import math

# FOMO Brain v9 - DEX + FOMO Trader Radar + simulacion comparativa
# V9 sigue siendo PAPER ONLY: no firma, no compra y no mueve fondos.
SEARCHES = ["pump", "meme", "doge", "pepe", "cat", "moon", "coin", "graduated", "launchpad"]

# Fase actual: APRENDIZAJE. No compra, no firma, no mueve fondos.
LEARNING_ONLY = True

# FOMO TRADER RADAR V9
# Fuente opcional SOLO LECTURA. Debe ser un feed/API autorizado por el usuario/proveedor.
# Sin URL configurada, V9 sigue funcionando y declara radar FOMO desconectado.
FOMO_RADAR_FEED_URL = os.getenv("FOMO_RADAR_FEED_URL", "").strip()
FOMO_RADAR_TOKEN = os.getenv("FOMO_RADAR_TOKEN", "").strip()
FOMO_RADAR_CONNECTED = bool(FOMO_RADAR_FEED_URL)
FOMO_RADAR_STATUS = "PENDIENTE"
FOMO_RADAR_MAX_EVENTS = 500

# EVENT RADAR v8
# Fuentes sociales se activarán únicamente mediante feeds/API autorizados.
# Mientras no exista una fuente conectada, NO se fabrican eventos.
EVENT_RADAR_ENABLED = True
# Se activa automáticamente cuando GitHub tenga el secreto X_BEARER_TOKEN.
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "").strip()
SOCIAL_FEED_CONNECTED = bool(X_BEARER_TOKEN)
EVENT_KEYWORDS = [
    "meme", "memecoin", "coin", "token", "crypto",
    "doge", "pepe", "pump", "moon"
]
EVENT_ACCOUNTS = [
    "realDonaldTrump"
]

# Filtros iniciales
MIN_LIQUIDITY = 10_000
MAX_MARKET_CAP = 2_000_000
MIN_VOLUME_1H = 5_000

# Solo referencia para una futura fase de gestion de riesgo.
# Esta version NO ejecuta compras.
MAX_EXPOSURE_EUR = 10.0

MEMORY_FILE = "fomo_memory.json"
EVENT_MEMORY_FILE = "fomo_event_memory.json"
V9_FILE = "fomo_shadow_v9.json"
JSON_CACHE = {}
REJECTIONS = []
X_STATUS = "PENDIENTE"
STUDY_TOKENS = [
    ("solana", "6Kixbp4noymaazXvuNqjdHqaeYG7YVhpfcw5APxYAQk1"),
    ("solana", "E4X5HjWLZfHe3i1HWWutFdA7ywW7ytXWaCvEJV5Mpump"),
]


def descartar(pair, reason):
    REJECTIONS.append({"chain": pair.get("chainId"),
                       "address": (pair.get("baseToken") or {}).get("address"),
                       "pair": pair.get("pairAddress"), "reason": reason})
    return None


def pedir_json(url):
    if url in JSON_CACHE:
        return JSON_CACHE[url]
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "FOMO-Brain/8.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.loads(response.read().decode())
    JSON_CACHE[url] = data
    return data


def numero(valor):
    try:
        value = float(valor or 0)
        return value if math.isfinite(value) else 0.0
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

    if score >= 6 and trades >= 20 and ratio >= 0.60 and token.get("change5m", 0) > 0:
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
        return descartar(pair, f"liquidez < {MIN_LIQUIDITY:g} USD")

    if market_cap <= 0 or market_cap > MAX_MARKET_CAP:
        return descartar(pair, f"capitalizacion ausente o > {MAX_MARKET_CAP:g} USD")

    if vol_1h < MIN_VOLUME_1H:
        return descartar(pair, "volumen 1h < 5000 USD")

    if change_5m <= 0 and change_1h <= 0:
        return descartar(pair, "sin momentum positivo 5m/1h")

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
        "netTrades5m": buys_5m - sells_5m,
        "volumeLiquidity1h": vol_1h / liquidity if liquidity else None,
        "graduationStatus": "NO VERIFICADA",
        "url": pair.get("url", "")
    }

    resultado["estadoEarly"] = clasificar_token(
        resultado
    )

    return resultado



def consultar_fomo_trader_radar():
    """Lee un feed autorizado de actividad FOMO; nunca usa credenciales de la cuenta.

    Formato aceptado: lista JSON o {"events": [...]}.
    Cada evento debe identificar chain, address/tokenAddress, trader y side.
    Solo BUY verificados participan en la confluencia.
    """
    global FOMO_RADAR_STATUS
    if not FOMO_RADAR_CONNECTED:
        FOMO_RADAR_STATUS = "SIN FUENTE AUTORIZADA"
        return []

    headers = {"User-Agent": "FOMO-Brain/9.0", "Accept": "application/json"}
    if FOMO_RADAR_TOKEN:
        headers["Authorization"] = "Bearer " + FOMO_RADAR_TOKEN
    req = urllib.request.Request(FOMO_RADAR_FEED_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        FOMO_RADAR_STATUS = "ERROR CONTROLADO"
        print(f"FOMO Trader Radar: ERROR CONTROLADO | {type(exc).__name__}: {exc}")
        return []

    raw = payload.get("events", []) if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        FOMO_RADAR_STATUS = "FORMATO INVALIDO"
        return []

    events = []
    for e in raw[:FOMO_RADAR_MAX_EVENTS]:
        if not isinstance(e, dict):
            continue
        chain = str(e.get("chain") or e.get("chainId") or "").strip().lower()
        address = str(e.get("address") or e.get("tokenAddress") or "").strip()
        trader = str(e.get("trader") or e.get("wallet") or e.get("profile") or "").strip()
        side = str(e.get("side") or e.get("action") or "").strip().upper()
        verified = e.get("verified", True) is True
        if chain and address and trader and side in ("BUY", "SELL") and verified:
            events.append({"chain": chain, "address": address, "trader": trader,
                           "side": side, "verified": True,
                           "timestamp": e.get("timestamp") or e.get("created_at")})
    FOMO_RADAR_STATUS = "CONECTADO"
    return events


def aplicar_confluencia_fomo(candidatos, eventos):
    """Añade señal de confluencia sin convertirla en una recomendacion."""
    by_token = {}
    for e in eventos:
        if e["side"] != "BUY":
            continue
        key = (e["chain"], e["address"])
        by_token.setdefault(key, set()).add(e["trader"])

    for key, token in candidatos.items():
        traders = sorted(by_token.get((str(key[0]).lower(), key[1]), set()))
        token["fomoTraders"] = traders
        token["fomoConfluence"] = len(traders)
        # Bonus acotado: FOMO complementa, nunca sustituye liquidez/momentum.
        bonus = 2 if len(traders) >= 3 else 1 if len(traders) >= 2 else 0
        token["fomoBonus"] = bonus
        token["score"] += bonus
        token["estadoEarly"] = clasificar_token(token)
    return candidatos

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

    for token in ranking[:100]:
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
            "pair": token["pair"],
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
    memoria = memoria[-10000:]

    with open(MEMORY_FILE, "w") as archivo:
        json.dump(
            memoria,
            archivo,
            indent=2
        )


def cargar_eventos():
    """Carga eventos sociales verificados ya registrados.

    V8 no hace scraping de X. X_BEARER_TOKEN habilita el conector oficial
    mediante la API oficial. Sin credenciales,
    el radar sigue funcionando con cero eventos y nunca inventa datos.
    """
    try:
        with open(EVENT_MEMORY_FILE, "r") as archivo:
            eventos = json.load(archivo)
        return eventos if isinstance(eventos, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def consultar_x():
    """Consulta publicaciones recientes mediante la API oficial de X."""
    global X_STATUS
    if not EVENT_RADAR_ENABLED or not SOCIAL_FEED_CONNECTED:
        X_STATUS = "SIN CREDENCIALES" if not SOCIAL_FEED_CONNECTED else "OFF"
        return []

    query = "(crypto OR memecoin OR meme OR token OR coin) from:realDonaldTrump -is:retweet"
    params = urllib.parse.urlencode({
        "query": query,
        "max_results": 10,
        "tweet.fields": "created_at,author_id"
    })
    url = "https://api.x.com/2/tweets/search/recent?" + params
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + X_BEARER_TOKEN,
            "User-Agent": "FOMO-Brain/8.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        X_STATUS = "ERROR"
        print(f"X API: ERROR CONTROLADO | {type(exc).__name__}: {exc}")
        return []

    if payload.get("errors"):
        X_STATUS = "RESPUESTA CON ERRORES"
        print("X API: respuesta parcial/con errores; no confirma cobertura")
    else:
        X_STATUS = "CONSULTA OK"

    eventos = []
    for post in payload.get("data", []):
        texto = str(post.get("text", ""))
        lower = texto.lower()
        keywords = [k for k in EVENT_KEYWORDS if k in lower]
        eventos.append({
            "source": "X",
            "account": "realDonaldTrump",
            "id": post.get("id"),
            "created_at": post.get("created_at"),
            "text": texto,
            "keywords": keywords
        })
    return eventos


def guardar_eventos(eventos):
    """Persiste eventos para correlacionarlos entre ejecuciones."""
    with open(EVENT_MEMORY_FILE, "w") as archivo:
        json.dump(eventos[-200:], archivo, indent=2)


def resumen_event_radar(eventos):
    estado = X_STATUS
    return (
        f"Event Radar: {'ACTIVO' if EVENT_RADAR_ENABLED else 'OFF'} "
        f"| X oficial: {estado} "
        f"| eventos verificados={len(eventos)}"
    )


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


# Cartera de prueba: dinero virtual, sin wallets ni ordenes reales.
PAPER_FEE = 0.01
PAPER_SLIPPAGE = 0.02


def cotizar_posicion(pos):
    """Consulta el par exacto y comprueba identidad, precio y liquidez."""
    chain = urllib.parse.quote(pos["chain"], safe="")
    pair_id = urllib.parse.quote(pos["pair"], safe="")
    url = f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pair_id}"
    try:
        data = pedir_json(url)
    except Exception:
        # El endpoint del contrato puede seguir disponible si falla el del par.
        data = {"pairs": []}
    pair = next((p for p in data.get("pairs") or []
                 if p.get("chainId") == pos["chain"]
                 and p.get("pairAddress") == pos["pair"]
                 and (p.get("baseToken") or {}).get("address") == pos["address"]), None)
    original_pair = pos["pair"]
    if (pair is None or numero(pair.get("priceUsd")) <= 0
            or numero((pair.get("liquidity") or {}).get("usd")) < MIN_LIQUIDITY):
        # Buscar un mercado del MISMO contrato y cadena; nunca por nombre.
        candidates = pares_token(pos["chain"], pos["address"])
        valid = [p for p in candidates if identidad_par(p, pos["chain"], pos["address"])
                 and numero(p.get("priceUsd")) > 0
                 and numero((p.get("liquidity") or {}).get("usd")) >= MIN_LIQUIDITY]
        if valid:
            pair = max(valid, key=lambda p: numero((p.get("liquidity") or {}).get("usd")))
    if pair is None:
        raise ValueError("Sin par verificable del mismo contrato y cadena")
    price = numero(pair.get("priceUsd"))
    liquidity = numero((pair.get("liquidity") or {}).get("usd"))
    if price <= 0:
        raise ValueError("El par no tiene precio valido")
    if liquidity < MIN_LIQUIDITY:
        raise ValueError(f"Liquidez insuficiente ({liquidity:.2f} USD); salida no verificable")
    if pair["pairAddress"] != original_pair:
        pos.setdefault("pair_history", []).append({
            "at": datetime.now(timezone.utc).isoformat(), "from": original_pair,
            "to": pair["pairAddress"], "reason": "par original sin liquidez/precio verificable"})
        pos["pair"] = pair["pairAddress"]
        pos["url"] = pair.get("url", "")
        print(f"CAMBIO PAR {pos['chain']}:{pos['address']} | {original_pair} -> {pos['pair']}")
    return price, liquidity, pair


def simular_cartera(ranking, paper_file=V9_FILE, label="V9 FOMO RADAR", confirm=True):
    now = datetime.now(timezone.utc)
    try:
        with open(paper_file) as handle:
            state = json.load(handle)
    except FileNotFoundError:
        state = {"version": 1, "started_at": now.isoformat(),
                 "cash": 100.0, "reserve": 0.0, "positions": [],
                 "closed": [], "seen": [], "observations": []}
    if state.get("version") != 1:
        raise ValueError("Version de cartera virtual no compatible")
    notes = []
    closed_this_run = set()
    cost = (1 + PAPER_SLIPPAGE) * (1 + PAPER_FEE)
    proceeds_factor = (1 - PAPER_SLIPPAGE) * (1 - PAPER_FEE)
    for pos in list(state["positions"]):
        # Mantener seguimiento incluso si desaparece de los filtros.
        try:
            price, liquidity, _ = cotizar_posicion(pos)
            pos["mark_net"] = pos["quantity"] * price * proceeds_factor
            pos["last_quote_at"] = now.isoformat()
            pos["quote_status"] = "OK"
        except Exception as exc:
            pos["quote_status"] = "NO VERIFICABLE"
            notes.append(pos["symbol"] + ": " + str(exc))
            continue
        pnl_pct = (pos["mark_net"] / pos["budget"] - 1) * 100
        age = (now - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 3600
        pos["peak_price"] = max(pos.get("peak_price", price), price)
        drawdown = (price / pos["peak_price"] - 1) * 100
        reason = ("STOP -15%" if pnl_pct <= -15 else
                  "TRAILING -15%" if pos.get("partial_taken") and drawdown <= -15 else
                  "TIEMPO 24h" if age >= 24 else None)
        partial = not reason and not pos.get("partial_taken") and pnl_pct >= 30
        if partial:
            reason = "PARCIAL +30%"
        fraction = 0.5 if partial else 1.0
        if reason:
            proceeds = pos["mark_net"] * fraction
            allocated_cost = pos["budget"] * fraction
            profit = proceeds - allocated_cost
            reserved = max(profit, 0) * 0.5
            state["reserve"] += reserved
            state["cash"] += proceeds - reserved
            state["closed"].append(dict(pos, closed_at=now.isoformat(),
                                        exit_price=price, proceeds=proceeds,
                                        profit=profit, reserved=reserved,
                                        exit_reason=reason, sold_fraction=fraction,
                                        allocated_cost=allocated_cost,
                                        sold_quantity=pos["quantity"] * fraction))
            if partial:
                pos["quantity"] *= 0.5
                pos["budget"] *= 0.5
                pos["mark_net"] *= 0.5
                pos["partial_taken"] = True
                pos["peak_price"] = price
            else:
                state["positions"].remove(pos)
                closed_this_run.add(pos["chain"] + ":" + pos["address"])
            notes.append("SALIDA VIRTUAL " + pos["symbol"] + " | " + reason
                         + " | resultado EUR " + format(profit, ".2f"))
    quotes_blocked = any(p["quote_status"] != "OK" for p in state["positions"])
    if quotes_blocked:
        notes.append("ENTRADAS PAUSADAS: hay posiciones sin cotizacion verificable")
    # Una sola entrada por token durante este experimento, sin reentradas.
    for token in ranking:
        key = token["chain"] + ":" + token["address"]
        reason = ("caso de estudio: no comprar automaticamente" if (token["chain"], token["address"]) in STUDY_TOKENS else
                  "cartera sin valoracion completa" if quotes_blocked else
                  "token ya operado" if key in state["seen"] or key in closed_this_run else
                  "maximo 3 posiciones" if len(state["positions"]) >= 3 else
                  "efectivo < 10 EUR" if state["cash"] < 10 else None)
        if reason:
            notes.append(f"DESCARTE {key} | {reason}")
            continue
        try:
            price, entry_liquidity, fresh_pair = cotizar_posicion(token)
            fresh = analizar_par(fresh_pair)
            if fresh is None:
                notes.append(f"DESCARTE {key} | par fresco no supera filtros")
                continue
            reason = motivo_entrada(fresh, confirm)
            if reason:
                notes.append(f"DESCARTE {key} | {reason}")
                continue
        except Exception as exc:
            notes.append("ENTRADA OMITIDA " + key + ": " + str(exc))
            continue
        budget = min(10.0, MAX_EXPOSURE_EUR)
        quantity = budget / (price * cost)
        state["cash"] -= budget
        state["seen"].append(key)
        state["positions"].append({
            "symbol": token["symbol"], "address": token["address"],
            "chain": token["chain"], "pair": token["pair"],
            "opened_at": now.isoformat(), "entry_price": price,
            "budget": budget, "quantity": quantity,
            "mark_net": quantity * price * proceeds_factor,
            "last_quote_at": now.isoformat(), "quote_status": "OK",
            "entry_score": fresh["score"], "url": token["url"],
            "partial_taken": False, "peak_price": price})
        notes.append("ENTRADA VIRTUAL " + token["symbol"] + " | EUR "
                     + format(budget, ".2f"))
    equity = (state["cash"] + state["reserve"]
              + sum(p["mark_net"] for p in state["positions"]))
    stale = sum(p["quote_status"] != "OK" for p in state["positions"])
    realized = sum(x["profit"] for x in state["closed"])
    known_value = state["cash"] + state["reserve"] + sum(
        p["mark_net"] for p in state["positions"] if p["quote_status"] == "OK")
    state["observations"].append({
        "at": now.isoformat(), "cash": state["cash"],
        "reserve": state["reserve"], "estimated_equity": equity,
        "open": len(state["positions"]), "closed": len(state["closed"]),
        "unverified_quotes": stale, "valuation_complete": stale == 0,
        "verified_component": known_value, "realized_pnl": realized})
    state["observations"] = state["observations"][-3000:]
    state["assumptions"] = {
        "initial_eur": 100, "max_trade_eur": 10, "max_positions": 3,
        "fee_per_side": PAPER_FEE, "slippage_per_side": PAPER_SLIPPAGE,
        "stop_net_pct": -15, "partial_target_net_pct": 30,
        "partial_fraction": 0.5, "trailing_peak_pct": -15, "max_hours": 24,
        "fills": "Estimados en cada lectura, no garantizados. Sin gas ni MEV.",
        "currency": "Precios USD tratados con EUR/USD=1 constante para la prueba."}
    state["assumptions"]["strategy"] = "confirmacion V9" if confirm else "reglas base"
    state["assumptions"]["entry_policy"] = "V9 aprendizaje: 20 trades, compras >=55%, edad 10-1440m, precio creciente, liquidez >=95% y volumen5m >=60% de lectura previa" if confirm else "reglas base"
    state["last_rejections"] = REJECTIONS[-300:]
    state["last_run_notes"] = notes
    with open(paper_file + ".tmp", "w") as handle:
        json.dump(state, handle, indent=2)
    os.replace(paper_file + ".tmp", paper_file)
    print(f"\nCARTERA VIRTUAL {label} — NO EJECUTA ORDENES REALES")
    for note in notes:
        print(note)
    print(f"Liquido EUR {state['cash']:.2f} | reserva EUR {state['reserve']:.2f}")
    print(f"Abiertas={len(state['positions'])} | ventas registradas={len(state['closed'])}")
    if stale:
        print(f"VALORACION INCOMPLETA: ultimo valor contable EUR {equity:.2f}; no es beneficio actual")
        print(f"Parte valorada EUR {known_value:.2f}; resto desconocido")
    else:
        print(f"Patrimonio estimado EUR {equity:.2f} | resultado EUR {equity - 100:+.2f}")
    print(f"Resultado realizado virtual EUR {realized:+.2f}")
    for pos in state["positions"]:
        print(f"POSICION {pos['symbol']} | chain={pos['chain']} | token={pos['address']} | "
              f"estado={pos['quote_status']} | ultima_cotizacion={pos['last_quote_at']}")
    print(f"Cotizaciones no verificables={stale}; conservan ultimo valor, NO son liquidez")
    print("Costes supuestos POR LADO: comision 1%, deslizamiento 2%; FX fijo 1:1")
    print("Stops evaluados cada 15 min: pueden ejecutarse virtualmente con perdidas mayores")


def identidad_par(pair, chain, address):
    return (pair.get("chainId") == chain
            and (pair.get("baseToken") or {}).get("address") == address
            and bool(pair.get("pairAddress")))


def pares_token(chain, address):
    url = ("https://api.dexscreener.com/token-pairs/v1/"
           + urllib.parse.quote(chain, safe="") + "/"
           + urllib.parse.quote(address, safe=""))
    data = pedir_json(url)
    if not isinstance(data, list):
        raise ValueError("Respuesta token-pairs no valida")
    return [p for p in data if identidad_par(p, chain, address)]


def motivo_entrada(token, confirm=False):
    checks = [(numero(token["price"]) <= 0, "precio ausente"),
              (token["score"] < 5, "score < 5"),
              (token["liquidity"] < 10_000, "liquidez < 10000 USD"),
              (token["buyRatio5m"] < (0.55 if confirm else 0.60), "ratio compras insuficiente"),
              (token["trades5m"] < 20, "actividad 5m insuficiente"),
              (token["change1h"] > 150, "subida 1h > 150%")]
    for failed, reason in checks:
        if failed:
            return reason
    if not confirm:
        return None
    age = token.get("ageMinutes")
    if age is None or not 10 <= age <= 1440:
        return "comparacion: edad fuera de 10-1440 min"
    if not 0 < token["change5m"] <= 25:
        return "comparacion: momentum 5m fuera de 0-25%"
    now = datetime.now(timezone.utc)
    prev = [x for x in cargar_memoria()
            if x.get("chain") == token["chain"] and x.get("address") == token["address"]
            and x.get("pair") == token["pair"]]
    if not prev:
        return "comparacion: falta lectura previa del mismo par"
    old = prev[-1]
    try:
        minutes = (now - datetime.fromisoformat(old["hora"])).total_seconds() / 60
    except (ValueError, KeyError):
        return "comparacion: lectura previa invalida"
    if not 5 <= minutes <= 30:
        return "comparacion: lectura previa fuera de 5-30 min"
    if (numero(token["price"]) <= numero(old.get("price"))
            or token["liquidity"] < 0.95 * numero(old.get("liquidity"))
            or token["vol5m"] < 0.60 * numero(old.get("vol5m"))):
        return "comparacion: precio/liquidez/volumen no confirman"
    return None


def descubrir_pares():
    pairs = {}
    sources = {}

    def add(pair, source):
        key = (pair.get("chainId"), pair.get("pairAddress"))
        if not all(key):
            return
        pairs[key] = pair
        sources.setdefault(key, set()).add(source)

    for term in SEARCHES:
        try:
            data = pedir_json("https://api.dexscreener.com/latest/dex/search/?q="
                              + urllib.parse.quote(term))
            for pair in data.get("pairs") or []:
                add(pair, "busqueda:" + term)
        except Exception as exc:
            print(f"FUENTE ERROR busqueda:{term} | {exc}")

    # Perfiles no equivalen a todos los lanzamientos ni a una recomendacion.
    requested = dict.fromkeys(STUDY_TOKENS)
    for endpoint in ("token-profiles/latest/v1", "token-profiles/recent-updates/v1"):
        try:
            profiles = pedir_json("https://api.dexscreener.com/" + endpoint)
            if not isinstance(profiles, list):
                raise ValueError("Respuesta perfiles no valida")
            for p in profiles[:20]:
                if p.get("chainId") and p.get("tokenAddress"):
                    requested.setdefault((p["chainId"], p["tokenAddress"]), None)
        except Exception as exc:
            print(f"FUENTE ERROR {endpoint} | {exc}")
    for old in reversed(cargar_memoria()):
        if len(requested) >= 60:
            break
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(old["hora"])).total_seconds()
            if age <= 86400 and old.get("chain") and old.get("address"):
                requested.setdefault((old["chain"], old["address"]), None)
        except (ValueError, KeyError):
            pass
    for chain, address in requested:
        try:
            found = pares_token(chain, address)
            for pair in found:
                add(pair, "seguimiento" if (chain, address) in STUDY_TOKENS else "perfil/historial")
            if (chain, address) in STUDY_TOKENS:
                print(f"ESTUDIO {chain}:{address} | pares={len(found)} | fuera de cartera por defecto")
                if found:
                    p = max(found, key=lambda p: numero((p.get("liquidity") or {}).get("usd")))
                    print(f"ESTUDIO DATOS {chain}:{address} | par={p['pairAddress']} | "
                          f"precio={p.get('priceUsd', 'NO DISPONIBLE')} | "
                          f"liquidez={numero((p.get('liquidity') or {}).get('usd')):.2f} | "
                          f"compras5m={(p.get('txns') or {}).get('m5', {}).get('buys', 'NO DISPONIBLE')} | "
                          f"ventas5m={(p.get('txns') or {}).get('m5', {}).get('sells', 'NO DISPONIBLE')}")
        except Exception as exc:
            print(f"FUENTE ERROR token:{chain}:{address} | {exc}")
    print(f"COBERTURA V8 pares recibidos={len(pairs)} | contratos consultados={len(requested)}")
    return pairs, sources


def main():
    ahora = datetime.now(timezone.utc)

    print("🧠 FOMO Brain v9 - DEX + FOMO TRADER RADAR + PAPER")
    fomo_events = consultar_fomo_trader_radar()
    print(f"FOMO Trader Radar: {FOMO_RADAR_STATUS} | eventos verificados={len(fomo_events)}")
    eventos = cargar_eventos()
    nuevos_eventos = consultar_x()
    conocidos = {str(e.get("id")) for e in eventos if e.get("id")}
    added = 0
    for evento in nuevos_eventos:
        event_id = str(evento.get("id") or "")
        if event_id and event_id not in conocidos:
            eventos.append(evento)
            conocidos.add(event_id)
            added += 1
    if nuevos_eventos:
        guardar_eventos(eventos)
    print(resumen_event_radar(eventos))
    print(f"X API: publicaciones devueltas={len(nuevos_eventos)} | nuevos_eventos={added}")
    print(f"Hora UTC: {ahora.isoformat()}")
    print(
        "Buscando memecoins pequeñas "
        "con actividad temprana..."
    )

    candidatos = {}

    pairs, sources = descubrir_pares()
    for pool_key, pair in pairs.items():
        resultado = analizar_par(pair)
        if resultado is None:
            continue
        resultado["discoverySources"] = sorted(sources[pool_key])
        # Solo coincidencia explicita de contrato; texto generico no confirma vinculo.
        linked = [e for e in eventos if resultado["address"] in str(e.get("text", ""))]
        resultado["eventMatches"] = len(linked)
        resultado["eventSources"] = sorted({e["source"] for e in linked})
        key = (resultado["chain"], resultado["address"])
        old = candidatos.get(key)
        # El par con mas liquidez, no el score mas alto de un pool diminuto.
        if old is None or resultado["liquidity"] > old["liquidity"]:
            candidatos[key] = resultado

    for token in candidatos.values():
        if token["score"] < 2:
            REJECTIONS.append({"chain": token["chain"], "address": token["address"],
                               "pair": token["pair"], "reason": "score < 2"})
    candidatos = {
        k: v
        for k, v in candidatos.items()
        if v["score"] >= 2
    }

    candidatos = aplicar_confluencia_fomo(candidatos, fomo_events)

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

    print("V9: prueba PAPER independiente; confluencia FOMO suma solo si el feed autorizado aporta evidencia")
    simular_cartera(ranking, V9_FILE, "V9 FOMO RADAR", confirm=True)
    counts = {}
    for item in REJECTIONS:
        counts[item["reason"]] = counts.get(item["reason"], 0) + 1
    print("DESCARTES DESCUBRIMIENTO " + json.dumps(counts, ensure_ascii=False))
    for item in REJECTIONS[:60]:
        print(f"DESCARTE PAR {item['chain']}:{item['address']} | {item['pair']} | {item['reason']}")

    print("TOP 10 FOMO BRAIN v9")

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
            f"| graduacion={token['graduationStatus']}"
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
            f"fomo_confluencia={token.get('fomoConfluence', 0)} "
            f"| bonus={token.get('fomoBonus', 0)} "
            f"| traders={','.join(token.get('fomoTraders', [])[:5]) or '-'}"
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
    print("✅ FOMO Brain v9 terminado")

    print(
        "Modo análisis únicamente | "
        f"exposición futura máxima: "
        f"€{MAX_EXPOSURE_EUR:.2f}"
    )


if __name__ == "__main__":
    main()
