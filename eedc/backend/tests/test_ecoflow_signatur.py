"""Akzeptanztest: EcoFlow-Signatur sortiert alle Parameter gemeinsam.

Bug (Dirk-PN 2026-05-21): `_build_sign_headers` sortierte nur die
Request-Parameter und hängte `accessKey/nonce/timestamp` hinten an.
EcoFlow signiert aber ALLE Parameter gemeinsam alphabetisch nach ASCII.
`device/list` (ohne Request-Parameter) klappte zufällig — beide
Konventionen ergeben denselben String. `device/quota/all?sn=…` scheiterte
mit `code 8521 signature is wrong`, weil eedc `sn=…&accessKey=…` statt
`accessKey=…&nonce=…&sn=…&timestamp=…` signierte.

Referenz-Beispiel EcoFlow: `accessKey=…&nonce=…&sn=…&timestamp=…`
"""

from __future__ import annotations

import hashlib
import hmac

from backend.services.cloud_import.ecoflow_powerocean import _build_sign_headers


def _erwarteter_sign(sign_str: str, secret_key: str) -> str:
    return hmac.new(
        secret_key.encode(), sign_str.encode(), hashlib.sha256
    ).hexdigest()


def test_sn_wird_alphabetisch_einsortiert():
    """sn steht im Sign-String zwischen nonce und timestamp, nicht davor."""
    headers = _build_sign_headers("AKtest", "SKtest", {"sn": "ABC123"})
    nonce, ts = headers["nonce"], headers["timestamp"]

    korrekt = f"accessKey=AKtest&nonce={nonce}&sn=ABC123&timestamp={ts}"
    assert headers["sign"] == _erwarteter_sign(korrekt, "SKtest")

    # Die alte (fehlerhafte) Konvention — sn vorangestellt — ergäbe eine
    # andere Signatur. Schützt davor, dass der Bug zurückkehrt.
    alt_buggy = f"sn=ABC123&accessKey=AKtest&nonce={nonce}&timestamp={ts}"
    assert headers["sign"] != _erwarteter_sign(alt_buggy, "SKtest")


def test_ohne_params_unveraendert():
    """Parameterloser Aufruf (device/list): accessKey&nonce&timestamp."""
    headers = _build_sign_headers("AKtest", "SKtest", None)
    nonce, ts = headers["nonce"], headers["timestamp"]

    erwartet = f"accessKey=AKtest&nonce={nonce}&timestamp={ts}"
    assert headers["sign"] == _erwarteter_sign(erwartet, "SKtest")


def test_verschachtelte_params_alle_gemeinsam_sortiert():
    """POST-Body mit verschachtelten Parametern: alle Keys (inkl.
    Auth-Triple) zusammen sortiert — `params.cmdSet` zwischen nonce und sn."""
    headers = _build_sign_headers(
        "AKtest", "SKtest", {"sn": "X9", "params": {"cmdSet": 11}}
    )
    nonce, ts = headers["nonce"], headers["timestamp"]

    korrekt = (
        f"accessKey=AKtest&nonce={nonce}&params.cmdSet=11&sn=X9&timestamp={ts}"
    )
    assert headers["sign"] == _erwarteter_sign(korrekt, "SKtest")
