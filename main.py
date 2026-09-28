"""Personal Telegram bot exposed as an authenticated MCP server."""

import os
import threading
import time

import httpx
import uvicorn
from fastmcp import FastMCP
from fastmcp.server.auth.providers.google import GoogleProvider, GoogleTokenVerifier
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from mcp.server.auth.provider import TokenError
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Configure {name} no ambiente do Render.")
    return value


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DEFAULT_CHAT_ID = os.getenv("DEFAULT_CHAT_ID", "").strip()

class PersonalGoogleProvider(GoogleProvider):
    """Permit OAuth token exchange only for the owner's verified Google account."""

    def __init__(self, *, allowed_email: str, client_id: str, **kwargs):
        self._allowed_email = allowed_email.casefold()
        self._identity_verifier = GoogleTokenVerifier(
            required_scopes=["openid", "email"], audience=client_id
        )
        super().__init__(client_id=client_id, required_scopes=["openid", "email"], **kwargs)

    async def _extract_upstream_claims(self, idp_tokens: dict) -> dict:
        token = await self._identity_verifier.verify_token(idp_tokens["access_token"])
        claims = token.claims if token else {}
        email = str(claims.get("email") or "").casefold()
        verified = str(claims.get("email_verified") or "").lower() in {"true", "1"}
        if not verified or email != self._allowed_email:
            raise TokenError("invalid_grant", "Conta Google não autorizada para este servidor")
        return {"sub": token.subject, "email": email}


oauth_client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
oauth_client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
oauth_allowed_email = os.getenv("OAUTH_ALLOWED_EMAIL", "").strip()
if any((oauth_client_id, oauth_client_secret, oauth_allowed_email)):
    if not all((oauth_client_id, oauth_client_secret, oauth_allowed_email)):
        raise RuntimeError("Configure GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET e OAUTH_ALLOWED_EMAIL juntos.")
    auth = PersonalGoogleProvider(
        client_id=oauth_client_id,
        client_secret=oauth_client_secret,
        allowed_email=oauth_allowed_email,
        base_url="https://meu-telegram-mcp.onrender.com",
    )
else:
    auth = StaticTokenVerifier(
        tokens={required_env("MCP_ACCESS_TOKEN"): {
            "client_id": "personal-gemini-spark", "scopes": ["telegram"]
        }},
        required_scopes=["telegram"],
    )
mcp = FastMCP("Telegram pessoal", auth=auth)


@mcp.custom_route("/health", methods=["GET", "HEAD"])
async def health(_request):
    return JSONResponse({"status": "ok", "service": "telegram-mcp"})


@mcp.custom_route("/", methods=["GET", "HEAD"])
async def root(_request):
    return JSONResponse({"status": "ok", "mcp_endpoint": "/mcp"})


async def telegram_api(method: str, payload: dict) -> dict:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN não configurado no Render.")
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}", json=payload
        )
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise ValueError(f"Telegram: {data.get('description', 'falha desconhecida')}")
    return data


@mcp.tool()
async def enviar_mensagem_telegram(mensagem: str, chat_id: str = "") -> str:
    """Envia uma mensagem de texto ao chat pessoal autorizado no Telegram."""
    if not DEFAULT_CHAT_ID:
        return "Configure DEFAULT_CHAT_ID no Render antes de enviar mensagens."
    if chat_id and chat_id != DEFAULT_CHAT_ID:
        return "Chat ID não autorizado para este bot pessoal."
    if not mensagem.strip() or len(mensagem) > 4096:
        return "A mensagem deve conter entre 1 e 4096 caracteres."
    try:
        data = await telegram_api(
            "sendMessage", {"chat_id": DEFAULT_CHAT_ID, "text": mensagem}
        )
        return f"Mensagem entregue (ID {data['result']['message_id']})."
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return f"Falha no envio: {type(exc).__name__}. Confira o token, o chat e se iniciou o bot."


@mcp.tool()
async def ler_ultimas_mensagens(quantidade: int = 5) -> str:
    """Lê até 20 atualizações pendentes do chat pessoal; não é histórico completo."""
    if not DEFAULT_CHAT_ID:
        return "Configure DEFAULT_CHAT_ID no Render antes de ler mensagens."
    if not 1 <= quantidade <= 20:
        return "A quantidade deve estar entre 1 e 20."
    try:
        data = await telegram_api("getUpdates", {"limit": 100, "timeout": 0})
    except (httpx.HTTPError, ValueError):
        return "Falha na leitura. Confira o token e se há um webhook ativo no bot."
    mensagens = []
    for update in data.get("result", []):
        msg = update.get("message") or update.get("edited_message") or {}
        if str(msg.get("chat", {}).get("id", "")) != DEFAULT_CHAT_ID:
            continue
        texto = msg.get("text") or "(mensagem sem texto)"
        mensagens.append(f"{msg.get('date', '')}: {texto}")
    return "\n".join(mensagens[-quantidade:]) or "Nenhuma atualização pendente neste chat."


middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["https://gemini.google.com"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["authorization", "content-type", "mcp-protocol-version", "mcp-session-id", "mcp-method", "mcp-name"],
        expose_headers=["mcp-session-id"],
    )
]
app = mcp.http_app(
    middleware=[] if oauth_client_id else middleware,
    stateless_http=True,
    json_response=True,
)


def deployment_smoke_test(port: int) -> None:
    """One-time operational probe, enabled only for the initial deployment."""
    time.sleep(4)
    try:
        with httpx.Client(timeout=15.0) as client:
            handshake = client.post(
                f"http://127.0.0.1:{port}/mcp",
                headers={
                    "Authorization": f"Bearer {os.environ.get('MCP_ACCESS_TOKEN', '')}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25", "capabilities": {},
                        "clientInfo": {"name": "render-smoke-test", "version": "1.0"},
                    },
                },
            )
            valid = handshake.status_code == 200 and handshake.json().get("result", {}).get("serverInfo")
            print(f"SMOKE MCP handshake: {'OK' if valid else 'FALHOU'} (HTTP {handshake.status_code})", flush=True)
            if not valid or not TELEGRAM_BOT_TOKEN or not DEFAULT_CHAT_ID:
                return
            sent = client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": DEFAULT_CHAT_ID, "text": "Teste de integração: servidor MCP do AssistSBF ativo."},
            )
            print(f"SMOKE Telegram sendMessage: {'OK' if sent.json().get('ok') else 'FALHOU'} (HTTP {sent.status_code})", flush=True)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"SMOKE falhou: {type(exc).__name__}", flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    if os.getenv("SMOKE_TEST_ON_STARTUP") == "1" and not oauth_client_id:
        threading.Thread(target=deployment_smoke_test, args=(port,), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=port)
