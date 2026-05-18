"""
Akzeptanztest: SSRF-Loopback-Block für `/api/connector/test` + `/api/connector/setup`.

Defense-in-Depth gegen Server-Side-Request-Forgery. Der Connector-Test-Endpoint
nahm vorher beliebige Hosts entgegen und schickte Requests dagegen — ein
authentifizierter Aufrufer konnte den Server gegen interne Endpoints,
Cloud-Metadata-Services oder den HA-Supervisor pivotieren.

Geblockt: Loopback, Link-local, Multicast, Unspecified, Reserved.
Erlaubt: Public-IPs + LAN-Bereiche (10/8, 172.16/12, 192.168/16) + DNS-Namen,
die auf solche Adressen auflösen.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_connector_ssrf_block.py
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from unittest.mock import patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from fastapi import HTTPException  # noqa: E402

from backend.api.routes.connector import (  # noqa: E402
    _extract_hostname,
    _validate_connector_host,
)


# ----------------------------------------------------------------------------
# Hostname-Extraktion
# ----------------------------------------------------------------------------

def test_extract_hostname_bare_ip() -> None:
    assert _extract_hostname("192.168.1.50") == "192.168.1.50"


def test_extract_hostname_url() -> None:
    assert _extract_hostname("https://192.168.1.50:80/api") == "192.168.1.50"


def test_extract_hostname_port_only() -> None:
    assert _extract_hostname("192.168.1.50:8080") == "192.168.1.50"


def test_extract_hostname_dns_name() -> None:
    assert _extract_hostname("wechselrichter.lan") == "wechselrichter.lan"


# ----------------------------------------------------------------------------
# Gefährliche Hosts werden geblockt
# ----------------------------------------------------------------------------

def _assert_blocked(host: str, resolved_ips: list[str]) -> None:
    """Hilfsfunktion: mockt getaddrinfo, erwartet HTTPException."""
    addrinfo = [(2, 1, 6, "", (ip, 0)) for ip in resolved_ips]
    with patch("backend.api.routes.connector.socket.getaddrinfo", return_value=addrinfo):
        try:
            _validate_connector_host(host)
        except HTTPException as e:
            assert e.status_code == 400
            return
        raise AssertionError(f"Host {host} ({resolved_ips}) sollte blockiert sein")


def _assert_allowed(host: str, resolved_ips: list[str]) -> None:
    addrinfo = [(2, 1, 6, "", (ip, 0)) for ip in resolved_ips]
    with patch("backend.api.routes.connector.socket.getaddrinfo", return_value=addrinfo):
        _validate_connector_host(host)  # darf nicht werfen


def test_loopback_127_geblockt() -> None:
    _assert_blocked("127.0.0.1", ["127.0.0.1"])


def test_loopback_alle_127_subnet_geblockt() -> None:
    _assert_blocked("127.5.5.5", ["127.5.5.5"])


def test_aws_metadata_geblockt() -> None:
    """169.254.169.254 ist AWS/GCP/Azure-Cloud-Metadata-Endpoint."""
    _assert_blocked("169.254.169.254", ["169.254.169.254"])


def test_link_local_169_254_geblockt() -> None:
    _assert_blocked("169.254.1.50", ["169.254.1.50"])


def test_ipv6_loopback_geblockt() -> None:
    _assert_blocked("::1", ["::1"])


def test_multicast_geblockt() -> None:
    _assert_blocked("224.0.0.1", ["224.0.0.1"])


def test_unspecified_geblockt() -> None:
    _assert_blocked("0.0.0.0", ["0.0.0.0"])


def test_dns_rebinding_geblockt() -> None:
    """Hostname löst auf Loopback auf → geblockt (auch wenn Hostname harmlos klingt)."""
    _assert_blocked("wechselrichter.evil.com", ["127.0.0.1"])


def test_dns_rebinding_alle_aufloesungen_geprueft() -> None:
    """Wenn auch nur EINE der aufgelösten IPs geblockt ist → reject."""
    _assert_blocked("multi.example.com", ["192.168.1.50", "127.0.0.1"])


# ----------------------------------------------------------------------------
# Erlaubte Hosts
# ----------------------------------------------------------------------------

def test_private_lan_10er_erlaubt() -> None:
    _assert_allowed("10.0.0.5", ["10.0.0.5"])


def test_private_lan_192_168_erlaubt() -> None:
    _assert_allowed("192.168.1.50", ["192.168.1.50"])


def test_private_lan_172_16_erlaubt() -> None:
    _assert_allowed("172.16.0.1", ["172.16.0.1"])


def test_public_ip_erlaubt() -> None:
    """Public-IPs sind erlaubt (für Cloud-Connectors mit explizitem Endpoint)."""
    _assert_allowed("8.8.8.8", ["8.8.8.8"])


def test_dns_name_auf_lan_erlaubt() -> None:
    _assert_allowed("wechselrichter.lan", ["192.168.1.50"])


def test_url_form_erlaubt() -> None:
    _assert_allowed("https://192.168.1.50:80/api", ["192.168.1.50"])


# ----------------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------------

def test_leerer_host_wirft() -> None:
    try:
        _validate_connector_host("")
    except HTTPException as e:
        assert e.status_code == 400
        return
    raise AssertionError("Leerer Host sollte HTTPException werfen")


def test_unresolvable_host_wirft() -> None:
    import socket as _socket
    with patch(
        "backend.api.routes.connector.socket.getaddrinfo",
        side_effect=_socket.gaierror("Name or service not known"),
    ):
        try:
            _validate_connector_host("does-not-resolve.invalid")
        except HTTPException as e:
            assert e.status_code == 400
            return
        raise AssertionError("Unresolvable Host sollte HTTPException werfen")


# ----------------------------------------------------------------------------
# Runner
# ----------------------------------------------------------------------------

ALLE_TESTS = [
    test_extract_hostname_bare_ip,
    test_extract_hostname_url,
    test_extract_hostname_port_only,
    test_extract_hostname_dns_name,
    test_loopback_127_geblockt,
    test_loopback_alle_127_subnet_geblockt,
    test_aws_metadata_geblockt,
    test_link_local_169_254_geblockt,
    test_ipv6_loopback_geblockt,
    test_multicast_geblockt,
    test_unspecified_geblockt,
    test_dns_rebinding_geblockt,
    test_dns_rebinding_alle_aufloesungen_geprueft,
    test_private_lan_10er_erlaubt,
    test_private_lan_192_168_erlaubt,
    test_private_lan_172_16_erlaubt,
    test_public_ip_erlaubt,
    test_dns_name_auf_lan_erlaubt,
    test_url_form_erlaubt,
    test_leerer_host_wirft,
    test_unresolvable_host_wirft,
]


def main() -> int:
    fehler = 0
    for fn in ALLE_TESTS:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:  # noqa: BLE001
            fehler += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    if fehler:
        print(f"\n{fehler} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {len(ALLE_TESTS)} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
