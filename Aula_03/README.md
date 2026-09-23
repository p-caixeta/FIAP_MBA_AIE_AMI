# Aula 03 · Agentes e RAG

## Plano de aula:
Aplicação local de chat com traces, RAG e o baseline fan-out da Aula 02. Os dados são sintéticos: o sistema consulta e propõe, mas não executa ações de negócio.

## Instalação
Requer Python 3.11/3.12, CPU, rede e uma chave de modelo compatível. Antes de criar o ambiente, confirme com `python --version` que o comando aponta para uma dessas versões.

```powershell
git clone https://github.com/p-caixeta/FIAP_MBA_AIE_AMI.git
cd Aula_03_new
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# caso esteja no cmd:
# copy .env.example .env

# Abra .env, informe OPENAI_API_KEY e salve.
python app.py
```

Abra http://127.0.0.1:5000. Se a ativação for bloqueada, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` e `.\.venv\Scripts\python.exe app.py`.


| Etapa | O que muda | Arquivo editável |
|---|---|---|
| Baseline | Fan-out Aula 02 e síntese Python | `graph.py`, `agents.py` |
| RAG fixo | Uma busca antes da síntese LLM | `retrieval.py`, `agents.py` |
| RAG como ferramenta | A síntese decide se busca | `agents.py`, `graph.py` |

## Como executar os exercícios e ver as mudanças ao vivo
Salve um arquivo Python, aguarde o reload, use **Verificar código** e **Repetir pergunta**. Alterações em `.env` ou nos dados exigem reiniciar o servidor. F5 limpa a conversa na página.

## Caso não consiga construir o servidor
Os notebooks independentes ficam em `notebooks/301_grafo_e_rag_fixo.ipynb` e `notebooks/302_rag_como_ferramenta.ipynb`; eles não se conectam a este Flask e cada aluno trabalha em sua cópia.
### Também há acesso direto pelo Colab: 
[Notebook 1](https://drive.google.com/file/d/1JreRztXbyxWkZbx6kLSf2AqIPF-PdA4t/view?usp=sharing) [Notebook 2](https://drive.google.com/file/d/1qlCQNaEIY42ED0NsraKgBbm_DkSQwowg/view?usp=sharing)

## Problemas comuns: 
confira chave/modelo para 401/403/404; instale requisitos no venv correto; se a porta 5000 estiver ocupada, encerre o servidor anterior ou altere `PORT` em `config.py`; se o reload ocorrer durante uma execução, reenvie a pergunta manualmente. 

Se o traceback apontar para outro Python (por exemplo `Python310\Lib\site-packages`) ou informar que o Python-base não existe, o `.venv` foi criado com um interpretador antigo/removido. Instale Python 3.11 ou 3.12 ( winget install -e --id Python.Python.3.12), apague somente a pasta `.venv`, recrie-a e instale os requisitos novamente.
## Limites: 
conversa e runs só existem na memória da página; dados e propostas são sintéticos.
