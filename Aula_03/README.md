# Aula 03 · Agentes e RAG

## Plano de aula:
Aplicação local de chat com traces, RAG e o baseline fan-out da Aula 02. Os dados são sintéticos: o sistema consulta e propõe, mas não executa ações de negócio.

## Ambiente compartilhado

Python 3.11/3.12. Execute uma vez na **raiz do repositório**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Edite .env na raiz com sua chave; não sobrescreva um .env já configurado.
```

Todas as aulas usam o mesmo `requirements.txt`, `.venv` e `.env` da raiz.
Variáveis já definidas no processo prevalecem; `.env` antigo de uma aula serve
apenas de fallback para valores ausentes. Não é preciso copiar chaves entre aulas.
Se a ativação for bloqueada, use `.\.venv\Scripts\python.exe` no lugar de `python`.
No VS Code, selecione o interpretador `.venv/Scripts/python.exe` da raiz.

Para iniciar a partir da raiz:

```powershell
python Aula_03/app.py
```

Abra http://127.0.0.1:5000. Salvar Python recarrega o app; alterações no `.env`
ou nos dados exigem reinício. Os notebooks Colab continuam independentes e
instalam o mesmo conjunto de versões em seu próprio runtime.

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

Se o Python-base do venv deixou de existir, recrie o `.venv` da raiz com Python 3.11/3.12 instalado.

## Limites: 
conversa e runs só existem na memória da página; dados e propostas são sintéticos.
