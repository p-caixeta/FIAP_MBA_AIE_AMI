# Agents, Multi-Agents & Interoperability

This repository contains the source code, exercises, and practical examples developed for the **Agents, Multi-Agents & Interoperability** class, part of the [MBA in AI Engineering](https://www.fiap.com.br/mba/mba-em-ai-engineering-multi-agents/) program at FIAP.

## About the Course
The module explores the fundamentals of autonomous agents, multi-agent systems, and how to build interoperable AI solutions capable of collaborating to solve complex problems. 

## Author
**Paulo Oliveira**   profpaulo.oliveira@fiap.com.br
##### [LinkedIn](https://www.linkedin.com/in/pc-oliveira/) 
 

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

## Executar uma aula

Na raiz, com o ambiente ativado:

| Aula | Comando | Endereço |
|---|---|---|
| 03 · RAG | `python Aula_03/app.py` | http://127.0.0.1:5000 |
| 04 · Memória | `python Aula_04/app.py` | http://127.0.0.1:5001 |
| 05 · MCP | `python Aula_05/app.py` | http://127.0.0.1:5002 |

Aula 05 oferece diagnóstico MCP sem chave de modelo. Confira [as instruções](Aula_05/README.md).
Cada aula conserva seus próprios dados e runtime; somente o ambiente Python e
a configuração são compartilhados. Não há instalação no Python global da máquina.

