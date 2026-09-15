import asyncio
import logging

import httpx
import pytest

from admin_bot.login_code import LoginCodeClient, LoginCodeError, LoginCodeIdentity


@pytest.mark.parametrize("failure", [httpx.ConnectTimeout, httpx.ConnectError])
@pytest.mark.parametrize("recovers", [True, False])
def test_connection_retries_are_bounded_and_logs_do_not_leak(failure, recovers, monkeypatch, caplog):
    calls = []
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("admin_bot.login_code.asyncio.sleep", sleep)
    caplog.set_level(logging.WARNING)

    async def run():
        async def handler(request):
            calls.append(request.content)
            if len(calls) < 3 or not recovers:
                raise failure("secret-token private-user", request=request)
            return httpx.Response(200, json={"login_code": "BC-SECRET", "expires_in": 300})

        client = LoginCodeClient("https://api.test/api/v1", "secret-token")
        await client._client.aclose()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test/api/v1")
        try:
            identity = LoginCodeIdentity(provider="telegram", provider_user_id="private-user")
            if recovers:
                assert (await client.create_login_code(identity)).login_code == "BC-SECRET"
            else:
                with pytest.raises(LoginCodeError):
                    await client.create_login_code(identity)
        finally:
            await client.close()

    asyncio.run(run())
    assert len(calls) == 3
    assert calls[0] == calls[1] == calls[2]
    assert delays == [0.5, 1.0]
    assert failure.__name__ in caplog.text
    for secret in ["secret-token", "private-user", "BC-SECRET"]:
        assert secret not in caplog.text


@pytest.mark.parametrize("failure", [httpx.ReadTimeout, httpx.WriteError, 401, 429, 503, "invalid_json", "missing_fields"])
def test_ambiguous_or_server_failures_are_not_replayed(failure, caplog):
    calls = []
    caplog.set_level(logging.WARNING)

    async def run():
        async def handler(request):
            calls.append(request)
            if isinstance(failure, int):
                return httpx.Response(failure, text="secret-response")
            if failure == "invalid_json":
                return httpx.Response(200, text="secret-response")
            if failure == "missing_fields":
                return httpx.Response(200, json={"login_code": "secret-response"})
            raise failure("secret-response", request=request)

        client = LoginCodeClient("https://api.test/api/v1", "token")
        await client._client.aclose()
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test/api/v1")
        try:
            with pytest.raises(LoginCodeError):
                await client.create_login_code(LoginCodeIdentity(provider="telegram", provider_user_id="123"))
        finally:
            await client.close()

    asyncio.run(run())
    assert len(calls) == 1
    assert "Login code" in caplog.text
    assert "secret-response" not in caplog.text
