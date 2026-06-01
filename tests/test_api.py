from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vw_euda_mqtt.api import (  # noqa: E402
    ApiError,
    EudaApiClient,
    PortalConfig,
    _extract_template_model,
    _extract_vins,
    _form_payload,
    _login_error,
    _login_fields,
    _marketing_payload,
    _safe_url_for_log,
    _terms_action_url,
    _terms_payload,
)


class PortalConfigTests(unittest.TestCase):
    def test_oidc_state_contains_country_language_and_brand(self) -> None:
        self.assertEqual(PortalConfig("user@example.com", "password", "AUDI", "de", "de").oidc_state, "de__de__AUDI")


class HtmlParsingTests(unittest.TestCase):
    def test_login_fields_merge_form_template_model_and_csrf(self) -> None:
        html = """
        <html>
          <script>
            window.templateModel = {
              "hmac": "hmac-value",
              "relayState": "relay-value",
              "emailPasswordForm": {"email": "prefilled@example.com"}
            };
            csrf_token = "csrf-value";
          </script>
          <form action="/identifier">
            <input name="existing" value="keep-me">
          </form>
        </html>
        """

        fields, action = _login_fields(html)

        self.assertEqual(action, "/identifier")
        self.assertEqual(fields["existing"], "keep-me")
        self.assertEqual(fields["hmac"], "hmac-value")
        self.assertEqual(fields["relayState"], "relay-value")
        self.assertEqual(fields["email"], "prefilled@example.com")
        self.assertEqual(fields["_csrf"], "csrf-value")

    def test_template_model_parser_returns_empty_dict_for_missing_or_invalid_model(self) -> None:
        self.assertEqual(_extract_template_model("<html></html>"), {})
        self.assertEqual(_extract_template_model("templateModel = {not-json}"), {})

    def test_login_error_extracts_nested_or_plain_error_text(self) -> None:
        self.assertEqual(_login_error('templateModel = {"error": {"text": "Denied"}};'), "Denied")
        self.assertEqual(_login_error('templateModel = {"errorCode": "BadCredentials"};'), "BadCredentials")
        self.assertIsNone(_login_error("<html></html>"))

    def test_form_payload_preserves_duplicate_input_order(self) -> None:
        payload = _form_payload(
            """
            <form>
              <input name="scope" value="cars">
              <input name="scope" value="profile">
              <input name="empty">
            </form>
            """
        )
        self.assertEqual(payload, [("scope", "cars"), ("scope", "profile"), ("empty", "")])

    def test_terms_payload_includes_documents_relay_state_hmac_and_csrf(self) -> None:
        html = """
        <script>
          templateModel = {
            "relayState": "relay",
            "hmac": "hmac",
            "legalDocuments": [
              {
                "name": "terms",
                "language": "de",
                "version": "1",
                "countryCode": "DE",
                "updated": true,
                "skippable": false,
                "declinable": true
              }
            ]
          };
          csrf_token = "csrf";
        </script>
        """

        payload = _terms_payload(html)

        self.assertEqual(payload["legalDocuments[0].name"], "terms")
        self.assertEqual(payload["legalDocuments[0].updated"], "yes")
        self.assertEqual(payload["legalDocuments[0].skippable"], "no")
        self.assertEqual(payload["legalDocuments[0].declinable"], "yes")
        self.assertEqual(payload["relayState"], "relay")
        self.assertEqual(payload["hmac"], "hmac")
        self.assertEqual(payload["_csrf"], "csrf")

    def test_terms_action_url_uses_client_id_from_template_model(self) -> None:
        html = 'templateModel = {"clientLegalEntityModel": {"clientId": "client-123"}};'
        self.assertEqual(
            _terms_action_url("https://identity.example/path?query=1", html),
            "https://identity.example/signin-service/v1/client-123/terms-and-conditions",
        )

    def test_marketing_payload_selects_bound_channels_and_skip_model_fields(self) -> None:
        html = """
        <script>
          templateModel = {
            "csrf": {"parameterName": "_csrf", "token": "csrf"},
            "documentKey": "doc",
            "relayStateToken": "relay",
            "hmac": "hmac",
            "countryOfJurisdiction": "DE",
            "language": "de",
            "callback": "https://example.com/callback",
            "marketChannels": [
              {"channelId": 1, "channelType": "BOUND_TO_BASIC_AGREEMENT"},
              {"channelId": 2, "channelType": "OPTIONAL"}
            ]
          };
        </script>
        """

        payload = dict(_marketing_payload(html))

        self.assertEqual(payload["_csrf"], "csrf")
        self.assertEqual(payload["documentKey"], "doc")
        self.assertEqual(payload["relayState"], "relay")
        self.assertEqual(payload["channel1"], "true")
        self.assertEqual(payload["channel2"], "false")

    def test_safe_url_for_log_removes_query_and_fragment(self) -> None:
        self.assertEqual(
            _safe_url_for_log("https://example.com/login?code=secret#frag"),
            "https://example.com/login",
        )
        self.assertEqual(_safe_url_for_log("/local/path?secret=value"), "/local/path")


class PayloadExtractionTests(unittest.TestCase):
    def test_extract_vins_finds_nested_unique_vehicle_identifiers(self) -> None:
        payload = {
            "vehicles": [
                {"vin": "TESTVIN1234567890", "vehicleNickname": "Primary"},
                {"vehicleIdentificationNumber": "TESTVIN1234567890", "modelName": "Duplicate"},
                {"relation": {"vehicleIdentificationNumber": "TESTVIN0000000001", "nickname": "Second"}},
            ]
        }

        self.assertEqual(
            _extract_vins(payload),
            [
                {"vin": "TESTVIN1234567890", "nickname": "Primary"},
                {"vin": "TESTVIN0000000001", "nickname": "Second"},
            ],
        )

    def test_unzip_json_returns_first_json_member(self) -> None:
        raw = _zip_bytes({"data.json": {"ok": True}, "readme.txt": "ignored"})
        self.assertEqual(EudaApiClient._unzip_json(raw, "dataset.zip"), {"ok": True})

    def test_unzip_json_raises_for_missing_json_or_invalid_zip(self) -> None:
        with self.assertRaises(ApiError):
            EudaApiClient._unzip_json(_zip_bytes({"readme.txt": "ignored"}), "dataset.zip")
        with self.assertRaises(ApiError):
            EudaApiClient._unzip_json(b"not-a-zip", "dataset.zip")


def _zip_bytes(files: dict[str, object]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, content in files.items():
            if isinstance(content, str):
                archive.writestr(name, content)
            else:
                archive.writestr(name, json.dumps(content))
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
