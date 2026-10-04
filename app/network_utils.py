from __future__ import annotations

import ipaddress
import socket

import psutil


def _is_virtual(adapter: str) -> bool:
    name = adapter.lower()
    return any(
        word in name
        for word in ("virtualbox", "vmware", "hyper-v", "vethernet", "wsl", "vpn", "loopback")
    )


def _label(ip: str, adapter: str) -> str:
    if ip.startswith("192.168.137."):
        return "Mode 2 Hotspot Laptop"
    if adapter and any(word in adapter.lower() for word in ("wi-fi", "wifi", "wlan")):
        return "Mode 1 Wi-Fi TPA"
    return "Kandidat jaringan lokal"


def get_private_candidates() -> list[dict[str, str]]:
    found: dict[str, str] = {}
    for adapter, addresses in psutil.net_if_addrs().items():
        if _is_virtual(adapter):
            continue
        for address_info in addresses:
            if address_info.family != socket.AF_INET:
                continue
            ip = address_info.address
            try:
                address = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if address.is_private and not ip.startswith(("127.", "169.254.")):
                found[ip] = adapter

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            address = ipaddress.ip_address(ip)
            if address.is_private and not ip.startswith(("127.", "169.254.")):
                found.setdefault(ip, "Wi-Fi/LAN")
    except OSError:
        pass

    try:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.settimeout(0.2)
        udp.connect(("8.8.8.8", 80))
        ip = udp.getsockname()[0]
        udp.close()
        address = ipaddress.ip_address(ip)
        if address.is_private and not ip.startswith(("127.", "169.254.")):
            found.setdefault(ip, "Koneksi utama")
    except OSError:
        pass

    return [
        {"ip": ip, "adapter": adapter, "label": _label(ip, adapter)}
        for ip, adapter in sorted(found.items())
    ]


def is_local_url(url: str) -> bool:
    parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(url)
    if parsed.scheme != "http" or parsed.path != "/scan" or parsed.port is None:
        return False
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        return False
    return address.is_private and not str(address).startswith(("127.", "169.254."))
