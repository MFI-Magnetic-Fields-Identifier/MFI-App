# MFI — Seleção e identificação de motores

A tela usa o catálogo JSON em `src/profiles.json`. Os perfis monofásico e trifásico contêm valores ilustrativos de frequência, fases e polos.

## Executar no Windows PowerShell

A partir da raiz do repositório, use Node.js 20.19 ou superior na série 20, ou Node.js 22.12 ou superior:

```powershell
Set-Location .\apps\web
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
```

Abra a URL local mostrada pelo Vite. Com a API Python desligada, alterne entre os perfis. O cartão de detalhes deve atualizar de 1 fase e 4 polos para 3 fases e 6 polos. Também é possível selecionar com Tab e as setas do teclado.

## Verificar a compilação

Na pasta `apps/web`, execute:

```powershell
npm.cmd run build
```

Esse comando verifica os tipos TypeScript e gera a versão estática em `dist/`.

## Identificar pela câmera ou por foto

Em outro PowerShell, na raiz do repositório, inicie a API. O exemplo usa o checkpoint sintético gerado na etapa 4.1:

```powershell
Set-Location .\ComputerVisionPython
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:MFI_CHECKPOINT = (Resolve-Path .\models\demo-v1\best.pt).Path
.\.venv\Scripts\python.exe -m uvicorn mfi_cv.api:app --host 127.0.0.1 --port 8000
```

No frontend, clique em **Abrir câmera**, enquadre o motor e clique em **Capturar imagem**; então clique em **Analisar motor**. Também é possível escolher um JPEG, PNG ou WebP de até 8 MiB. A captura é reduzida para no máximo 1920 pixels no maior lado e enviada como JPEG. A API recebe uma imagem estática por chamada: não há classificação contínua de vídeo.

Após a previsão, a interface consulta `GET /motors/{model_id}` para buscar fabricante e especificações do melhor candidato, quando o status não é `unknown`. Em `needs_confirmation`, o item é exibido como candidato para revisão, não como identificação confirmada. A tela informa que a API atual não retorna medição de campo em teslas nem dados para simular o campo magnético.

Para verificar a integração com dados sintéticos, capture ou escolha uma imagem de `ComputerVisionPython/dataset/raw/`. A tela deve mostrar o estado da identificação, candidatos `demo-*` e, se o catálogo tiver o ID candidato, seus dados técnicos. Para verificar indisponibilidade, pare a API e envie novamente. A seleção manual deve continuar funcionando.

O Vite encaminha `/predict`, `/motors` e `/health` para `http://127.0.0.1:8000` em desenvolvimento. Se a API estiver em outro endereço, defina `$env:MFI_API_TARGET` antes de iniciar o Vite. Ao servir `dist/` em produção, configure esses caminhos como proxy para a API na mesma origem. A câmera precisa de HTTPS em dispositivos móveis (localhost é permitido no próprio computador).
