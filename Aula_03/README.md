# Aula 03 · Agentes e RAG

Aplicação local de chat com traces, RAG e o baseline fan-out da Aula 02. Os dados são sintéticos: o sistema consulta e propõe, mas não executa ações de negócio.

Requer Python 3.11/3.12, CPU, rede e uma chave de modelo compatível. Antes de criar o ambiente, confirme com `python --version` que o comando aponta para uma dessas versões.

winget install -e --id Python.Python.3.12

```powershell
git clone https://github.com/p-caixeta/FIAP_MBA_AIE_AMI.git
cd Aula_03_new
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Abra .env, informe OPENAI_API_KEY e salve.
python app.py
```

Abra http://127.0.0.1:5000. Se a ativação for bloqueada, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` e `.\.venv\Scripts\python.exe app.py`.

Se o traceback apontar para outro Python (por exemplo `Python310\Lib\site-packages`) ou informar que o Python-base não existe, o `.venv` foi criado com um interpretador antigo/removido. Instale Python 3.11 ou 3.12, apague somente a pasta `.venv`, recrie-a e instale os requisitos novamente. Não reutilize esse ambiente: pacotes globais antigos, inclusive `aiohttp`, podem conflitar com o SDK.

| Etapa | O que muda | Arquivo editável |
|---|---|---|
| Baseline | Fan-out Aula 02 e síntese Python | `graph.py`, `agents.py` |
| RAG fixo | Uma busca antes da síntese LLM | `retrieval.py`, `agents.py` |
| RAG como ferramenta | A síntese decide se busca | `agents.py`, `graph.py` |

Salve um arquivo Python, aguarde o reload, use **Verificar código** e **Repetir pergunta**. Alterações em `.env` ou nos dados exigem reiniciar o servidor. F5 limpa a conversa na página.

Os notebooks independentes ficam em `notebooks/301_grafo_e_rag_fixo.ipynb` e `notebooks/302_rag_como_ferramenta.ipynb`; eles não se conectam a este Flask e cada aluno trabalha em sua cópia.

Problemas comuns: confira chave/modelo para 401/403/404; instale requisitos no venv correto; se a porta 5000 estiver ocupada, encerre o servidor anterior ou altere `PORT` em `config.py`; se o reload ocorrer durante uma execução, reenvie a pergunta manualmente.

Limites: conversa e runs só existem na memória da página; dados e propostas são sintéticos. Consulte `VALIDACAO.md` antes de usar em aula.
