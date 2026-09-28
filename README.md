# AssistSBF — Telegram MCP

Servidor MCP pessoal para conectar o bot do Telegram ao Gemini Spark.

## URL

`https://meu-telegram-mcp.onrender.com/mcp`

A URL só funcionará no Spark depois que o OAuth Google estiver configurado. O servidor mantém o modo de autenticação anterior enquanto as três variáveis OAuth estiverem ausentes.

## Configurar OAuth Google

1. No Google Cloud Console, crie ou selecione um projeto e configure **Google Auth Platform** com público **External**. Para uso de teste, adicione exclusivamente a conta Google que você usará no Gemini como usuário de teste.
2. Crie um cliente OAuth do tipo **Web application**. Em **Authorized redirect URIs**, cadastre exatamente:
   `https://meu-telegram-mcp.onrender.com/auth/callback`
3. No Render, configure as variáveis de ambiente, sem colocá-las neste repositório:
   - `GOOGLE_OAUTH_CLIENT_ID` — Client ID do aplicativo web.
   - `GOOGLE_OAUTH_CLIENT_SECRET` — Client Secret do aplicativo web.
   - `OAUTH_ALLOWED_EMAIL` — e-mail exato da conta Google autorizada.
4. Aguarde o deploy ficar Live. No Gemini Spark, adicione a URL MCP acima; o servidor apresentará a descoberta OAuth e solicitará o consentimento da conta permitida.

As variáveis `TELEGRAM_BOT_TOKEN` e `DEFAULT_CHAT_ID` são necessárias para as ferramentas. A leitura pelo Bot API cobre atualizações pendentes do bot, não um histórico completo.

## Serviço

- Runtime: Python
- Build: `pip install -r requirements.txt`
- Start: `python main.py`
- Verificação pública: `GET /health`

O provedor OAuth usa o fluxo do FastMCP e verifica o e-mail Google antes de emitir credenciais MCP. O armazenamento padrão do FastMCP no plano sem disco persistente do Render pode exigir nova vinculação após reinícios.
