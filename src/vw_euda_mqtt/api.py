"""Client for the VW EU Data Act portal.

Adapted from https://github.com/mikrohard/hass-vw-eu-data-act (MIT).
"""

from __future__ import annotations

import io
import json
import logging
import re
import uuid
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlparse

import aiohttp

LOG = logging.getLogger(__name__)

BASE_URL = "https://eu-data-act.drivesomethinggreater.com"
IDENTITY_BASE = "https://identity.vwgroup.io"
OIDC_AUTHORIZE_URL = IDENTITY_BASE + "/oidc/v1/authorize"
OIDC_CLIENT_ID = "9b58543e-1c15-4193-91d5-8a14145bebb0@apps_vw-dilab_com"
OIDC_SCOPE = "openid cars profile"
OIDC_REDIRECT_URI = BASE_URL + "/login"

VEHICLES_PATH = "/proxy_api/consent/me/vehicles"
RELATION_PATH = "/proxy_api/vum/v2/users/me/relations/{vin}"
METADATA_PATH = "/proxy_api/euda-apim/datarequest/vehicles/{vin}/metadata/partial"
LIST_PATH = "/proxy_api/euda-apim/datadelivery/vehicles/{vin}/{identifier}/list"
DOWNLOAD_PATH = "/proxy_api/euda-apim/datadelivery/vehicles/{vin}/{identifier}/download"

NO_CONTENT_SUFFIX = "_no_content_found.zip"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


class ApiError(Exception):
    """Generic API failure."""


class AuthError(ApiError):
    """Authentication failed or session expired."""


@dataclass(frozen=True)
class PortalConfig:
    email: str
    password: str
    brand: str = "AUDI"
    country: str = "de"
    language: str = "de"

    @property
    def oidc_state(self) -> str:
        return f"{self.country}__{self.language}__{self.brand}"


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._in_form = False
        self._done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        attr = dict(attrs)
        if tag == "form" and self.action is None:
            self.action = attr.get("action")
            self._in_form = True
        elif tag == "input" and self._in_form:
            name = attr.get("name")
            if name:
                self.fields[name] = attr.get("value") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._in_form:
            self._in_form = False
            self._done = True


def _parse_form(html: str) -> _FormParser:
    parser = _FormParser()
    parser.feed(html)
    return parser


def _extract_template_model(html: str) -> dict:
    idx = html.find("templateModel")
    if idx == -1:
        return {}
    brace = html.find("{", idx)
    if brace == -1:
        return {}
    depth = 0
    for i in range(brace, len(html)):
        char = html[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[brace : i + 1])
                except ValueError:
                    return {}
    return {}


def _extract_csrf(html: str) -> str | None:
    match = re.search(r"csrf_token\s*[:=]\s*['\"]([^'\"]+)['\"]", html)
    return match.group(1) if match else None


def _login_fields(html: str) -> tuple[dict[str, str], str | None]:
    form = _parse_form(html)
    fields: dict[str, str] = dict(form.fields)
    model = _extract_template_model(html)
    if model:
        for key in ("hmac", "relayState"):
            if model.get(key):
                fields[key] = model[key]
        email = (model.get("emailPasswordForm") or {}).get("email")
        if email:
            fields.setdefault("email", email)
    csrf = _extract_csrf(html)
    if csrf:
        fields.setdefault("_csrf", csrf)
    return fields, form.action


def _login_error(html: str) -> str | None:
    model = _extract_template_model(html)
    err = model.get("error") or model.get("errorCode")
    if isinstance(err, dict):
        return err.get("text") or err.get("errorCode") or str(err)
    return str(err) if err else None


def _extract_vins(payload) -> list[dict]:
    vins: dict[str, dict] = {}

    def walk(node):
        if isinstance(node, dict):
            vin = node.get("vin") or node.get("vehicleIdentificationNumber")
            if isinstance(vin, str) and len(vin) == 17:
                vins.setdefault(vin, {"vin": vin})
                nick = node.get("vehicleNickname") or node.get("nickname") or node.get("modelName")
                if nick:
                    vins[vin]["nickname"] = nick
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    return list(vins.values())


class EudaApiClient:
    """Authenticated client for the EU Data Act portal."""

    def __init__(self, session: aiohttp.ClientSession, config: PortalConfig) -> None:
        self._session = session
        self._config = config
        self._logged_in = False

    async def _get(
        self,
        url: str,
        *,
        headers: dict | None = None,
        allow_redirects: bool = True,
    ):
        request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
        return await self._session.get(
            url,
            headers=request_headers,
            allow_redirects=allow_redirects,
        )

    async def async_login(self) -> None:
        try:
            await self._do_login()
        except aiohttp.ClientError as err:
            raise ApiError(f"Network error during login: {err}") from err
        self._logged_in = True

    async def _do_login(self) -> None:
        try:
            async with await self._get(f"{BASE_URL}/") as resp:
                await resp.read()
        except aiohttp.ClientError as err:
            LOG.debug("Portal priming failed, continuing: %s", err)

        authorize_url = self._build_authorize_url()
        LOG.debug("OIDC authorize URL: %s", authorize_url)
        async with await self._get(authorize_url) as resp:
            signin_url = str(resp.url)
            signin_html = await resp.text()

        fields, action = _login_fields(signin_html)
        if "hmac" not in fields or "_csrf" not in fields:
            raise AuthError(f"Could not parse sign-in form, found fields: {sorted(fields)}")
        fields["email"] = self._config.email
        identifier_action = urljoin(signin_url, action or "")
        async with self._session.post(
            identifier_action,
            data=fields,
            headers={"User-Agent": USER_AGENT, "Referer": signin_url},
        ) as resp:
            authenticate_url = str(resp.url)
            authenticate_html = await resp.text()

        fields2, action2 = _login_fields(authenticate_html)
        if "hmac" not in fields2 or "_csrf" not in fields2:
            err = _login_error(authenticate_html)
            raise AuthError(
                err
                or "Identity portal did not return the password form. "
                "Check the email address or login flow."
            )
        fields2["email"] = self._config.email
        fields2["password"] = self._config.password
        authenticate_action = (
            urljoin(authenticate_url, action2)
            if action2
            else authenticate_url.split("?", 1)[0]
        )

        async with self._session.post(
            authenticate_action,
            data=fields2,
            headers={"User-Agent": USER_AGENT, "Referer": authenticate_url},
        ) as resp:
            landing = str(resp.url)
            landing_html = await resp.text()
            if resp.status >= 400:
                err = _login_error(landing_html)
                raise AuthError(err or f"Login rejected with HTTP {resp.status}")

        portal_host = urlparse(BASE_URL).netloc
        if "terms-and-conditions" in landing:
            raise AuthError(
                "The VW identity client requires one-time terms/registration confirmation. "
                "Log in to the EU Data Act portal in a browser once, accept the terms, "
                "then run the service again."
            )
        if "signin-service" in landing or "/error" in landing:
            raise AuthError("Login failed. Check email/password or complete browser login first.")
        if urlparse(landing).netloc != portal_host:
            raise AuthError(f"Login did not complete, ended at {landing}")

    def _build_authorize_url(self) -> str:
        params = {
            "client_id": OIDC_CLIENT_ID,
            "response_type": "code",
            "scope": OIDC_SCOPE,
            "state": self._config.oidc_state,
            "redirect_uri": OIDC_REDIRECT_URI,
            "prompt": "login",
        }
        return f"{OIDC_AUTHORIZE_URL}?{urlencode(params)}"

    async def _get_json(
        self,
        url: str,
        *,
        headers: dict | None = None,
        _retry: bool = True,
    ):
        try:
            async with await self._get(url, headers=headers) as resp:
                if resp.status in (401, 403) and _retry:
                    self._logged_in = False
                    await self.async_login()
                    return await self._get_json(url, headers=headers, _retry=False)
                if resp.status >= 400:
                    raise ApiError(f"GET {url} -> HTTP {resp.status}")
                text = await resp.text()
        except aiohttp.ClientError as err:
            raise ApiError(f"Connection error for {url}: {err}") from err
        try:
            return json.loads(text)
        except ValueError as err:
            raise ApiError(f"Invalid JSON from {url}: {err}") from err

    async def async_ensure_login(self) -> None:
        if not self._logged_in:
            await self.async_login()

    async def async_list_vehicles(self) -> list[dict]:
        await self.async_ensure_login()
        payload = await self._get_json(f"{BASE_URL}{VEHICLES_PATH}?viewPosition=FRONT_LEFT")
        vehicles = _extract_vins(payload)
        for vehicle in vehicles:
            try:
                relation = await self.async_get_relation(vehicle["vin"])
                nickname = (relation.get("relation") or {}).get("vehicleNickname")
                if nickname:
                    vehicle["nickname"] = nickname
            except ApiError as err:
                LOG.debug("Could not fetch vehicle nickname for %s: %s", vehicle["vin"], err)
        return vehicles

    async def async_get_relation(self, vin: str) -> dict:
        await self.async_ensure_login()
        headers = {"traceid": f"vehicle-relation-fetch-{uuid.uuid4()}"}
        return await self._get_json(
            f"{BASE_URL}{RELATION_PATH.format(vin=vin)}",
            headers=headers,
        )

    async def async_get_metadata(self, vin: str) -> dict:
        await self.async_ensure_login()
        return await self._get_json(f"{BASE_URL}{METADATA_PATH.format(vin=vin)}")

    async def async_list_datasets(self, vin: str, identifier: str) -> list[dict]:
        await self.async_ensure_login()
        url = f"{BASE_URL}{LIST_PATH.format(vin=vin, identifier=identifier)}"
        data = await self._get_json(url, headers={"type": "partial"})
        return data if isinstance(data, list) else data.get("files", [])

    async def async_download_dataset(self, vin: str, identifier: str, name: str) -> dict:
        await self.async_ensure_login()
        if name.endswith(NO_CONTENT_SUFFIX):
            raise ApiError(f"{name} contains no content")
        url = f"{BASE_URL}{DOWNLOAD_PATH.format(vin=vin, identifier=identifier)}"
        headers = {"filename": name, "type": "partial"}
        try:
            async with await self._get(url, headers=headers) as resp:
                if resp.status in (401, 403):
                    self._logged_in = False
                    await self.async_login()
                    async with await self._get(url, headers=headers) as resp2:
                        if resp2.status >= 400:
                            raise ApiError(f"Download {name} -> HTTP {resp2.status}")
                        raw = await resp2.read()
                elif resp.status >= 400:
                    raise ApiError(f"Download {name} -> HTTP {resp.status}")
                else:
                    raw = await resp.read()
        except aiohttp.ClientError as err:
            raise ApiError(f"Connection error downloading {name}: {err}") from err
        return self._unzip_json(raw, name)

    @staticmethod
    def _unzip_json(raw: bytes, name: str) -> dict:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                members = [item for item in zf.namelist() if item.lower().endswith(".json")]
                if not members:
                    raise ApiError(f"No JSON inside {name}")
                with zf.open(members[0]) as file:
                    return json.loads(file.read().decode("utf-8"))
        except (zipfile.BadZipFile, ValueError) as err:
            raise ApiError(f"Could not read {name}: {err}") from err
