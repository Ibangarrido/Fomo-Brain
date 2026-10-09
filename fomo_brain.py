from datetime import datetime, timezone, timedelta
import json
import urllib.parse
import urllib.request
import os
import math
import time
from exit_watchdog import ThreadCache, wallet_transaction, wallet_lock, ExitWatchdog, MarketRateLimiter

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
    "realDonaldTrump", "elonmusk"
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
V10_FILE = "fomo_paper_v10.json"
V10_IMPULSE_FILE = "fomo_paper_v10_impulse.json"
V10_R3_FILE = "fomo_paper_v10_r3.json"
SESSION_MAX_CYCLES = 15
SESSION_WINDOW_SECONDS = 900
MAX_CONFIRMATION_MINUTES = 1.5
JSON_CACHE = ThreadCache()
EXIT_WATCHDOG = None
MARKET_RATE_LIMITER = MarketRateLimiter(0.25, {"api.geckoterminal.com": 2.1})
# DEX <=240/min; public GeckoTerminal <30/min, shared by discovery and watcher.
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
    if EXIT_WATCHDOG is not None or urllib.parse.urlsplit(url).netloc == "api.geckoterminal.com":
        MARKET_RATE_LIMITER.wait(url)
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

    # Las entradas recorren todo el ranking: todos necesitan una lectura previa.
    # TOP 10 es solo la salida resumida de pantalla, no el universo confirmable.
    for token in ranking:
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
    print(f"MEMORIA: {len(ranking)} candidatos guardados; historial={len(memoria)}/10000")


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
    """Read both public accounts; keywords classify posts after retrieval."""
    global X_STATUS
    if not EVENT_RADAR_ENABLED or not SOCIAL_FEED_CONNECTED:
        X_STATUS = "SIN CREDENCIALES" if not SOCIAL_FEED_CONNECTED else "OFF"
        return []
    from social_radar import collect_posts

    def fetch(params):
        url = "https://api.x.com/2/tweets/search/recent?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + X_BEARER_TOKEN,
            "User-Agent": "FOMO-Brain/social-r2"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    events, status, coverage = collect_posts(fetch, EVENT_ACCOUNTS, EVENT_KEYWORDS)
    X_STATUS = status
    print("X COBERTURA social-r2 | " + json.dumps(coverage, ensure_ascii=False))
    return events


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
V10_MAX_TOTAL_LOSS_PCT = 25.0
V10_LOSS_PAUSE_MINUTES = 60
V10_LOSS_PAUSE_COUNT = 2
V10_ENTRY_BUDGET_EUR = 5.0
V10_RISK_VERSION = "capital-r2"


def freno_cartera_v10(state, now, conservative_unknown=False):
    """Block NEW entries only. Never fabricate an exit or reset historical losses."""
    control = state.setdefault("risk_control", {"version": V10_RISK_VERSION})
    control["version"] = V10_RISK_VERSION
    if control.get("halted_at"):
        return control["halt_reason"]
    if conservative_unknown or all(p.get("quote_status") == "OK" for p in state["positions"]):
        equity = (state["cash"] + state["reserve"]
                  + sum(p["mark_net"] for p in state["positions"]
                        if not conservative_unknown or p.get("quote_status") == "OK"))
        floor = 100.0 * (1 - V10_MAX_TOTAL_LOSS_PCT / 100)
        if equity <= floor:
            reason = (f"riesgo capital-r1: patrimonio EUR {equity:.2f} <= {floor:.2f};"
                      " perdida total >=25%; nuevas entradas bloqueadas hasta revision")
            control.update(halted_at=now.isoformat(), halt_reason=reason,
                           equity_at_halt=equity, capital_reference=100.0)
            return reason
    # Aggregate partial + final legs of each POSITION, not each sale separately.
    grouped = {}
    for leg in state.get("closed", []):
        if not all(k in leg for k in ("chain", "address", "opened_at", "closed_at", "profit", "exit_reason")):
            continue
        key = (leg["chain"], leg["address"], leg["opened_at"])
        row = grouped.setdefault(key, {"profit": 0.0, "completed_at": None})
        row["profit"] += leg["profit"]
        if leg["exit_reason"] != "PARCIAL +30%":
            row["completed_at"] = datetime.fromisoformat(leg["closed_at"])
    completed = sorted((r for r in grouped.values() if r["completed_at"]),
                       key=lambda r: r["completed_at"])
    recent = completed[-V10_LOSS_PAUSE_COUNT:]
    if (len(recent) == V10_LOSS_PAUSE_COUNT and all(r["profit"] < 0 for r in recent)
            and now - timedelta(minutes=V10_LOSS_PAUSE_MINUTES) <= recent[0]["completed_at"] <= now
            and recent[-1]["completed_at"] <= now):
        until = recent[-1]["completed_at"] + timedelta(minutes=V10_LOSS_PAUSE_MINUTES)
        control["pause_until"] = until.isoformat()
    if control.get("pause_until"):
        until = datetime.fromisoformat(control["pause_until"])
        if now < until:
            return ("riesgo capital-r2: dos posiciones completas perdedoras consecutivas; "
                    f"entradas pausadas hasta {until.isoformat()}")
    return None


class CotizacionBajaLiquidez(ValueError):
    """Precio identificable que NO autoriza una ejecucion virtual."""
    def __init__(self, price, liquidity):
        super().__init__(f"Liquidez insuficiente ({liquidity:.2f} USD); salida no verificable")
        self.price = price
        self.liquidity = liquidity


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
        try:
            candidates = pares_token(pos["chain"], pos["address"])
        except Exception:
            # Conservar un precio indicativo del par exacto aunque falle el respaldo.
            if pair is None or numero(pair.get("priceUsd")) <= 0:
                raise
            candidates = []
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
        raise CotizacionBajaLiquidez(price, liquidity)
    if pair["pairAddress"] != original_pair:
        pos.setdefault("pair_history", []).append({
            "at": datetime.now(timezone.utc).isoformat(), "from": original_pair,
            "to": pair["pairAddress"], "reason": "par original sin liquidez/precio verificable"})
        pos["pair"] = pair["pairAddress"]
        pos["url"] = pair.get("url", "")
        print(f"CAMBIO PAR {pos['chain']}:{pos['address']} | {original_pair} -> {pos['pair']}")
    pos["quote_source"] = "DEX Screener"
    pos["quote_pair"] = pair["pairAddress"]
    pos["quote_observed_at"] = datetime.now(timezone.utc).isoformat()
    if os.getenv("BRAIN_QUOTE_GUARD", "0") == "1" and pos.get("quantity"):
        from quote_safety import extreme, corroborate, record_market_observation
        observation = record_market_observation(pos, price, pair)
        observation["accepted"] = False
        previous = pos.get("last_verified_price")
        if previous is None:
            previous = pos.get("mark_net", 0) / pos["quantity"] / ((1 - PAPER_SLIPPAGE) * (1 - PAPER_FEE))
        if extreme(price, previous):
            try:
                evidence = corroborate(pos, price, pedir_json)
            except Exception as exc:
                evidence = {"version": "quote-r2", "status": "SIN DATOS", "reason": str(exc), "primary_price": price}
            pos["quote_crosscheck"] = evidence
            observation["crosscheck"] = evidence
            if evidence["status"] != "COINCIDE":
                pos["indicative_price"] = price
                pos["indicative_liquidity"] = liquidity
                pos["indicative_mark_net"] = pos["quantity"] * price * (1 - PAPER_SLIPPAGE) * (1 - PAPER_FEE)
                pos["last_indicative_quote_at"] = datetime.now(timezone.utc).isoformat()
                raise ValueError("COTIZACION EXTREMA EN REVISION: " + json.dumps(evidence, ensure_ascii=False))
        pos["last_verified_price"] = price
        observation["accepted"] = True
    return price, liquidity, pair


def invalidate_entry_quote(token):
    """Discard only this token's cached market responses before final entry checks."""
    chain = urllib.parse.quote(token["chain"], safe="")
    address = urllib.parse.quote(token["address"], safe="")
    pool = urllib.parse.quote(token["pair"], safe="")
    for url in (f"https://api.dexscreener.com/latest/dex/pairs/{chain}/{pool}",
                f"https://api.dexscreener.com/token-pairs/v1/{chain}/{address}"):
        JSON_CACHE.pop(url, None)


def record_unverified_quote(pos, error, now):
    """Keep historical marks separate from current, executable valuations."""
    pos["quote_status"] = "NO VERIFICABLE"
    pos["quote_error"] = str(error)
    pos["last_quote_attempt_at"] = now.isoformat()
    try:
        pos["quote_age_seconds"] = max(0, (now - datetime.fromisoformat(pos["last_quote_at"])).total_seconds())
    except (KeyError, TypeError, ValueError):
        pos["quote_age_seconds"] = None


@wallet_transaction
def simular_cartera(ranking, paper_file=V10_FILE, label="V10 EARLY", confirm=True, entry_mode="early", entry_guard=None, min_buy_ratio=0.60, profit_protection=False, quarantine_m4=False):
    from m4_lab import RECOVERY, is_quarantined
    if type(quarantine_m4) is not bool or (quarantine_m4 and os.path.basename(paper_file) != RECOVERY):
        raise ValueError("Cuarentena M4 reservada al laboratorio aislado")
    if not math.isfinite(min_buy_ratio) or not 0 <= min_buy_ratio <= 1:
        raise ValueError("Umbral de compras invalido")
    ratio_lab = os.path.basename(paper_file).startswith("fomo_lab_ratio_")
    if min_buy_ratio != 0.60 and not ratio_lab:
        raise ValueError("Umbral alternativo reservado al laboratorio ratio")
    protect_lab = os.path.basename(paper_file).startswith("fomo_lab_protect_")
    if type(profit_protection) is not bool or (profit_protection and not protect_lab):
        raise ValueError("Proteccion reservada al laboratorio aislado")
    now = datetime.now(timezone.utc)
    try:
        with open(paper_file) as handle:
            state = json.load(handle)
    except FileNotFoundError:
        state = {"version": 1, "started_at": now.isoformat(),
                 "cash": 100.0, "reserve": 0.0, "positions": [],
                 "closed": [], "seen": [], "observations": []}
    if os.getenv("BRAIN_QUOTE_GUARD", "0") == "1":
        for sale in state.get("closed", []):
            if (sale.get("chain") == "solana" and
                sale.get("address") == "FeAWY9L9hr82TvTuEyi328V9FP7GxVuGLx7xNg6kzWVa" and
                sale.get("exit_price") == 2.887e-7):
                sale.setdefault("quote_review", {
                    "status": "EN REVISION", "version": "quote-r1",
                    "reason": "precio de cierre discrepa de OHLCV independiente; no corregir contabilidad",
                    "source": "GeckoTerminal", "minute_start_utc": "2026-10-06T18:55:00+00:00",
                    "historical_low_usd": .0005799666150227353,
                    "historical_close_usd": .0005800645649876336})
    if state.get("version") != 1:
        raise ValueError("Version de cartera virtual no compatible")
    if quarantine_m4 and state.get("m4_experiment", {}).get("arm") != "recovery":
        raise ValueError("Falta bifurcacion M4 recovery; no reiniciar")
    # Preserve the change point; cumulative portfolios mix old and new policies.
    data_policy = {"version": "quote-r2", "early_entry_version": "early-r5",
                   "early_max_change1h_pct": 150, "crosscheck_drop_pct": 30,
                   "crosscheck_rise_pct": 50, "source_price_timestamp": "UNKNOWN"}
    policy_history = state.setdefault("data_policy_history", [])
    if not policy_history or policy_history[-1]["version"] != data_policy["version"]:
        policy_history.append(dict(data_policy, effective_at=now.isoformat(),
                                   cash=state["cash"], reserve=state["reserve"],
                                   open=len(state["positions"]), closed=len(state["closed"])))
    if ratio_lab:
        expected = {"mode": entry_mode, "min_buy_ratio": min_buy_ratio, "version": "ratio-r1"}
        if state.get("ratio_experiment", expected) != expected:
            raise ValueError("Cartera ratio incompatible; no mezclar umbrales")
        state["ratio_experiment"] = expected
    # Record the transition without erasing cash, reserves, positions or losses.
    epochs = state.setdefault("risk_policy_history", [])
    if not epochs or epochs[-1]["version"] != V10_RISK_VERSION:
        epochs.append({"version": V10_RISK_VERSION, "effective_at": now.isoformat(),
                       "cash": state["cash"], "reserve": state["reserve"],
                       "realized_pnl": sum(x["profit"] for x in state["closed"]),
                       "open": len(state["positions"]),
                       "entry_budget_eur": V10_ENTRY_BUDGET_EUR,
                       "loss_pause_count": V10_LOSS_PAUSE_COUNT})
    if protect_lab:
        expected_protection = {"version": "protect-r1", "mode": entry_mode,
                               "enabled": profit_protection}
        if state.get("protection_experiment") != expected_protection:
            raise ValueError("Cartera de proteccion incompatible; no mezclar brazos")
    notes = ["RIESGO capital-r2: nuevas entradas <=5 EUR; pausa tras dos posiciones"
             " perdedoras consecutivas en 60m; stops estimados entre lecturas"]
    entry_budget = min(V10_ENTRY_BUDGET_EUR, MAX_EXPOSURE_EUR)
    if not math.isfinite(entry_budget) or entry_budget <= 0:
        raise ValueError("Presupuesto virtual invalido")
    closed_this_run = set()
    cost = (1 + PAPER_SLIPPAGE) * (1 + PAPER_FEE)
    proceeds_factor = (1 - PAPER_SLIPPAGE) * (1 - PAPER_FEE)
    for pos in list(state["positions"]):
        # Mantener seguimiento incluso si desaparece de los filtros.
        for field in ("indicative_price", "indicative_liquidity", "indicative_mark_net",
                      "indicative_pnl_pct", "last_indicative_quote_at"):
            pos.pop(field, None)
        previous_quote_at = pos.get("last_quote_at")
        quote_requested_at = datetime.now(timezone.utc)
        try:
            price, liquidity, _ = cotizar_posicion(pos)
            now = datetime.now(timezone.utc)  # Timestamp reception, not start of the wallet scan.
            pos["quote_request_seconds"] = max(0, (now - quote_requested_at).total_seconds())
            pos["mark_net"] = pos["quantity"] * price * proceeds_factor
            pos["last_quote_at"] = now.isoformat()
            pos["quote_status"] = "OK"
            pos.pop("quote_error", None)
            pos["last_quote_attempt_at"] = now.isoformat()
            pos["quote_age_seconds"] = 0.0
            try:
                pos["quote_gap_seconds"] = max(0, (now - datetime.fromisoformat(previous_quote_at)).total_seconds())
            except (TypeError, ValueError):
                pos["quote_gap_seconds"] = None
        except CotizacionBajaLiquidez as exc:
            # Informar del precio actual sin convertir una salida no verificable en efectivo.
            now = datetime.now(timezone.utc)
            record_unverified_quote(pos, exc, now)
            pos["indicative_price"] = exc.price
            pos["indicative_liquidity"] = exc.liquidity
            pos["indicative_mark_net"] = pos["quantity"] * exc.price * proceeds_factor
            pos["indicative_pnl_pct"] = (pos["indicative_mark_net"] / pos["budget"] - 1) * 100
            pos["last_indicative_quote_at"] = now.isoformat()
            notes.append(f"{pos['symbol']}: {exc}; precio indicativo={exc.price}"
                         f" | valor indicativo EUR {pos['indicative_mark_net']:.2f}"
                         f" | resultado indicativo {pos['indicative_pnl_pct']:+.2f}%"
                         " | NO ES EFECTIVO NI VENTA EJECUTABLE")
            continue
        except Exception as exc:
            now = datetime.now(timezone.utc)
            record_unverified_quote(pos, exc, now)
            notes.append(pos["symbol"] + ": " + str(exc))
            continue
        pnl_pct = (pos["mark_net"] / pos["budget"] - 1) * 100
        pos["last_pnl_net_pct"] = pnl_pct
        pos["peak_pnl_net_pct"] = max(pos.get("peak_pnl_net_pct", pnl_pct), pnl_pct)
        age = (now - datetime.fromisoformat(pos["opened_at"])).total_seconds() / 3600
        pos["peak_price"] = max(pos.get("peak_price", price), price)
        drawdown = (price / pos["peak_price"] - 1) * 100
        # Only a verified observation after activation can arm protection.
        if profit_protection and pnl_pct >= 12 and not pos.get("profit_protection_armed"):
            pos["profit_protection_armed"] = True
            pos["profit_protection_armed_at"] = now.isoformat()
            notes.append(f"PROTECCION ARMADA {pos['symbol']} | neto={pnl_pct:+.2f}%")
        reason = ("STOP -15%" if pnl_pct <= -15 else
                  "PROTECCION +12% -> +2%" if profit_protection and pos.get("profit_protection_armed") and pnl_pct <= 2 else
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
                                        sold_quantity=pos["quantity"] * fraction,
                                        exit_risk_policy_version=V10_RISK_VERSION,
                                        stop_overshoot_pct=max(0, -15 - pnl_pct) if reason == "STOP -15%" else None))
            if partial:
                pos["quantity"] *= 0.5
                pos["budget"] *= 0.5
                pos["mark_net"] *= 0.5
                pos["partial_taken"] = True
                pos["peak_price"] = price
            else:
                state["positions"].remove(pos)
                closed_this_run.add(pos["chain"] + ":" + pos["address"])
            note = ("SALIDA VIRTUAL " + pos["symbol"] + " | " + reason
                    + " | resultado EUR " + format(profit, ".2f"))
            if reason == "STOP -15%":
                note += (f" | neto={pnl_pct:+.2f}% | pico_neto_observado={pos['peak_pnl_net_pct']:+.2f}%"
                         f" | hueco_cotizacion_s={pos.get('quote_gap_seconds')}"
                         f" | exceso_stop_pp={max(0, -15-pnl_pct):.2f}")
            notes.append(note)
    quotes_blocked = any(p["quote_status"] != "OK" and not
                        (quarantine_m4 and is_quarantined(p)) for p in state["positions"])
    if quarantine_m4:
        notes.append("LAB M4: posicion heredada aislada; valor desconocido excluido del control de riesgo; no es venta")
    if quotes_blocked:
        notes.append("ENTRADAS PAUSADAS: hay posiciones sin cotizacion verificable")
    risk_reason = freno_cartera_v10(state, now, conservative_unknown=quarantine_m4)
    if risk_reason:
        notes.append("FRENO V10: " + risk_reason)
    # Una sola entrada por token durante este experimento, sin reentradas.
    for token in ranking:
        key = token["chain"] + ":" + token["address"]
        risk_reason = freno_cartera_v10(state, now, conservative_unknown=quarantine_m4)
        reason = (risk_reason if risk_reason else
                  "caso de estudio: no comprar automaticamente" if (token["chain"], token["address"]) in STUDY_TOKENS else
                  "cartera sin valoracion completa" if quotes_blocked else
                  "token ya operado" if key in state["seen"] or key in closed_this_run else
                  "maximo 3 posiciones" if len(state["positions"]) >= 3 else
                  f"efectivo < {entry_budget:.2f} EUR" if state["cash"] < entry_budget else None)
        if reason:
            notes.append(f"DESCARTE {key} | {reason}")
            continue
        try:
            price, entry_liquidity, fresh_pair = cotizar_posicion(token)
            fresh = analizar_par(fresh_pair)
            if fresh is None:
                notes.append(f"DESCARTE {key} | par fresco no supera filtros")
                continue
            # No perseguir una cotizacion que ya se alejo de la señal del radar.
            drift = variacion(price, token.get("price"))
            if confirm and (drift is None or abs(drift) > 5):
                notes.append(f"DESCARTE {key} | cotizacion se aleja >5% de la señal")
                continue
            reason = motivo_entrada(fresh, confirm, entry_mode, min_buy_ratio=min_buy_ratio)
            if not reason and entry_guard is not None:
                reason = entry_guard(fresh)
            if reason:
                notes.append(f"DESCARTE {key} | {reason}")
                continue
        except Exception as exc:
            notes.append("ENTRADA OMITIDA " + key + ": " + str(exc))
            continue
        fee_evidence = None
        final_quote_evidence = None
        entry_at = now
        if os.getenv("BRAIN_QUOTE_GUARD", "0") == "1":
            from quote_safety import entry_fees
            fee_evidence, fee_reason = entry_fees(fresh, pedir_json)
            if fee_reason:
                notes.append(f"DESCARTE {key} | quote-r1: {fee_reason} | " + json.dumps(fee_evidence, ensure_ascii=False))
                continue
            # Security requests can take seconds. Do not fill at the pre-check price.
            try:
                invalidate_entry_quote(token)
                price, entry_liquidity, fresh_pair = cotizar_posicion(token)
                fresh = analizar_par(fresh_pair)
                if fresh is None:
                    raise ValueError("par final no supera filtros")
                drift = variacion(price, token.get("price"))
                if confirm and (drift is None or abs(drift) > 5):
                    raise ValueError("precio final se aleja >5% de la señal")
                reason = motivo_entrada(fresh, confirm, entry_mode, min_buy_ratio=min_buy_ratio)
                if not reason and entry_guard is not None:
                    reason = entry_guard(fresh)
                if reason:
                    raise ValueError(reason)
                entry_at = datetime.now(timezone.utc)
                reason = freno_cartera_v10(state, entry_at, conservative_unknown=quarantine_m4)
                if reason:
                    raise ValueError(reason)
                final_quote_evidence = {"version": "entry-quote-r1", "after_security_checks": True,
                                        "observed_at": entry_at.isoformat(), "price": price,
                                        "pair": fresh_pair["pairAddress"], "drift_pct": drift}
            except Exception as exc:
                notes.append(f"ENTRADA OMITIDA {key} | precio final tras seguridad: {exc}")
                continue
        budget = entry_budget
        quantity = budget / (price * cost)
        state["cash"] -= budget
        state["seen"].append(key)
        state["positions"].append({
            "symbol": token["symbol"], "address": token["address"],
            "chain": token["chain"], "pair": token["pair"],
            "opened_at": entry_at.isoformat(), "entry_price": price,
            "budget": budget, "quantity": quantity,
            "mark_net": quantity * price * proceeds_factor,
            "last_quote_at": entry_at.isoformat(), "quote_status": "OK",
            "entry_score": fresh["score"], "url": token["url"],
            "partial_taken": False, "peak_price": price,
            "entry_policy_version": ("early-r5" if entry_mode == "early" else "impulse-r4") if confirm else "base",
            "entry_fee_evidence": fee_evidence, "entry_final_quote": final_quote_evidence,
            "entry_snapshot": {k: fresh.get(k) for k in (
                "price", "liquidity", "vol5m", "trades5m", "buyRatio5m",
                "buys5m", "sells5m", "change5m", "change1h", "ageMinutes")},
            "signal_price": token.get("price"), "quote_drift_pct": drift,
            "entry_confirmation": ultima_lectura_par(fresh) if confirm else None,
            "entry_candle_context": fresh.get("candle_context"),
            "entry_experiment": label if entry_guard is not None or ratio_lab or protect_lab else None,
            "entry_protection_policy": "protect-r1" if profit_protection else None,
            "entry_risk_policy_version": V10_RISK_VERSION,
            "entry_min_buy_ratio": min_buy_ratio,
            "entry_policy_suffix": fresh.get("entry_policy_suffix")})
        notes.append("ENTRADA VIRTUAL " + token["symbol"] + " | EUR "
                     + format(budget, ".2f")
                     + f" | precio={price} | liquidez={fresh['liquidity']:.0f}"
                     + f" | trades5m={fresh['trades5m']} | compras={fresh['buyRatio5m']:.1%}"
                     + f" | volumen5m={fresh['vol5m']:.0f} | cambio5m={fresh['change5m']:.2f}%")
    equity = (state["cash"] + state["reserve"]
              + sum(p["mark_net"] for p in state["positions"]))
    stale = sum(p["quote_status"] != "OK" for p in state["positions"])
    realized = sum(x["profit"] for x in state["closed"])
    known_value = state["cash"] + state["reserve"] + sum(
        p["mark_net"] for p in state["positions"] if p["quote_status"] == "OK")
    indicative_only_equity = None
    if stale and all(p["quote_status"] == "OK" or "indicative_mark_net" in p
                     for p in state["positions"]):
        indicative_only_equity = state["cash"] + state["reserve"] + sum(
            p["mark_net"] if p["quote_status"] == "OK" else p["indicative_mark_net"]
            for p in state["positions"])
    state["observations"].append({
        "at": datetime.now(timezone.utc).isoformat(), "risk_policy_version": V10_RISK_VERSION, "cash": state["cash"],
        "reserve": state["reserve"], "estimated_equity": equity if stale == 0 else None,
        "accounting_equity": equity, "valuation_version": "valuation-r2",
        "open": len(state["positions"]), "closed": len(state["closed"]),
        "unverified_quotes": stale, "valuation_complete": stale == 0,
        "verified_component": known_value, "realized_pnl": realized,
        "indicative_only_equity": indicative_only_equity})
    state["observations"] = state["observations"][-3000:]
    state["assumptions"] = {
        "initial_eur": 100, "max_trade_eur": 10, "new_entry_budget_eur": entry_budget,
        "risk_policy_version": V10_RISK_VERSION, "max_positions": 3,
        "fee_per_side": PAPER_FEE, "slippage_per_side": PAPER_SLIPPAGE,
        "stop_net_pct": -15, "partial_target_net_pct": 30,
        "partial_fraction": 0.5, "trailing_peak_pct": -15, "max_hours": 24,
        "fills": "Estimados en cada lectura, no garantizados. Sin gas ni MEV.",
        "currency": "Precios USD tratados con EUR/USD=1 constante para la prueba."}
    state["assumptions"]["strategy"] = "confirmacion V10" if confirm else "reglas base"
    state["assumptions"]["exit_monitor"] = {
        "version": "watchdog-r1" if EXIT_WATCHDOG is not None else "cooperative-15s",
        "target_seconds": 3 if EXIT_WATCHDOG is not None else 15,
        "guaranteed": False, "quotes": "indicative market data; not a swap execution",
        "limits": "same-wallet transactions, rate limits, network latency and gaps between runs"}
    state["assumptions"]["entry_policy"] = "V10 early r5: edad del par 2-60m, momentum5m 2-60% en ambas lecturas, 40 trades, compras >=60%, liquidez >=20000 USD; confirmacion 0.5-1.5m, precio +1-12%, liquidez >=95%, volumen5m no decreciente; subida1h <=150% en ambas lecturas" if confirm else "reglas base"
    state["assumptions"]["quote_quality"] = dict(data_policy,
        guard_enabled=os.getenv("BRAIN_QUOTE_GUARD", "0") == "1",
        history_limit_per_position=360, unchanged_price_is_not_proof_of_staleness=True,
        crosscheck_is_not_execution=True)
    state["assumptions"]["candidate_memory_scope"] = "todos los candidatos filtrados; TOP 10 solo para pantalla"
    state["assumptions"]["max_quote_drift_pct"] = 5 if confirm else None
    state["assumptions"]["entry_mode"] = entry_mode
    state["assumptions"]["risk_policy"] = "capital-r2: nuevas entradas <=5 EUR; perdida total >=25% bloquea entradas hasta revision; 2 posiciones completas perdedoras en 60m pausan 60m desde ultimo cierre; salidas siguen activas"
    state["assumptions"]["experiment"] = label if entry_guard is not None or ratio_lab else None
    state["assumptions"]["min_buy_ratio_5m"] = min_buy_ratio
    state["assumptions"]["holders_status"] = "SIN FUENTE VERIFICADA; no se usan para confirmar"
    if entry_mode == "impulse":
        state["assumptions"]["entry_policy"] = "V10 impulso r4: sin filtro de edad; lectura previa 0.5-1.5m del mismo par; precio +1-20%, volumen5m +10% minimo, liquidez >=95%; momentum5m 2-25% en ambas lecturas, compras >=60%, 20 trades"
    state["assumptions"]["entry_policy"] = state["assumptions"]["entry_policy"].replace("compras >=60%", f"compras >={min_buy_ratio:.0%}")
    state["assumptions"]["profit_protection"] = {"enabled": profit_protection, "arm_net_pct": 12, "exit_net_pct": 2,
                                                "fills": "Precio observado, no garantiza +2%"}
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
        if indicative_only_equity is not None:
            print(f"VALOR INDICATIVO DE PRECIOS EUR {indicative_only_equity:.2f}; NO liquidable ni patrimonio verificable")
    else:
        print(f"Patrimonio estimado EUR {equity:.2f} | resultado EUR {equity - 100:+.2f}")
    print(f"Resultado realizado virtual EUR {realized:+.2f}")
    for pos in state["positions"]:
        print(f"POSICION {pos['symbol']} | chain={pos['chain']} | token={pos['address']} | "
              f"estado={pos['quote_status']} | ultima_cotizacion={pos['last_quote_at']}")
        if pos.get("quote_audit"):
            audit = pos["quote_audit"]
            print(f"CALIDAD PRECIO {pos['symbol']} | antiguedad_dato=DESCONOCIDA"
                  f" | precio_sin_cambio_s={audit['price_unchanged_seconds']:.1f}"
                  f" | snapshot_sin_cambio_s={audit['snapshot_unchanged_seconds']:.1f}"
                  " | recepcion NO demuestra frescura ni ejecucion")
    print(f"Cotizaciones no verificables={stale}; conservan ultimo valor, NO son liquidez")
    print("Costes supuestos POR LADO: comision 1%, deslizamiento 2%; FX fijo 1:1")
    print("Stops: " + str(state["assumptions"]["exit_monitor"]) + "; NO garantizados")


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


def ultima_lectura_par(token):
    prev = [x for x in cargar_memoria()
            if x.get("chain") == token["chain"] and x.get("address") == token["address"]
            and x.get("pair") == token["pair"]]
    return prev[-1] if prev else None


def motivo_entrada(token, confirm=False, entry_mode="early", min_buy_ratio=0.60):
    if not math.isfinite(min_buy_ratio) or not 0 <= min_buy_ratio <= 1:
        raise ValueError("Umbral de compras invalido")
    if entry_mode not in ("early", "impulse"):
        raise ValueError("Modo de entrada desconocido")
    checks = [(numero(token["price"]) <= 0, "precio ausente"),
              (token["score"] < 5, "score < 5"),
              (token["liquidity"] < 10_000, "liquidez < 10000 USD"),
              (token["buyRatio5m"] < min_buy_ratio, f"ratio compras < {min_buy_ratio:.0%}"),
              (token["trades5m"] < 20, "actividad 5m insuficiente"),
              (not confirm and token["change1h"] > 150, "subida 1h > 150%")]
    for failed, reason in checks:
        if failed:
            return reason
    if not confirm:
        return None
    if entry_mode == "early":
        if token["change1h"] > 150:
            return "early r5: subida 1h > 150%"
        if token["liquidity"] < 20_000:
            return "early r2: liquidez < 20000 USD"
        if token["trades5m"] < 40 or token["buyRatio5m"] < min_buy_ratio:
            return f"early r2: requiere 40 trades y compras >={min_buy_ratio:.0%}"
    age = token.get("ageMinutes")
    if entry_mode == "early" and (age is None or not 2 <= age <= 60):
        return "comparacion: edad fuera de 2-60 min"
    if not 2 <= token["change5m"] <= 60:
        return "comparacion: momentum 5m fuera de 2-60%"
    now = datetime.now(timezone.utc)
    old = ultima_lectura_par(token)
    if old is None:
        return "comparacion: falta lectura previa del mismo par"
    try:
        minutes = (now - datetime.fromisoformat(old["hora"])).total_seconds() / 60
    except (ValueError, KeyError):
        return "comparacion: lectura previa invalida"
    if not 0.5 <= minutes <= MAX_CONFIRMATION_MINUTES:
        return "comparacion: lectura previa fuera de 30-90 segundos"
    if entry_mode == "impulse":
        # No perseguir velas 5m ya extendidas: la run 143 entro en HODLUP
        # con +45.71%/5m y termino inmediatamente en stop. El impulso debe
        # acelerar, pero todavia estar en una zona de entrada razonable.
        if not 2 <= numero(old.get("change5m")) <= 25:
            return "impulso r4: lectura anterior 5m fuera de 2-25%"
        if not 2 <= numero(token.get("change5m")) <= 25:
            return "impulso r4: vela 5m extendida fuera de 2-25%"
        price_growth = variacion(token["price"], old.get("price"))
        volume_growth = variacion(token["vol5m"], old.get("vol5m"))
        if price_growth is None or not 1 <= price_growth <= 20:
            return "impulso r4: precio entre lecturas fuera de 1-20%"
        if volume_growth is None or volume_growth < 10:
            return "impulso r4: volumen5m no crece al menos 10%"
        if token["liquidity"] < 0.95 * numero(old.get("liquidity")):
            return "impulso r4: liquidez cae mas del 5%"
        return None
    if numero(old.get("change1h")) > 150:
        return "early r5: lectura anterior subida 1h > 150%"
    if not 2 <= numero(old.get("change5m")) <= 60:
        return "early r2: lectura anterior sin momentum positivo sostenido"
    growth = variacion(token["price"], old.get("price"))
    if growth is None or not 1 <= growth <= 12:
        return "early r2: precio entre lecturas fuera de 1-12%"
    if token["liquidity"] < 0.95 * numero(old.get("liquidity")):
        return "early r2: liquidez cae mas del 5%"
    if token["vol5m"] < numero(old.get("vol5m")):
        return "early r2: volumen5m decreciente"
    return None


EXIT_SERVICE_AT = None


def service_discovery_exits():
    """Cooperative exit priority at safe discovery boundaries; no concurrent writers."""
    global EXIT_SERVICE_AT
    if EXIT_WATCHDOG is not None:
        return  # Independent worker owns exit-only passes during discovery.
    if EXIT_SERVICE_AT is None or time.monotonic() < EXIT_SERVICE_AT:
        return
    refresh_open_positions()
    EXIT_SERVICE_AT = time.monotonic() + 15


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
        service_discovery_exits()
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
        service_discovery_exits()
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
        service_discovery_exits()
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


def main(refresh_events=True):
    from candle_lab import begin_cycle
    begin_cycle()
    service_discovery_exits()
    ahora = datetime.now(timezone.utc)

    print("🧠 FOMO Brain v10 - DEX + FOMO TRADER RADAR + PAPER")
    fomo_events = consultar_fomo_trader_radar()
    print(f"FOMO Trader Radar: {FOMO_RADAR_STATUS} | eventos verificados={len(fomo_events)}")
    eventos = cargar_eventos()
    nuevos_eventos = consultar_x() if refresh_events else []
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
        service_discovery_exits()
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

    service_discovery_exits()
    print("V10 EARLY: edad del PAR 2-60m; no equivale a edad del token ni a graduacion FOMO. Subida1h >150% es aviso.")
    simular_cartera(ranking, V10_FILE, "V10 EARLY", confirm=True)
    try:
        from candle_lab import guard as candle_guard
        simular_cartera(ranking, V10_R3_FILE, "V10-r3 EARLY + VELAS", confirm=True,
                        entry_mode="early", entry_guard=candle_guard(True, "early", "V10-r3 EARLY + VELAS"))
    except Exception as exc:
        print("V10-r3 ERROR: " + str(exc) + "; V10 historicas permanecen separadas")
    print("V10 IMPULSO: cartera independiente; no sumar con EARLY. Holders SIN FUENTE VERIFICADA.")
    simular_cartera(ranking, V10_IMPULSE_FILE, "V10 IMPULSO", confirm=True, entry_mode="impulse")
    if os.getenv("BRAIN_CANDLE_LAB", "0") == "1":
        try:
            from candle_lab import run as run_candle_lab
            run_candle_lab(ranking, simular_cartera)
        except Exception as exc:
            print("LAB VELAS ERROR: " + str(exc) + "; V10 historicas permanecen separadas")
    if os.getenv("BRAIN_RATIO_LAB", "0") == "1":
        try:
            from ratio_lab import run as run_ratio_lab
            run_ratio_lab(ranking, simular_cartera)
        except Exception as exc:
            print("LAB RATIO ERROR: " + str(exc) + "; historiales separados")
    if os.getenv("BRAIN_PROTECT_LAB", "0") == "1":
        try:
            from protection_lab import run as run_protection_lab
            run_protection_lab(ranking, simular_cartera)
        except Exception as exc:
            print("LAB PROTECCION ERROR: " + str(exc) + "; otros laboratorios siguen activos")
        if os.getenv("BRAIN_CANDLE_LAB", "0") == "1":
            try:
                from protection_lab import run_velas
                run_velas(ranking, simular_cartera)
            except Exception as exc:
                print("LAB PROTECT VELAS ERROR: " + str(exc) + "; historial original conservado")
    if os.getenv("BRAIN_VOLUME_LAB", "0") == "1":
        try:
            from volume_lab import run as run_volume_lab
            run_volume_lab(ranking, simular_cartera)
        except Exception as exc:
            print("LAB VOLUMEN ERROR: " + str(exc) + "; carteras anteriores siguen separadas")
    if os.getenv("BRAIN_M4_LAB", "0") == "1":
        try:
            from m4_lab import run as run_m4_lab
            run_m4_lab(ranking, simular_cartera)
        except Exception as exc:
            print("LAB M4 ERROR: " + str(exc) + "; historiales originales conservados")
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
    print("✅ FOMO Brain v10 terminado")

    print(
        "Modo análisis únicamente | "
        f"exposición futura máxima: "
        f"€{MAX_EXPOSURE_EUR:.2f}"
    )


def refresh_open_positions(stop_event=None):
    """Exit-only ticks: never discover candidates, bootstrap wallets or buy."""
    wallets = [(V10_FILE, "V10 EARLY", "early", .60, False),
               (V10_IMPULSE_FILE, "V10 IMPULSO", "impulse", .60, False),
               (V10_R3_FILE, "V10-r3 EARLY + VELAS", "early", .60, False)]
    for mode in ("early", "impulse"):
        if os.getenv("BRAIN_CANDLE_LAB", "0") == "1":
            for arm in ("control", "velas"):
                wallets.append((f"fomo_lab_{mode}_{arm}_r1.json",
                                f"LAB {mode.upper()} {arm.upper()} r1", mode, .60, False))
        if os.getenv("BRAIN_RATIO_LAB", "0") == "1":
            for ratio in (60, 52):
                wallets.append((f"fomo_lab_ratio_{mode}_{ratio}_r1.json",
                                f"LAB RATIO {mode.upper()} {ratio}% r1", mode, ratio / 100, False))
        if os.getenv("BRAIN_PROTECT_LAB", "0") == "1":
            for arm in ("control", "protect"):
                wallets.append((f"fomo_lab_protect_{mode}_{arm}_r1.json",
                                f"LAB PROTECT {mode.upper()} {arm.upper()} r1", mode, .60, arm == "protect"))
    JSON_CACHE.clear()  # Fresh quotes shared across wallets within this tick only.
    if os.getenv("BRAIN_M4_LAB", "0") == "1":
        from m4_lab import CONTROL, RECOVERY
        for path in (CONTROL, RECOVERY):
            wallets.append((path, "LAB M4 " + path, "early", .60, False))
    if os.getenv("BRAIN_PROTECT_LAB", "0") == "1" and os.getenv("BRAIN_CANDLE_LAB", "0") == "1":
        from protection_lab import velas_filename
        for arm in ("control", "protect"):
            wallets.append((velas_filename(arm), f"LAB PROTECT VELAS {arm.upper()} r1",
                            "early", .60, arm == "protect"))
    if os.getenv("BRAIN_VOLUME_LAB", "0") == "1":
        for arm in ("control", "volume"):
            wallets.append((f"fomo_lab_volume_impulse_{arm}_r1.json",
                            f"LAB VOLUME IMPULSE {arm.upper()} r1", "impulse", .60, False))
    for path, label, mode, ratio, protect in wallets:
        if stop_event is not None and stop_event.is_set():
            break
        lock = wallet_lock(path)
        if not lock.acquire(blocking=False):
            print(f"WATCHDOG POSPUESTO {label}: transaccion de la misma cartera activa", flush=True)
            continue
        try:
            with open(path) as handle:
                state = json.load(handle)
            if not state.get("positions"):
                continue
            print(f"V10 SALIDAS {'WATCHDOG 3s objetivo' if EXIT_WATCHDOG is not None else '15s'} | {label}", flush=True)
            simular_cartera([], path, label, confirm=True, entry_mode=mode,
                            min_buy_ratio=ratio, profit_protection=protect,
                            quarantine_m4=os.path.basename(path) == "fomo_lab_m4_recovery_r1.json")
        except FileNotFoundError:
            continue
        except Exception as exc:
            print(f"V10 SALIDAS ERROR {label}: {exc}", flush=True)
        finally:
            lock.release()


def run_session(cycles=1, interval_seconds=60):
    global EXIT_SERVICE_AT, EXIT_WATCHDOG
    # Ventana acotada: no cambia el cron ni presupone continuidad entre runs.
    if not 1 <= cycles <= SESSION_MAX_CYCLES or interval_seconds < 60:
        raise ValueError("Sesion: 1-15 lecturas e intervalo >=60s")
    started = time.monotonic()
    EXIT_SERVICE_AT = started
    route_shadow = None
    try:
        if os.getenv("BRAIN_ROUTE_SHADOW", "1") == "1":
            from route_shadow import RouteShadow
            route_shadow = RouteShadow(duration=SESSION_WINDOW_SECONDS)
            route_shadow.start()
        if os.getenv("BRAIN_EXIT_WATCHDOG", "0") == "1":
            EXIT_WATCHDOG = ExitWatchdog(refresh_open_positions, interval=3,
                                         duration=SESSION_WINDOW_SECONDS)
            EXIT_WATCHDOG.start()
            print("WATCHDOG r1 INICIO | objetivo 3s | solo salidas virtuales | sin continuidad entre runs", flush=True)
        for index in range(cycles):
            if index and time.monotonic() - started >= SESSION_WINDOW_SECONDS:
                break
            JSON_CACHE.clear()
            REJECTIONS.clear()
            print(f"V10 LECTURA {index + 1}/{cycles}", flush=True)
            main(refresh_events=index == 0)
            if EXIT_WATCHDOG is not None and EXIT_WATCHDOG.error is not None:
                raise RuntimeError("Vigilante de salidas fallo") from EXIT_WATCHDOG.error
            if index + 1 < cycles:
                remaining = SESSION_WINDOW_SECONDS - (time.monotonic() - started)
                delay = max(0, started + (index + 1) * interval_seconds - time.monotonic())
                if remaining <= 0 or delay >= remaining:
                    break
                deadline = started + (index + 1) * interval_seconds
                tick = started + index * interval_seconds + 15
                while EXIT_WATCHDOG is None and tick < deadline:
                    if time.monotonic() < tick:
                        time.sleep(tick - time.monotonic())
                    if time.monotonic() >= min(deadline, started + SESSION_WINDOW_SECONDS):
                        break
                    refresh_open_positions()
                    # Skip missed ticks; never issue a burst to catch up.
                    tick += 15
                    while tick <= time.monotonic():
                        tick += 15
                delay = max(0, deadline - time.monotonic())
                if delay:
                    time.sleep(delay)
    finally:
        if EXIT_WATCHDOG is not None:
            EXIT_WATCHDOG.stop()
            EXIT_WATCHDOG = None
        if route_shadow is not None:
            route_shadow.stop()
        EXIT_SERVICE_AT = None


if __name__ == "__main__":
    run_session(int(os.getenv("BRAIN_CYCLES", "1")))


