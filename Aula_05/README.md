# Aula 05 · Interoperabilidade com MCP

Continuação do Assistente de Atendimento e Operações: mesmo fan-out de logística/resolução, RAG e memória da Aula 04, agora com ferramentas em um servidor **customizado para a aula**. SDK oficial `mcp==2.2.0`; protocolo observado `2026-07-28`. [SDK Python](https://github.com/modelcontextprotocol/python-sdk)


## Executar

Na raiz do repositório, use a **mesma `.venv`, `.env` e `requirements.txt` das aulas anteriores**. Setup completo no [README principal](../README.md).

```powershell
.\.venv\Scripts\python.exe Aula_05/app.py
```

Abra http://127.0.0.1:5002. Diagnóstico MCP funciona sem chave. O chat usa `OPENAI_API_KEY` do `.env` da raiz e o modelo configurado em `OPENAI_MODEL`. Reinicie após mudar `.env` ou fixtures. Salvar Python recarrega o Flask; reinicie separadamente o servidor HTTP se sua fonte mudar.

| Integração | Operações | Políticas |
|---|---|---|
| `local` | Funções locais | Busca local |
| `mcp_tools` | MCP | Busca local |
| `mcp_tools_rag` | MCP | Busca MCP |



