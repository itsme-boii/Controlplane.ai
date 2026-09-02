from __future__ import annotations

import httpx


class ActionExecutionError(Exception):
    """Raised when an external action execution fails due to network/API issues."""

    pass


class MailtrapClient:
    def __init__(self, api_token: str, inbox_id: str, timeout_s: float = 15.0) -> None:
        self.api_token = api_token
        self.inbox_id = inbox_id
        self.client = httpx.AsyncClient(timeout=timeout_s)
        self.base_url = "https://sandbox.api.mailtrap.io/api"

    async def send_email(self, to: str, subject: str, body: str) -> dict:
        url = f"{self.base_url}/send/{self.inbox_id}"
        headers = {
            "Api-Token": self.api_token,
            "Content-Type": "application/json",
        }
        payload = {
            "to": [{"email": to}],
            "from": {"email": "controlplane@example.com", "name": "ControlPlane.ai"},
            "subject": subject,
            "text": body,
        }

        try:
            resp = await self.client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise ActionExecutionError(
                f"Mailtrap API error {e.response.status_code}: {e.response.text}"
            ) from e
        except httpx.RequestError as e:
            raise ActionExecutionError(f"Mailtrap network error: {e}") from e

    async def aclose(self) -> None:
        await self.client.aclose()
