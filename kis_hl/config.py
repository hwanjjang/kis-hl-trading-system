from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

KIS_BASE_URLS = {
    "sim": "https://openapivts.koreainvestment.com:29443",
    "live": "https://openapi.koreainvestment.com:9443",
}

KIS_WS_URLS = {
    "sim": "ws://ops.koreainvestment.com:31000",
    "live": "ws://ops.koreainvestment.com:21000",
}

HL_MAINNET_URL = "https://api.hyperliquid.xyz"
HL_TESTNET_URL = "https://api.hyperliquid-testnet.xyz"


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    data_dir: Path
    log_level: str


@dataclass(frozen=True, slots=True)
class KisConfig:
    mode: str
    base_url: str
    app_key: str
    app_secret: str
    account_id: str
    account8: str
    product_code2: str
    hts_id: str
    token_dir: Path
    http_timeout_seconds: float
    min_request_interval_ms: int
    rate_limit_retries: int
    rate_limit_delay_ms: int
    ws_url: str = ""


@dataclass(frozen=True, slots=True)
class HyperliquidConfig:
    base_url: str
    account_address: str
    private_key: str
    key_profile: str
    ws_url: str = ""


def load_env_file(path: str | Path = ".env", *, override: bool = False) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_env_value(value.strip())
        if key and (override or key not in os.environ):
            os.environ[key] = value


def load_runtime_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    source = env or os.environ
    return RuntimeConfig(
        data_dir=Path(source.get("DATA_DIR", "data")),
        log_level=source.get("LOG_LEVEL", "INFO").upper(),
    )


def load_kis_config(env: Mapping[str, str] | None = None) -> KisConfig:
    source = env or os.environ
    sandbox = source.get("SANDBOX", "true").lower() != "false"
    mode = "sim" if sandbox else "live"

    if mode == "sim":
        app_key_name = "KIS_API_ST_KEY"
        app_secret_name = "KIS_API_ST_SECRET"
        account_name = "KIS_ST_STOCK_ACCOUNT"
    else:
        app_key_name = "KIS_API_KEY"
        app_secret_name = "KIS_API_SECRET"
        account_name = "KIS_STOCK_ACCOUNT"

    account_parts = normalize_kis_account(_require_env(source, account_name))
    token_dir = Path(source.get("KIS_TOKEN_DIR", "data/kis-tokens"))

    return KisConfig(
        mode=mode,
        base_url=source.get("KIS_BASE_URL", KIS_BASE_URLS[mode]),
        app_key=_require_env(source, app_key_name),
        app_secret=_require_env(source, app_secret_name),
        account_id=account_parts[0] + account_parts[1],
        account8=account_parts[0],
        product_code2=account_parts[1],
        hts_id=source.get("KIS_HTSID", ""),
        token_dir=token_dir,
        http_timeout_seconds=float(source.get("KIS_HTTP_TIMEOUT_SECONDS", "10")),
        min_request_interval_ms=int(source.get("KIS_MIN_REQUEST_INTERVAL_MS", "300")),
        rate_limit_retries=int(source.get("KIS_RATE_LIMIT_RETRIES", "2")),
        rate_limit_delay_ms=int(source.get("KIS_RATE_LIMIT_DELAY_MS", "500")),
        ws_url=source.get("KIS_WS_ST_URL" if mode == "sim" else "KIS_WS_URL", KIS_WS_URLS[mode]),
    )


def load_hyperliquid_config(env: Mapping[str, str] | None = None) -> HyperliquidConfig:
    source = env or os.environ
    profile = source.get("HYPERLIQUID_KEY_PROFILE", "default").strip().lower()
    if profile not in {"default", "production"}:
        raise RuntimeError("HYPERLIQUID_KEY_PROFILE must be 'default' or 'production'")
    if profile == "production":
        address_name = "PRO_HYPERLIQUID_WALLETADDRESS"
        private_key_name = "PRO_HYPERLIQUID_PRIVATEKEY"
    else:
        address_name = "HYPERLIQUID_WALLETADDRESS"
        private_key_name = "HYPERLIQUID_PRIVATEKEY"

    if "HYPERLIQUID_BASE_URL" in source:
        base_url = source["HYPERLIQUID_BASE_URL"]
    elif source.get("HYPERLIQUID_TESTNET", "false").lower() == "true":
        base_url = HL_TESTNET_URL
    else:
        base_url = HL_MAINNET_URL

    private_key = source.get(private_key_name, "").strip()
    if private_key and not private_key.startswith("0x"):
        private_key = "0x" + private_key

    return HyperliquidConfig(
        base_url=base_url,
        account_address=source.get(address_name, "").strip(),
        private_key=private_key,
        key_profile=profile,
        ws_url=source.get("HYPERLIQUID_WS_URL", "").strip(),
    )


def normalize_kis_account(raw: str) -> tuple[str, str]:
    compact = raw.replace("-", "").strip()
    if not compact.isdigit() or len(compact) != 10:
        raise ValueError("KIS stock account must be 10 digits including the 2-digit product code")
    return compact[:8], compact[8:]


def _require_env(source: Mapping[str, str], name: str) -> str:
    value = source.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value
