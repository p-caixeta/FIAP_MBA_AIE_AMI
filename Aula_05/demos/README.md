# Demos A/B

Dois servidores customizados, com o mesmo nome de ferramenta, descrição e schemas. A usa a fixture conhecida. B falsifica deliberadamente o status de E100 em `mcp_server.py`. Não são malware nem integrações de terceiros.

Na raiz do repositório:

```powershell
.\.venv\Scripts\python.exe Aula_05/diagnostics.py --compare
```

Também disponíveis no botão Comparar A/B da interface e na célula 41 do notebook 501. A comparação usa MCP real por stdio e não exige chave de modelo.

Resultado esperado: `same_catalog=true`; A informa `atrasado`, B informa `entregue`. Confira `dados/shipments.json` e o ramo `demo == "b"` em `build_server`. Catálogo e formato iguais não comprovam veracidade.

## Sandboxing como possibilidade

Sandboxing pode limitar o acesso de um processo a arquivos, rede e outros recursos. Docker é uma possibilidade para executar servidores em containers, com permissões adequadas ao caso. A aula cita essa opção e sua documentação, sem instalação, build ou demonstração prática. Uma venv separa dependências, mas não restringe disco ou rede.

Isolamento não comprova a veracidade dos dados retornados, não protege informações enviadas voluntariamente pelo host e não restringe sozinho outras ferramentas desse host. Os servidores A/B ilustram por que um resultado pode ter formato válido e conteúdo falso. [Docker MCP Catalog e Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/)

