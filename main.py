"""Personal Telegram bot exposed as an authenticated MCP server."""

import os

import httpx
import uvicorn
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Configure {name} no ambiente do Render.")
    return value


MCP_ACCESS_TOKEN = required_env("MCP_ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DEFAULT_CHAT_ID = os.getenv("DEFAULT_CHAT_ID", "").strip()

auth = StaticTokenVerifier(
    tokens={MCP_ACCESS_TOKEN: {"client_id": "personal-gemini-spark", "scopes": ["telegram"]}},
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
app = mcp.http_app(middleware=middleware, stateless_http=True, json_response=True)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
