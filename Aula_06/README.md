# Aula 06 · Raciocínio multimodal e revisão humana

Analise imagens e quadros de vídeo do caso **P600/E600**, revise a proposta do agente
e aprove, rejeite ou peça mais evidências antes da abertura de um chamado.

## Executar o app

Na raiz do repositório, crie o ambiente compartilhado, se necessário, e instale as dependências:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe Aula_06/app.py
```

Abra **http://127.0.0.1:5003**.

- **Análise fornecida**: usa exemplos fixos, sem chave de API. Escolha evidência suficiente, insuficiente ou conflito.
- **LMM real**: configure `OPENAI_API_KEY` no `.env` da raiz. O modelo usa `OPENAI_MODEL` ou, se definido, `OPENAI_VISION_MODEL`. Texto, imagens e quadros selecionados são enviados ao provedor; áudio não é processado.

## Exercícios

- [601 · Evidências multimodais](notebooks/601_evidencias_multimodais.ipynb): exercícios 1.1–1.3.
- [602 · Decisão e revisão humana](notebooks/602_decisao_e_revisao_humana.ipynb): exercícios 2.1–3.2.

Os notebooks incluem o código e as mídias necessários e podem ser usados no Colab.
No VS Code, selecione o kernel da `.venv`. Execute as células em ordem; após alterar
um módulo, execute sua célula e **Carregar módulos** novamente. Use kernels separados
para notebooks de aulas diferentes.

`RUN_LIVE=False` usa as análises fornecidas. Altere para `True` nas comparações com LMM;
o notebook solicitará a chave de API quando necessário.

| Exercício | Função no app |
|---|---|
| 1.1 · Relato e imagem | `media.build_multimodal_input` |
| 1.2 · Observação e lacuna | `reasoning.analyze_evidence` |
| 1.3 · Entre os quadros | `media.sample_frames` |
| 2.1 · Fontes discordam | `reasoning.propose_action` |
| 2.2 · Quando parar | `review.route_proposal` |
| 2.3 · O que aprovar | `review.review_payload` |
| 3.1 · Decisão humana | `workflow.human_review` / `review.validate_decision` |
| 3.2 · Reinício e repetição | `workflow.resume_case` / `store.Store.execute_approved` |

## Usar a interface

1. Escolha mídias do kit ou envie arquivos e clique **Analisar e preparar proposta**.
2. Confira observações, lacunas, ação e argumentos nos passos do inspector.
3. Se editar o resumo, clique **Salvar revisão** antes de aprovar a nova versão.
4. Experimente **Aprovar esta versão**, **Rejeitar** e **Pedir evidência** em casos separados.
5. Para continuar um caso que precisa de evidência, anexe o material e marque a continuação.
6. Para retomar após reiniciar o app, use **Recuperar caso**.

A aprovação vale para uma proposta e versão. Não apague `runtime/` se quiser retomar
os casos: ali ficam os bancos locais, uploads e quadros utilizados.

O kit contém ilustrações e vídeos sintéticos, sob CC0-1.0. A aplicação aceita até quatro
arquivos de 10 MB cada, imagens de até 8 megapixels e vídeos de até 15 segundos.
Selecione de dois a oito quadros por vídeo, com limite de 12 imagens/quadros por análise.

## Slides e referências

- [Slides da aula](https://docs.google.com/presentation/d/1KEcdIAG67Hs3rXKxgJ9QxDtiXpUIwMbOBdOlJzJ_tuM/edit)
- [OpenAI · imagens e visão](https://developers.openai.com/api/docs/guides/images-vision)
- [OpenAI · saída estruturada](https://developers.openai.com/api/docs/guides/structured-outputs)
- [LangGraph · interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [LangGraph · persistência](https://docs.langchain.com/oss/python/langgraph/persistence)
