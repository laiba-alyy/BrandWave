import hashlib
import ipaddress
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# ── SSRF guard ────────────────────────────────────────────────────────────────
#
# /verify-shopify, /generate-token aur /verify JAAN BOOJH KAR bina auth ke hain
# (onboarding wizard user ke login se PEHLE chalti hai). Lekin teeno ek user ka
# diya hua URL server se fetch karti thin, bina koi check kiye — yani koi bhi
# is backend ko andaruni network scan karne ke liye istemal kar sakta tha.
#
# Timing se pata chal jata tha ke kya zinda hai:
#     http://127.0.0.1:8000    ->  0.4s  (open)
#     http://localhost:1       ->  5.1s  (refused)
#     http://169.254.169.254   -> 10.4s  (filtered — cloud metadata service)
#
# Cloud par 169.254.169.254 instance metadata deta hai (IAM credentials tak).
# Is liye fetch karne se PEHLE hostname resolve kar ke dekhte hain ke koi bhi
# resolved address private/loopback/link-local to nahi.

class UnsafeUrlError(ValueError):
    """URL private ya andaruni network ki taraf ishara kar raha hai."""


_ALLOWED_SCHEMES = {"http", "https"}


def _is_public_address(ip: str) -> bool:
    """Sirf asli public internet addresses qubool — baaqi sab reject."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private          # 10/8, 172.16/12, 192.168/16, fc00::/7
        or addr.is_loopback      # 127/8, ::1
        or addr.is_link_local    # 169.254/16 <- cloud metadata
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_safe_url(website_url: str) -> str:
    """
    URL ko public-internet ke liye validate karo, warna UnsafeUrlError.

    Hostname ke SAARE resolved addresses check hote hain — ek bhi private nikla
    to reject, taake aisa DNS naam kaam na kare jo jaan boojh kar 127.0.0.1 par
    point karta ho.

    Return: normalized URL (scheme lagi hui).
    """
    value = (website_url or "").strip()
    if not value:
        raise UnsafeUrlError("Website URL is required.")
    if not value.startswith(("http://", "https://")):
        value = "https://" + value

    parsed = urlparse(value)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError("Only http:// and https:// URLs are supported.")

    host = parsed.hostname
    if not host:
        raise UnsafeUrlError("That URL has no hostname.")

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        raise UnsafeUrlError(f"Could not resolve '{host}'. Check the address and try again.")

    addresses = {info[4][0] for info in infos}
    if not addresses or not all(_is_public_address(a) for a in addresses):
        raise UnsafeUrlError(
            "That address is not reachable on the public internet. "
            "Enter your live store URL."
        )

    return value


def verify_shopify_store(website_url: str) -> bool:
    """Shopify store hai ya nahi verify karo — /products.json check"""
    try:
        website_url = assert_safe_url(website_url)

        parsed = urlparse(website_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        url = f"{base}/products.json?limit=1"
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            return "products" in data

        return False

    except UnsafeUrlError:
        raise      # caller isay 400 mein badalta hai — chup-chaap False nahi
    except Exception as e:
        print(f"Shopify verification error: {e}")
        return False


def generate_verification_token(website_url: str) -> str:
    """Website URL se unique token generate karo"""
    token = hashlib.md5(f"brandwave-{website_url}".encode()).hexdigest()[:16]
    return token


def check_verification(website_url: str, token: str) -> bool:
    """Website pe meta tag check karo"""
    try:
        website_url = assert_safe_url(website_url)

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(website_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        meta_tag = soup.find("meta", attrs={"name": "brandwave-verify"})
        if meta_tag and meta_tag.get("content") == token:
            return True
        return False

    except UnsafeUrlError:
        raise
    except Exception as e:
        print(f"Verification error: {e}")
        return False


def check_robots_txt(website_url: str) -> bool:
    """robots.txt check karo"""
    try:
        website_url = assert_safe_url(website_url)

        robots_url = website_url.rstrip("/") + "/robots.txt"
        response = requests.get(robots_url, timeout=5)

        if response.status_code == 404:
            return True

        lines = response.text.split("\n")
        user_agent_applies = False

        for line in lines:
            line = line.strip().lower()
            if line.startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                user_agent_applies = agent == "*"
            if user_agent_applies and line == "disallow: /":
                return False

        return True

    except:
        return True