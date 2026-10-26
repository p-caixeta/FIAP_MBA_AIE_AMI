# Aula 07 · Uma aplicação, novas capacidades

Construa um planejador de workshops e observe o efeito de cada mudança no código.

Na raiz do repositório, use a mesma `.venv`, `.env` e `requirements.txt` das outras aulas:

```powershell
.\.venv\Scripts\python.exe Aula_07/app.py
```

Abra **http://127.0.0.1:5004**. Configure `OPENAI_API_KEY` e `OPENAI_MODEL` no `.env` da raiz. A etapa de imagem usa `OPENAI_VISION_MODEL`, quando informado, ou o modelo principal, que precisa aceitar imagens. As chamadas são reais e usam a conta configurada.

## Editar → salvar → executar → comparar

Comece em `lesson.py`. A configuração inicial é um agente, sem ferramentas ou memória. Altere uma capacidade, salve e aguarde o aviso **Código atualizado**. Clique **Executar novamente**: o servidor local recarrega o Python e o navegador conserva o resultado anterior. Esse ciclo de desenvolvimento local dispensa um deploy por edição.

| Conceito | Edição em `lesson.py` | Efeito a inspecionar |
|---|---|---|
| Ferramenta local | `LOCAL_TOOLS = [consultar_espaco]`, ao final do arquivo | Consulta aos preços-base fictícios |
| RAG obrigatório | `RAG_MODE = "fixed"` | Busca antes do agente; condição educacional D1 |
| RAG como ferramenta | `RAG_MODE = "tool"` | Agente escolhe se busca; veja a chamada na atividade |
| Memória | `USE_MEMORY = True` | Continuação da conversa e uma preferência salva |
| Subagente | `ARCHITECTURE = "subagent"` | Planejador delega uma revisão financeira |
| Equipe | `ARCHITECTURE = "team"` | Programa e orçamento em paralelo, depois síntese |
| MCP | Preencher `MCP_SERVERS` | Descoberta real de ferramentas e chamadas ao servidor |
| A2A | Preencher `A2A_AGENTS` | Tarefa enviada ao redator externo |
| Imagem | `USE_IMAGE = True` e selecionar uma imagem | Bytes visuais enviados ao modelo; interpretação inspecionável |
| HITL | `HUMAN_REVIEW = True` | Pausa, edição, aprovação ou rejeição antes da escrita |

**Repetir o mesmo pedido** reutiliza o contexto inicial da execução anterior. **Alterar o pedido** cria um novo turno. Para experimentar memória, faça uma pergunta de continuação, como “Adapte para um público mais técnico”. **Nova conversa** muda a sessão; a preferência persistente continua disponível enquanto não for esquecida. O perfil é único nesta demonstração local.

## MCP e A2A existentes

Os clientes estão prontos para conectar serviços disponíveis. Esta aula não cria nem altera esses servidores.

Para MCP HTTP, informe a URL completa em `AULA07_MCP_URL` no `.env` e registre:

```python
MCP_SERVERS = {"math": {"url": os.getenv("AULA07_MCP_URL", "")}}
```

Também é possível usar o comando de inicialização **já existente** de um servidor stdio:

```python
MCP_SERVERS = {"math": {"command": "python", "args": ["caminho/servidor.py"]}}
```

Troque o caminho e o comando pelos reais. O cliente inicia e encerra o subprocesso; para HTTP, o servidor precisa estar rodando separadamente. Novos servidores MCP entram como novos itens no mesmo dicionário. As ferramentas e seus schemas vêm da descoberta, sem funções-ponte escritas uma a uma.

Para o servidor A2A fornecido, informe o endpoint completo em `AULA07_A2A_URL` e registre:

```python
A2A_AGENTS = {
    "redator": {"url": os.getenv("AULA07_A2A_URL", ""),
                "description": "Autor de artigos em até dois parágrafos."}
}
```

O cliente mantém o contrato `message/send`, `message.text` e `message.type` do notebook. Esse exemplo é uma integração didática com formato simplificado; não é uma implementação completa da especificação A2A.

O notebook fornecido não publica um Agent Card. Por isso, a interface identifica o redator como **Cadastro local · formato do notebook**. Se um servidor já publicar um card, acrescente `card_url` ao cadastro para buscá-lo e inspecioná-lo. Registrar uma descrição local não equivale a descobrir capacidades remotamente, e o endereço de chamada continua sendo o `url` configurado.

**Preparação externa pendente:** o notebook MathServer deixa `mcp.run()` comentado; o notebook A2A inicia por Colab/ngrok. Os materiais fornecidos não trazem um procedimento completo para iniciá-los localmente. Obtenha o comando ou endpoint funcional antes dessas etapas. Deixe os dois dicionários vazios enquanto os serviços não estiverem disponíveis; conectar um serviço indisponível produz um erro visível.

Reinicie o app depois de editar `.env`. Durante a aula, conecte os servidores prontos alterando apenas `lesson.py`.

## Evidências e efeito local

O painel **Atividade** mostra os passos efetivamente executados. Abra uma entrada para conferir os argumentos e o retorno. **Fontes**, **Memória** e **Capacidades** mostram documentos recuperados, contexto selecionado e catálogos da última execução. Um servidor configurado pode oferecer ferramentas que o agente não chamou.

Os documentos em `dados/regras` e os preços são fictícios. D1 permite locação de R$ 900 para 20–40 participantes; para 30 pessoas, locação + materiais + instrutor somam R$ 2.700. A escolha de fontes e ferramentas pela LLM deve ser conferida na execução. A imagem `dados/sala.png` é sintética, gerada para esta aula, com mesas em fileiras; não contém pessoas ou dados privados.

Aprovar salva um plano em `runtime/approved/`. Rejeitar não escreve o plano. Editar cria uma nova revisão e exige nova aprovação. A pausa fica em SQLite e pode ser recuperada após o reload, na mesma aba/navegador. Fechar a aba durante uma execução em andamento pode interrompê-la; aguarde o resultado antes de editar o código.

## Onde está cada parte

- `lesson.py`: configurações da aula, ferramenta local, RAG, prompt e formato da proposta.
- `workflow.py`: agentes, delegação, equipe paralela, imagem e pausa humana.
- `integrations.py`: clientes MCP e A2A, sem implementação dos servidores.
- `memory.py`: conversa recente e preferência em SQLite.
- `app.py`, `templates/`, `static/`: servidor local e interface.

Comentários indicam onde ampliar APIs, retrieval, seleção de ferramentas, autenticação, persistência e execução de ações. O exemplo é uma aplicação local de ensino. Preparação do professor, testes, dependências de verificação e arquivos gerados ficam ignorados pelo Git.
