# Local Knowledge Explorer

MVP local-first para transcrever videos com Whisper, gerar SRT com timestamps, indexar chunks em SQLite e consultar via RAG com fontes clicaveis.

## O que existe agora

- Selecao manual de video pelos arquivos locais.
- Botao explicito de indexacao/reindexacao.
- Transcricao local com `faster-whisper` ou via Groq `whisper-large-v3-turbo`.
- SRT salvo em `.local_data/transcripts/`.
- SQLite local em `.local_data/app.sqlite3`.
- Embeddings locais por hashing, sem custo e sem rede.
- Retrieve local top-k por cosine similarity dentro do backend.
- Chat Cloud via DeepSeek ou Groq Llama 4 Scout com memoria curta da sessao.
- Fontes com nome do arquivo, timestamps e salto direto para o trecho do video.
- Topicos navegaveis gerados via DeepSeek ou Groq quando a API key estiver configurada.
- Biblioteca persistente: videos indexados ficam salvos no SQLite com embeddings, SRT, chunks, topicos, categoria e notas.
- Barra lateral agrupada por categoria para reabrir videos sem transcrever/indexar novamente.
- Painel de progresso em tempo real para indexacao: validacao, hash, Whisper/Groq, SRT, chunking, embeddings, SQLite e topicos iniciais.
- Conversao opcional para MP4 H.264/AAC quando o navegador toca audio mas nao mostra imagem do video.
- Resumo geral da apresentacao em Markdown via DeepSeek, com links de tempo para pular no video.
- Busca textual basica no SRT carregado, com salto para o timestamp encontrado.


## Portable launcher

Para rodar o app com uma tela de inicializacao local:

```bash
./start.sh
```

No Windows, use:

```bat
start.bat
```

Isso abre uma landing em `localhost`. Ao clicar em `Start app`, o launcher:

- cria/usa um virtualenv local em `.venv` para evitar o bloqueio PEP 668 do Python do sistema;
- instala dependencias Python do projeto dentro desse virtualenv;
- garante que o frontend esta buildado;
- inicia o backend FastAPI;
- abre o app em `http://127.0.0.1:8000`.

Observacao: em Ubuntu/Debian, se a criacao do virtualenv falhar, instale `python3-venv`: `sudo apt install python3-venv`.

### Gerar pacote portatil

Em uma maquina de build com Node/NPM disponivel:

```bash
python scripts/build_portable.py
```

O pacote sai em:

```text
dist/llm-forfiles-portable
```

Essa pasta inclui o backend, frontend buildado, landing launcher e scripts `start.sh`/`start.bat`. Ela nao inclui `node_modules`, `.local_data` nem videos indexados. Na primeira execucao no outro PC, o launcher prepara dependencias e inicia o app.

## Desktop Electron

Agora o projeto tambem pode rodar como app desktop standalone em Electron, sem abrir navegador nem usar a landing page do launcher.

### Como funciona

- O frontend React e carregado dentro de uma janela Electron.
- O backend FastAPI sobe em segundo plano, com porta local aleatoria, sem expor uma pagina inicial no navegador.
- Na primeira abertura, o app cria um virtualenv proprio em `userData/python-runtime`, instala as dependencias Python e depois reutiliza esse ambiente nas proximas execucoes.
- Os dados persistentes continuam indo para a pasta de dados do app (`userData/data`), separada do codigo.

### Desenvolvimento

Instale as dependencias do Electron e do frontend:

```bash
npm install
npm --prefix frontend install
```

Build do frontend + abertura do app Electron:

```bash
npm run desktop:dev
```

Se quiser forcar um Python especifico em desenvolvimento:

```bash
LLM_FORFILES_PYTHON_BIN=/caminho/para/python3 npm run desktop:dev
```

### Gerar pacote desktop

Antes do build empacotado, coloque uma distribuicao Python completa com `venv` e `pip` em:

```text
vendor/python
```

Exemplos esperados:

- Linux: `vendor/python/bin/python3`
- Windows: `vendor/python/python.exe`

Se quiser montar um bundle local rapidamente a partir do Python atual da maquina:

```bash
python3 scripts/build_python_bundle.py
```

Isso cria um runtime em `vendor/python` usando `venv --copies`, suficiente para o Electron incluir um Python proprio no pacote.

Depois gere o pacote:

```bash
npm run desktop:dist
```

Saidas esperadas do `electron-builder`:

- Windows: instalador `NSIS`
- Linux: pacote `AppImage`

Observacao importante: para o instalador funcionar em outra maquina sem Python preinstalado, o `vendor/python` precisa ser preenchido antes do build. Em modo de desenvolvimento, o app pode usar o Python local do sistema.

## Backend

Instale dependencias:

```bash
python -m pip install -e .
```

Inicie a API:

```bash
python -m uvicorn backend.app.main:app --reload
```

Healthcheck:

```text
GET http://127.0.0.1:8000/health
```

Endpoints principais:

- `GET /files/list?path=...`
- `POST /videos/index`
- `POST /videos/index/jobs`
- `GET /jobs/{job_id}`
- `GET /documents`
- `GET /documents/{id}/transcript`
- `PUT /documents/{id}/save`
- `GET /documents/{id}/topics`
- `GET /documents/{id}/media`
- `POST /documents/{id}/media/jobs`
- `POST /documents/{id}/topics/summarize`
- `POST /documents/{id}/summary`
- `POST /search/semantic`
- `POST /search/ask`
- `GET /settings/secrets/deepseek`
- `POST /settings/secrets/deepseek`
- `DELETE /settings/secrets/deepseek`
- `GET /settings/secrets/groq`
- `POST /settings/secrets/groq`
- `DELETE /settings/secrets/groq`
- `GET /media?path=...`

## Frontend

O frontend fica em `frontend/`.

```bash
cd frontend
npm install
npm run dev
```

Se precisar apontar para outra API:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
```

## Providers

Embeddings usam hashing local sem modelo externo. Chat, topicos e resumo geral podem usar DeepSeek ou Groq, escolhidos no botao `Config` da UI:

```bash
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
```

Whisper:

```bash
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_CPU_THREADS=2  # padrao conservador; use 0 para automatico ou 4, 8... para fixar mais threads
```

Groq:

```bash
GROQ_API_KEY=...
GROQ_WHISPER_MODEL=whisper-large-v3-turbo
GROQ_LLM_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
# Para SRT grande no free tier, tambem teste:
# GROQ_LLM_MODEL=groq/compound-mini
GROQ_TRANSCRIPTION_LANGUAGE=pt  # opcional
```

Observacao: `faster-whisper` baixa o modelo na primeira transcricao e precisa de acesso ao cache/modelo do Hugging Face. A transcricao via Groq usa `ffmpeg` para extrair MP3 mono 16 kHz, manter cada upload abaixo de 25 MB e gerar o mesmo SRT com timestamps. O processamento de video tambem depende de suporte de media/ffmpeg via PyAV.

## Fluxo

1. Abra a UI.
2. Navegue ate um video local ou cole o caminho absoluto.
3. Informe uma categoria, escolha `Local` ou `Groq` em `Transcricao`, ajuste `Threads Whisper` se estiver usando local, e clique em Indexar.
4. A aplicacao mostra progresso detalhado enquanto transcreve, salva SRT, cria chunks, calcula embeddings e grava tudo no SQLite.
5. Use Salvar para alterar categoria/notas sem reprocessar o video.
6. Reabra qualquer video pela barra lateral categorizada; os dados salvos sao reaproveitados.
7. Se o video tocar apenas audio, clique em `MP4` ou `Gerar MP4 H.264` para criar uma copia web em `.local_data/web_videos/`.
8. Use topicos, resumo em Markdown, SRT ou respostas do chat para pular para o trecho do video.

## Chat Cloud

A UI usa apenas o modo Cloud no chat, com DeepSeek. A memoria curta nao e persistida no banco; a UI envia somente as ultimas mensagens da sessao atual junto da pergunta.

A DeepSeek API key e a Groq API key podem ser informadas no botao `Config` no topo esquerdo da UI. Ali tambem da para escolher qual provider de IA usar para chat, topicos e resumo. Quando salvas, o backend grava os segredos criptografados em `.local_data/secrets.json` usando uma chave Fernet em `.local_data/secret.key`, ambos com permissao de dono quando o sistema permite. A UI mostra apenas o status e a chave mascarada, nunca a chave completa. Tambem ha botao para apagar cada chave salva.

Observacao de seguranca: isso protege contra gravacao em texto puro, mas quem tiver acesso aos dois arquivos locais (`secrets.json` e `secret.key`) consegue descriptografar. Para seguranca mais forte, use `DEEPSEEK_API_KEY` via variavel de ambiente ou um keyring do sistema operacional.

Para usar DeepSeek via variavel de ambiente:

```bash
DEEPSEEK_API_KEY=... python -m uvicorn backend.app.main:app --reload
```

Os topicos tentam enviar o transcript compacto inteiro primeiro, preservando a visao global da reuniao. Se o provider recusar por contexto/limite, o backend cai para blocos por tempo.
