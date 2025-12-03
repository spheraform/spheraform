"""Proxy management for geo-restricted servers."""

import random
import httpx
from typing import Optional, List, Dict
from dataclasses import dataclass
import os
from datetime import datetime, timedelta
from abc import ABC, abstractmethod


# ============================================================================
# Abstract Base Class
# ============================================================================


class ProxyProvider(ABC):
    """
    Abstract base class for proxy providers.

    All proxy providers must implement this interface to be used by ProxyManager.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for identification."""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Provider priority (higher = used first)."""
        pass

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether this provider is enabled."""
        pass

    @abstractmethod
    def get_proxy(self, country_hint: Optional[str] = None) -> Optional[str]:
        """
        Get a single proxy URL.

        Args:
            country_hint: Country code(s), comma-separated (e.g., "GB" or "BE,NL,LU")

        Returns:
            Proxy URL string or None
        """
        pass

    def get_proxies(self, country_hint: Optional[str] = None) -> List[str]:
        """
        Get multiple proxy URLs for fallback.

        Args:
            country_hint: Country code(s), comma-separated (e.g., "GB" or "BE,NL,LU")

        Returns:
            List of proxy URL strings
        """
        proxy = self.get_proxy(country_hint)
        return [proxy] if proxy else []


# ============================================================================
# ProxyScrape Provider (Free Proxies)
# ============================================================================


@dataclass
class ProxyScrapeProxy:
    """Proxy entry from ProxyScrape API."""

    ip: str
    port: int
    country: str  # 2-letter country code
    protocol: str
    anonymity: str
    alive: bool = True

    @property
    def url(self) -> str:
        """Get proxy URL in format http://ip:port"""
        return f"http://{self.ip}:{self.port}"


class ProxyScrapeProvider(ProxyProvider):
    """
    Free proxy provider using ProxyScrape API.

    Features:
    - Fetches free HTTP proxies
    - 15-minute cache to avoid API hammering
    - Country-based filtering with fallback
    """

    def __init__(self, enabled: bool = True, priority: int = 100):
        self._enabled = enabled
        self._priority = priority
        self._cache: List[ProxyScrapeProxy] = []
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=15)

    @property
    def name(self) -> str:
        return "proxyscrape"

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _fetch_proxies(self, force_refresh: bool = False) -> List[ProxyScrapeProxy]:
        """Fetch proxies from API with caching."""
        # Check cache
        if (
            not force_refresh
            and self._cache
            and self._cache_time
            and datetime.now() - self._cache_time < self._cache_ttl
        ):
            return self._cache

        try:
            url = "https://api.proxyscrape.com/v4/free-proxy-list/get"
            params = {
                "request": "displayproxies",
                "protocol": "http",
                "timeout": "10000",
                "country": "all",
                "ssl": "all",
                "anonymity": "all",
                "format": "json",
            }

            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                proxies = []
                if "proxies" in data:
                    for proxy_data in data["proxies"]:
                        try:
                            proxy = ProxyScrapeProxy(
                                ip=proxy_data.get("ip", ""),
                                port=int(proxy_data.get("port", 0)),
                                country=proxy_data.get("country", {}).get("code", "").upper(),
                                protocol=proxy_data.get("protocol", "http"),
                                anonymity=proxy_data.get("anonymity", "unknown"),
                                alive=proxy_data.get("alive", True),
                            )
                            if proxy.ip and proxy.port and proxy.alive:
                                proxies.append(proxy)
                        except (ValueError, KeyError):
                            continue

                self._cache = proxies
                self._cache_time = datetime.now()
                return proxies

        except Exception as e:
            print(f"Error fetching ProxyScrape proxies: {e}")
            return self._cache

    def get_proxy(self, country_hint: Optional[str] = None) -> Optional[str]:
        """Get a random proxy filtered by country."""
        if not self._enabled:
            print("ProxyScrape provider is disabled")
            return None

        proxies = self._fetch_proxies()
        print(f"ProxyScrape: Fetched {len(proxies)} proxies from cache/API")

        if not proxies:
            print("ProxyScrape: No proxies available")
            return None

        # If no country hint, return random proxy
        if not country_hint:
            proxy = random.choice(proxies)
            print(f"ProxyScrape: Selected random proxy {proxy.url} ({proxy.country})")
            return proxy.url

        # Try each country in comma-separated list
        countries = [c.strip().upper() for c in country_hint.split(",")]
        print(f"ProxyScrape: Filtering for countries: {countries}")

        for country in countries:
            country_proxies = [p for p in proxies if p.country == country]
            print(f"ProxyScrape: Found {len(country_proxies)} proxies for {country}")
            if country_proxies:
                proxy = random.choice(country_proxies)
                print(f"ProxyScrape: Selected {proxy.url} from {country}")
                return proxy.url

        # No proxies found for any requested country - return random one
        proxy = random.choice(proxies)
        print(f"ProxyScrape: No country match, using random proxy {proxy.url} ({proxy.country})")
        return proxy.url


# ============================================================================
# Proxifly Provider (Premium Rotating Proxies)
# ============================================================================


@dataclass
class ProxiflyConfig:
    """Configuration for Proxifly API integration."""

    api_key: str
    endpoint: str = "http://api.proxifly.dev:3000"
    country: Optional[str] = None
    enabled: bool = True


class ProxiflyProvider(ProxyProvider):
    """
    Premium proxy provider using Proxifly API.

    Features:
    - Rotating residential/datacenter proxies
    - Country-specific proxy selection
    - Built-in rotation on each request
    """

    def __init__(self, config: ProxiflyConfig, priority: int = 50):
        self._config = config
        self._priority = priority

    @property
    def name(self) -> str:
        return "proxifly"

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def _build_url(self, country: Optional[str] = None) -> str:
        """Build Proxifly proxy URL with optional country."""
        api_key = self._config.api_key
        endpoint = self._config.endpoint

        # If comma-separated countries, use first one
        if country and "," in country:
            country = country.split(",")[0].strip()

        # Build credentials with country if specified
        if country:
            credentials = f"{api_key}_{country.upper()}"
        else:
            credentials = api_key

        # Insert credentials into endpoint URL
        if endpoint.startswith("http://"):
            return f"http://{credentials}@{endpoint[7:]}"
        elif endpoint.startswith("https://"):
            return f"https://{credentials}@{endpoint[8:]}"
        else:
            return f"http://{credentials}@{endpoint}"

    def get_proxy(self, country_hint: Optional[str] = None) -> Optional[str]:
        """Get Proxifly proxy URL."""
        if not self._config.enabled:
            return None

        country = country_hint or self._config.country
        return self._build_url(country)

    def get_proxies(self, country_hint: Optional[str] = None) -> List[str]:
        """Get all Proxifly URLs for comma-separated countries."""
        if not self._config.enabled:
            return []

        country_str = country_hint or self._config.country
        if not country_str:
            proxy = self.get_proxy(None)
            return [proxy] if proxy else []

        # Build proxy URL for each country
        countries = [c.strip().upper() for c in country_str.split(",")]
        urls = []

        for country in countries:
            url = self._build_url(country)
            if url:
                urls.append(url)

        return urls


# ============================================================================
# Static Proxy Provider
# ============================================================================


@dataclass
class ProxyConfig:
    """Configuration for a single static proxy."""

    url: str  # Format: http://user:pass@host:port or http://host:port
    country: Optional[str] = None  # ISO country code (e.g., "GB", "US")
    enabled: bool = True
    priority: int = 0  # Higher priority proxies used first


class StaticProxyProvider(ProxyProvider):
    """
    Static proxy provider for manually configured proxies.

    Features:
    - Manual proxy configuration
    - Country-based filtering
    - Priority-based selection
    """

    def __init__(self, proxies: List[ProxyConfig], priority: int = 0):
        self._proxies = proxies
        self._priority = priority

    @property
    def name(self) -> str:
        return "static"

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def enabled(self) -> bool:
        return any(p.enabled for p in self._proxies)

    def get_proxy(self, country_hint: Optional[str] = None) -> Optional[str]:
        """Get proxy from static pool."""
        enabled_proxies = [p for p in self._proxies if p.enabled]
        if not enabled_proxies:
            return None

        # Filter by country if hint provided
        if country_hint:
            # Try each country in comma-separated list
            countries = [c.strip().upper() for c in country_hint.split(",")]
            for country in countries:
                country_proxies = [p for p in enabled_proxies if p.country == country]
                if country_proxies:
                    enabled_proxies = country_proxies
                    break

        # Sort by priority and select
        enabled_proxies.sort(key=lambda p: p.priority, reverse=True)
        max_priority = enabled_proxies[0].priority
        top_proxies = [p for p in enabled_proxies if p.priority == max_priority]

        return random.choice(top_proxies).url


# ============================================================================
# Server-Specific Proxy Provider
# ============================================================================


class ServerProxyProvider(ProxyProvider):
    """
    Server-specific proxy provider from connection_config.

    Handles:
    - Direct proxy URLs from connection_config
    - Server-specific Proxifly configuration
    """

    def __init__(self, connection_config: Dict, priority: int = 1000):
        self._connection_config = connection_config
        self._priority = priority

    @property
    def name(self) -> str:
        return "server_specific"

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def enabled(self) -> bool:
        return bool(
            self._connection_config.get("proxy")
            or self._connection_config.get("proxifly")
        )

    def get_proxy(self, country_hint: Optional[str] = None) -> Optional[str]:
        """Get server-specific proxy."""
        # Direct proxy URL
        proxy_config = self._connection_config.get("proxy")
        if proxy_config:
            if isinstance(proxy_config, str):
                return proxy_config
            elif isinstance(proxy_config, dict):
                return proxy_config.get("url")

        # Server-specific Proxifly config
        proxifly_config = self._connection_config.get("proxifly")
        if proxifly_config and isinstance(proxifly_config, dict):
            api_key = proxifly_config.get("api_key")
            if api_key:
                config = ProxiflyConfig(
                    api_key=api_key,
                    endpoint=proxifly_config.get("endpoint", "http://api.proxifly.dev:3000"),
                    country=proxifly_config.get("country"),
                )
                provider = ProxiflyProvider(config)
                return provider.get_proxy(country_hint)

        return None


# ============================================================================
# Proxy Manager
# ============================================================================


class ProxyManager:
    """
    Orchestrates multiple proxy providers with priority-based selection.

    Features:
    - Multiple provider support (ProxyScrape, Proxifly, static proxies)
    - Priority-based provider selection
    - Server-specific proxy configuration
    - Country-based proxy selection
    - Automatic fallback
    """

    def __init__(self):
        self._providers: List[ProxyProvider] = []

        # Check if ProxyScrape should be enabled (default: disabled to avoid unreliable free proxies)
        proxyscrape_enabled = os.getenv("PROXYSCRAPE_ENABLED", "false").lower() in ("true", "1", "yes")

        # Initialize default providers
        self._proxyscrape_provider = ProxyScrapeProvider(enabled=proxyscrape_enabled, priority=100)
        self._static_proxy_provider = StaticProxyProvider(proxies=[], priority=0)
        self._proxifly_provider: Optional[ProxiflyProvider] = None

        self.register_provider(self._proxyscrape_provider)
        self.register_provider(self._static_proxy_provider)

    def register_provider(self, provider: ProxyProvider):
        """Register a proxy provider."""
        self._providers.append(provider)
        # Keep sorted by priority (highest first)
        self._providers.sort(key=lambda p: p.priority, reverse=True)

    def add_global_proxy(self, proxy: ProxyConfig):
        """Add a proxy to the static global pool."""
        self._static_proxy_provider._proxies.append(proxy)

    def configure_proxifly(
        self,
        api_key: str,
        endpoint: str = "http://api.proxifly.dev:3000",
        country: Optional[str] = None,
    ):
        """Configure Proxifly API integration."""
        config = ProxiflyConfig(
            api_key=api_key,
            endpoint=endpoint,
            country=country,
            enabled=True,
        )

        # Remove existing Proxifly provider if any
        if self._proxifly_provider:
            self._providers.remove(self._proxifly_provider)

        # Create and register new Proxifly provider
        self._proxifly_provider = ProxiflyProvider(config, priority=50)
        self.register_provider(self._proxifly_provider)

    def get_proxy_for_server(
        self,
        server_connection_config: Optional[Dict] = None,
        country_hint: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get the best proxy for a server request.

        Priority order:
        1. Server-specific proxy (from connection_config) - priority 1000
        2. ProxyScrape free proxies - priority 100
        3. Proxifly premium proxies - priority 50
        4. Static proxy pool - priority 0

        Args:
            server_connection_config: Server's connection_config dict
            country_hint: Preferred country for proxy (e.g., "GB" for "BE,NL,LU")

        Returns:
            Proxy URL string or None if no proxy configured
        """
        providers = list(self._providers)  # Copy to avoid modification during iteration

        # Add server-specific provider if connection_config provided
        if server_connection_config:
            server_provider = ServerProxyProvider(server_connection_config, priority=1000)
            if server_provider.enabled:
                providers.insert(0, server_provider)

        # Try providers in priority order
        for provider in providers:
            if not provider.enabled:
                continue

            try:
                proxy = provider.get_proxy(country_hint)
                if proxy:
                    return proxy
            except Exception as e:
                print(f"Error getting proxy from {provider.name}: {e}")
                continue

        return None

    def get_httpx_proxy_config(
        self,
        server_connection_config: Optional[Dict] = None,
        country_hint: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """
        Get proxy configuration in httpx format.

        Returns:
            Dict with 'http://' and 'https://' keys, or None
        """
        proxy_url = self.get_proxy_for_server(server_connection_config, country_hint)
        if not proxy_url:
            return None

        return {"http://": proxy_url, "https://": proxy_url}

    def load_from_env(self):
        """
        Load proxy configuration from environment variables.

        Supports:
        - PROXYSCRAPE_ENABLED: Enable ProxyScrape free proxies (true/false, default: false)
        - PROXIFLY_API_KEY: Proxifly API key
        - PROXIFLY_COUNTRY: Default country code
        - PROXIFLY_ENDPOINT: Custom Proxifly endpoint
        - SPHERAFORM_PROXIES: Static proxy list format (url;country|url;country|...)
        """
        # Load Proxifly configuration
        proxifly_key = os.getenv("PROXIFLY_API_KEY")
        if proxifly_key:
            self.configure_proxifly(
                api_key=proxifly_key,
                endpoint=os.getenv("PROXIFLY_ENDPOINT", "http://api.proxifly.dev:3000"),
                country=os.getenv("PROXIFLY_COUNTRY"),
            )

        # Load static proxy list
        proxies_str = os.getenv("SPHERAFORM_PROXIES")
        if proxies_str:
            for proxy_entry in proxies_str.split("|"):
                parts = proxy_entry.split(";")
                url = parts[0].strip()
                country = parts[1].strip() if len(parts) > 1 else None

                self.add_global_proxy(ProxyConfig(url=url, country=country))


# ============================================================================
# Global Singleton Instance
# ============================================================================

# Global singleton instance
proxy_manager = ProxyManager()

# Auto-load from environment on import
proxy_manager.load_from_env()
