import os
import httpx
from fastmcp import FastMCP

# Inicializa o conector MCP
mcp = FastMCP("Telegram Bot MCP")

# Token do BotFather
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "SEU_TOKEN_AQUI")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

@mcp.tool()
async def enviar_mensagem_telegram(chat_id: str, mensagem: str) -> str:
    """Envia uma mensagem de texto para o Telegram através do bot."""
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": mensagem,
            "parse_mode": "Markdown"
        }
        res = await client.post(url, json=payload)
        data = res.json()
        if data.get("ok"):
            return "Mensagem entregue com sucesso no seu Telegram!"
        return f"Falha no envio: {data.get('description')}"

@mcp.tool()
async def ler_ultimas_mensagens(quantidade: int = 5) -> str:
    """Lê as mensagens recentes recebidas pelo bot no Telegram."""
    async with httpx.AsyncClient() as client:
        url = f"{BASE_URL}/getUpdates?limit={quantidade}"
        res = await client.get(url)
        data = res.json()
        if not data.get("ok"):
            return f"Erro ao consultar: {data.get('description')}"
        
        mensagens = data.get("result", [])
        if not mensagens:
            return "Nenhuma nova mensagem encontrada no Telegram."
        
        lista = []
        for item in mensagens:
            msg = item.get("message", {})
            remetente = msg.get("from", {}).get("first_name", "Desconhecido")
            cid = msg.get("chat", {}).get("id")
            texto = msg.get("text", "(sem texto)")
            lista.append(f"De {remetente} (Chat ID: {cid}): {texto}")
        
        return "\n".join(lista)

if __name__ == "__main__":
    porta = int(os.environ.get("PORT", 8000))
    mcp.run(transport="sse", host="0.0.0.0", port=porta)
