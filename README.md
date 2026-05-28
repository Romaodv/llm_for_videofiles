# Local Knowledge Explorer

MVP local-first para transcrever vídeos com Whisper, gerar SRT com timestamps, indexar chunks em SQLite e consultar via RAG com fontes clicáveis.

## O que existe agora

- Seleção manual de vídeo pelos arquivos locais.
- Botão explícito de indexação/reindexação.
- Transcrição local com `faster-whisper` ou via Groq `whisper-large-v3-turbo`.
- SRT salvo em `.local_data/transcripts/`.
- SQLite local em `.local_data/app.sqlite3`.
- Embeddings locais por hashing, sem custo e sem rede.
- Retrieve local top-k por cosine similarity dentro do backend.
- Chat Cloud via DeepSeek ou Groq Llama 4 Scout com memória curta da sessão.
- Fontes com nome do arquivo, timestamps e salto direto para o trecho do vídeo.
- Tópicos navegáveis gerados via DeepSeek ou Groq quando a API key estiver configurada.
- Biblioteca persistente: vídeos indexados ficam salvos no SQLite com embeddings, SRT, chunks, tópicos, categoria e notas.
- Barra lateral agrupada por categoria para reabrir vídeos sem transcrever/indexar novamente.
- Painel de progresso em tempo real para indexação: validação, hash, Whisper/Groq, SRT, chunking, embeddings, SQLite e tópicos iniciais.
- Conversão opcional para MP4 H.264/AAC quando o navegador toca áudio mas não mostra imagem do vídeo.
- Resumo geral da apresentação em Markdown via DeepSeek, com links de tempo para pular no vídeo.
- Busca textual básica no SRT carregado, com salto para o timestamp encontrado.


## Portable launcher

Para rodar o app com uma tela de inicialização local:

```bash
./start.sh
```

No Windows, use:

```bat
start.bat
```

Isso abre uma landing em `localhost`. Ao clicar em `Start app`, o launcher:

- cria/usa um virtualenv local em `.venv` para evitar o bloqueio PEP 668 do Python do sistema;
- instala dependências Python do projeto dentro desse virtualenv;
- garante que o frontend está buildado;
- inicia o backend FastAPI;
- abre o app em `http://127.0.0.1:8000`.

Observação: em Ubuntu/Debian, se a criação do virtualenv falhar, instale `python3-venv`: `sudo apt install python3-venv`.

### Gerar pacote portátil

Em uma máquina de build com Node/NPM disponível:

```bash
python scripts/build_portable.py
```

O pacote sai em:

```text
dist/llm-forfiles-portable
```

Essa pasta inclui o backend, frontend buildado, landing launcher e scripts `start.sh`/`start.bat`. Ela não inclui `node_modules`, `.local_data` nem vídeos indexados. Na primeira execução no outro PC, o launcher prepara dependências e inicia o app.

## Desktop Electron

Agora o projeto também pode rodar como app desktop standalone em Electron, sem abrir navegador nem usar a landing page do launcher.

Instalador Windows mais recente:

- [Download via Mega](https://mega.nz/file/grYTGarZ#nZS5Nh3C7Wc8XbLnyPyNHlFsFZqxSezQPEUk1g8nfYA)

### Como funciona

- O frontend React é carregado dentro de uma janela Electron.
- O backend FastAPI sobe em segundo plano, com porta local aleatória, sem expor uma página inicial no navegador.
- Na primeira abertura, o app cria um virtualenv próprio em `userData/python-runtime`, instala as dependências Python e depois reutiliza esse ambiente nas próximas execuções.
- Os dados persistentes continuam indo para a pasta de dados do app (`userData/data`), separada do código.

### Desenvolvimento

Instale as dependências do Electron e do frontend:

```bash
npm install
npm --prefix frontend install
```

Build do frontend + abertura do app Electron:

```bash
npm run desktop:dev
```

Se quiser forçar um Python específico em desenvolvimento:

```bash
LLM_FORFILES_PYTHON_BIN=/caminho/para/python3 npm run desktop:dev
```

### Gerar pacote desktop

Antes do build empacotado, coloque uma distribuição Python completa com `venv` e `pip` em:

```text
vendor/python
```

Exemplos esperados:

- Linux: `vendor/python/bin/python3`
- Windows: `vendor/python/python.exe`

Se quiser montar um bundle local rapidamente a partir do Python atual da máquina:

```bash
python3 scripts/build_python_bundle.py
```

Isso cria um runtime em `vendor/python` usando `venv --copies`, suficiente para o Electron incluir um Python próprio no pacote.

Depois gere o pacote:

```bash
npm run desktop:dist
```

Saídas esperadas do `electron-builder`:

- Windows: instalador `NSIS`
- Linux: pacote `AppImage`

Observação importante: para o instalador funcionar em outra máquina sem Python preinstalado, o `vendor/python` precisa ser preenchido antes do build. Em modo de desenvolvimento, o app pode usar o Python local do sistema.

## Backend

Instale dependências:

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

Embeddings usam hashing local sem modelo externo. Chat, tópicos e resumo geral podem usar DeepSeek ou Groq, escolhidos no botão `Config` da UI:

```bash
DEEPSEEK_API_KEY=...
DEEPSEEK_MODEL=deepseek-v4-flash
```

Whisper:

```bash
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_CPU_THREADS=2  # padrão conservador; use 0 para automático ou 4, 8... para fixar mais threads
```

Groq:

```bash
GROQ_API_KEY=...
GROQ_WHISPER_MODEL=whisper-large-v3-turbo
GROQ_LLM_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
# Para SRT grande no free tier, também teste:
# GROQ_LLM_MODEL=groq/compound-mini
GROQ_TRANSCRIPTION_LANGUAGE=pt  # opcional
```

Observação: `faster-whisper` baixa o modelo na primeira transcrição e precisa de acesso ao cache/modelo do Hugging Face. A transcrição via Groq usa `ffmpeg` para extrair MP3 mono 16 kHz, manter cada upload abaixo de 25 MB e gerar o mesmo SRT com timestamps. O processamento de vídeo também depende de suporte de mídia/ffmpeg via PyAV.

## Fluxo

1. Abra a UI.
2. Navegue até um vídeo local ou cole o caminho absoluto.
3. Informe uma categoria, escolha `Local` ou `Groq` em `Transcrição`, ajuste `Threads Whisper` se estiver usando local, e clique em Indexar.
4. A aplicação mostra progresso detalhado enquanto transcreve, salva SRT, cria chunks, calcula embeddings e grava tudo no SQLite.
5. Use Salvar para alterar categoria/notas sem reprocessar o vídeo.
6. Reabra qualquer vídeo pela barra lateral categorizada; os dados salvos são reaproveitados.
7. Se o vídeo tocar apenas áudio, clique em `MP4` ou `Gerar MP4 H.264` para criar uma cópia web em `.local_data/web_videos/`.
8. Use tópicos, resumo em Markdown, SRT ou respostas do chat para pular para o trecho do vídeo.

## Chat Cloud

A UI usa apenas o modo Cloud no chat, com DeepSeek. A memória curta não é persistida no banco; a UI envia somente as últimas mensagens da sessão atual junto da pergunta.

A DeepSeek API key e a Groq API key podem ser informadas no botão `Config` no topo esquerdo da UI. Ali também dá para escolher qual provider de IA usar para chat, tópicos e resumo. Quando salvas, o backend grava os segredos criptografados em `.local_data/secrets.json` usando uma chave Fernet em `.local_data/secret.key`, ambos com permissão de dono quando o sistema permite. A UI mostra apenas o status e a chave mascarada, nunca a chave completa. Também há botão para apagar cada chave salva.

Observação de segurança: isso protege contra gravação em texto puro, mas quem tiver acesso aos dois arquivos locais (`secrets.json` e `secret.key`) consegue descriptografar. Para segurança mais forte, use `DEEPSEEK_API_KEY` via variável de ambiente ou um keyring do sistema operacional.

Para usar DeepSeek via variável de ambiente:

```bash
DEEPSEEK_API_KEY=... python -m uvicorn backend.app.main:app --reload
```

Os tópicos tentam enviar o transcript compacto inteiro primeiro, preservando a visão global da reunião. Se o provider recusar por contexto/limite, o backend cai para blocos por tempo.
