# MFI — Visão computacional

O comando inicial verifica se o pacote `mfi_cv` foi instalado e pode ser executado.

## Configuração no Windows PowerShell

Use Python 3.11 ou superior com `venv` e `pip`. A partir da raiz do repositório:

```powershell
Set-Location .\ComputerVisionPython
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
```

O comando instala o pacote em modo editável e inclui o pytest. Os comandos abaixo usam diretamente o Python do ambiente virtual, sem precisar ativá-lo.

## Execução e testes

Na pasta `ComputerVisionPython`, execute:

```powershell
.\.venv\Scripts\python.exe -m mfi_cv
.\.venv\Scripts\python.exe -m mfi_cv --help
.\.venv\Scripts\python.exe -m pytest
```

O primeiro comando deve imprimir `MFI CV: ambiente Python pronto.` e o segundo deve mostrar a ajuda. Para verificar a rejeição de parâmetros desconhecidos, execute:

```powershell
.\.venv\Scripts\python.exe -m mfi_cv --invalido
$LASTEXITCODE
```

O comando deve indicar o argumento inválido e retornar o código `2`.

## Persistência local com SQLite

Na pasta `ComputerVisionPython`, instale as dependências e aplique a migração:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
Remove-Item Env:MFI_DATABASE_URL -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

O banco local fica em `mfi_cv.sqlite3`, ignorado pelo Git. Use estes dados fictícios para verificar o cadastro e a consulta em conexões separadas:

```powershell
@'
from uuid import uuid4
from mfi_cv.data import MotorModel
from mfi_cv.data.database import create_database_engine
from mfi_cv.data.repository import MotorRepository

model = MotorModel(f"demo-{uuid4()}", "Fabricante ficticio", "Linha ficticia",
                   "Modelo ficticio", "Fonte ficticia")
engine = create_database_engine()
with engine.begin() as connection:
    MotorRepository(connection).add_model(model)
with engine.connect() as connection:
    repository = MotorRepository(connection)
    print(repository.get_model(model.model_id))
    print(repository.get_model("id-ausente"))
engine.dispose()
'@ | .\.venv\Scripts\python.exe -
```

A consulta deve imprimir o modelo cadastrado e, para o ID ausente, `None`. Use `engine.begin()` para agrupar cadastros em uma transação. Um ID duplicado ou uma referência estrangeira ausente gera `sqlalchemy.exc.IntegrityError`. Trate essa exceção fora do bloco da transação para que o SQLAlchemy reverta os cadastros do bloco.

## PostgreSQL

Instale o driver opcional, configure `MFI_DATABASE_URL` no ambiente da sessão e aplique a mesma migração a um banco PostgreSQL existente, com permissão para criar tabelas. O valor abaixo usa apenas dados fictícios:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[postgres]'
$env:MFI_DATABASE_URL = 'postgresql+psycopg://usuario:senha@localhost:5432/mfi'
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Importação de fotografias

Na pasta `ComputerVisionPython`, instale o pacote atualizado e aplique a migração conforme a seção **Persistência local com SQLite**. A revisão atual deve ser `0002_image_import`.

O importador aceita imagens estáticas JPEG, PNG e WebP e identifica o formato pelo conteúdo. A foto original é copiada para `dataset/raw/<prefixo-do-hash>/<sha256>.<extensão>`. O caminho registrado é relativo a `dataset/raw`, ou à pasta passada em `storage_root`. Use a mesma pasta de armazenamento para as importações de um catálogo.

Execute esta demonstração no PowerShell. Ela gera dois arquivos sintéticos, importa ambos e tenta importar o primeiro novamente:

```powershell
@'
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from PIL import Image
from mfi_cv.data import CaptureSession, MotorModel, MotorUnit
from mfi_cv.data.database import create_database_engine
from mfi_cv.data.image_import import DuplicateImageError, import_photo
from mfi_cv.data.repository import MotorRepository

tag = uuid4().hex
model = MotorModel(f"modelo-{tag}", "Fabricante ficticio", "Linha ficticia",
                   "Modelo ficticio", "Fonte ficticia")
unit = MotorUnit(f"exemplar-{tag}", model)
session = CaptureSession(f"sessao-{tag}")
engine = create_database_engine()
with engine.begin() as connection:
    repository = MotorRepository(connection)
    repository.add_model(model)
    repository.add_unit(unit)
    repository.add_session(session)

metadata = dict(unit_id=unit.unit_id, session_id=session.session_id,
                origin="Imagem sintetica de demonstracao", capture_angle_deg=45)
with TemporaryDirectory() as temp:
    photo = Image.frombytes("RGB", (8, 8), bytes.fromhex(tag) * 12)
    files = [Path(temp) / "demo.png", Path(temp) / "demo.jpg"]
    for source in files:
        photo.save(source)
        imported = import_photo(engine, source, **metadata)
        print(imported.original_filename, Path("dataset/raw") / imported.path)
    try:
        import_photo(engine, files[0], **metadata)
    except DuplicateImageError as error:
        print("Duplicata da imagem", error.image_id)
engine.dispose()
'@ | .\.venv\Scripts\python.exe -
```

A saída deve mostrar os dois caminhos e, na última linha, o ID do registro da primeira foto. O SHA-256 identifica arquivos com bytes idênticos. Uma nova codificação da mesma foto pode produzir um hash diferente.

## Relatório de qualidade das fotografias

Na pasta `ComputerVisionPython`, execute no PowerShell:

```powershell
.\.venv\Scripts\python.exe -m mfi_cv.data.image_quality .\dataset\raw |
    Set-Content -Encoding ASCII .\dataset\relatorio-qualidade.json
Get-Content .\dataset\relatorio-qualidade.json -Raw | ConvertFrom-Json |
    Select-Object -ExpandProperty files |
    Where-Object { $_.issues.Count -gt 0 } |
    Format-Table path, width, height, sharpness, issues -AutoSize
```

O relatório tem caminhos relativos à pasta analisada. Abra os arquivos sinalizados para revisão visual. `invalid_image` indica conteúdo corrompido ou incompatível com os formatos estáticos aceitos. `unreadable` indica falha na leitura dos bytes, e `duplicate` indica conteúdo idêntico por SHA-256. Todos os caminhos de uma duplicata também aparecem em `duplicate_groups`.

A resolução recebe `low_resolution` quando o menor lado tem menos que `--min-side` pixels (padrão 640). A nitidez recebe `low_sharpness` quando a variância do Laplaciano fica abaixo de `--min-sharpness` (padrão 100). O Laplaciano mede diferenças locais de intensidade. Sua variância costuma cair quando o desfoque suaviza bordas. A métrica usa tons de cinza, limita o maior lado a 512 pixels sem ampliar e registra `null` se a imagem resultante for pequena demais para a janela de 3 × 3 pixels.

Os limites são iniciais e servem para triagem. Textura, ruído e iluminação também afetam a métrica. O relatório preserva as fotos e seus status no catálogo. Pastas e arquivos iniciados por ponto, incluindo os temporários do importador, são ignorados. Rode a análise com a pasta estável para reproduzir o resultado.

## Exportação do dataset de classificação

Na pasta `ComputerVisionPython`, com o catálogo migrado e as fotos aprovadas no armazenamento, execute:

```powershell
.\.venv\Scripts\python.exe -m mfi_cv.data.classification_dataset --source .\dataset\raw --output .\dataset\classification --seed 42
$manifesto = Get-Content .\dataset\classification\manifest.json -Raw -Encoding UTF8 | ConvertFrom-Json
$manifesto.classes | ConvertTo-Json -Depth 5
$manifesto.warnings
```

O comando lê o banco definido por `MFI_DATABASE_URL` ou o SQLite local. A saída deve ser uma pasta nova. Para verificar a repetibilidade, execute com a mesma seed e outra pasta de saída, com catálogo e arquivos estáveis, e compare o SHA-256 dos dois manifestos com `Get-FileHash`.

O manifesto mapeia as pastas de classe aos IDs comerciais e registra origem, hash, exemplar, sessão e partição de cada arquivo exportado. O exportador mantém juntos os registros ligados por exemplar, sessão ou SHA-256, inclusive por vínculos transitivos. Vínculos do catálogo podem incluir fotos pendentes ou rejeitadas. Somente as aprovadas são copiadas.

A divisão reserva treino para cada classe e tenta alocar cerca de 15% dos grupos por classe para validação e 15% para teste, priorizando cobertura em ambas. Os percentuais são metas para grupos, e a quantidade de fotos pode variar entre partições. Consulte `missing_splits` e `warnings` antes de usar o dataset para avaliação. Classes sem fotos aprovadas ficam fora da exportação. Se nenhuma foto estiver aprovada, o comando termina com erro e a saída não é publicada.

Para verificar o fluxo com dados sintéticos, sem alterar o catálogo local, execute:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_classification_dataset.py
```

## Pré-processamento e comparação visual

Na pasta `ComputerVisionPython`, selecione as fotos a processar e informe uma pasta de saída nova. O exemplo usa até três arquivos do armazenamento local:

```powershell
$fotos = @(Get-ChildItem .\dataset\raw -Recurse -File -Include *.jpg,*.jpeg,*.png,*.webp |
    Sort-Object FullName | Select-Object -First 3 -ExpandProperty FullName)
.\.venv\Scripts\python.exe -m mfi_cv.data.preprocessing --output .\dataset\processed --size 224 --compare-contrast @fotos
```

Abra os arquivos `*-comparison.png` para ver lado a lado o original orientado, o redimensionado e, se solicitado, a comparação experimental de contraste. Os arquivos `*-processed.png` contêm a imagem RGB redimensionada. A operação preserva as proporções, centraliza a imagem com preenchimento cinza e corrige a orientação EXIF. Os arquivos de origem ficam disponíveis para revisão.

A receita inicial para treino e inferência é a mesma. Use `prepare_image` para orientar, converter para RGB e redimensionar para o tamanho registrado com o modelo, e `normalize_rgb` para dividir os canais por 255. O resultado é um buffer contíguo de `float32` na ordem `(3, altura, largura)`. O PNG conserva os valores inteiros de 0 a 255 para inspeção. O ajuste experimental de contraste atua apenas na luminância antes do preenchimento e fica fora dessa receita, pois pode alterar detalhes visuais. Ao escolher o classificador, valide a transformação nativa da biblioteca e configure uma única passagem de redimensionamento e normalização, com a mesma receita na avaliação e na inferência.

## Primeiro treinamento do classificador

Na pasta `ComputerVisionPython`, instale o extra de treinamento. O primeiro treino precisa baixar os pesos oficiais ImageNet da MobileNetV3 Small. A variável abaixo guarda o cache na pasta `models/`, ignorada pelo Git.

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test,training]'
$env:TORCH_HOME = Join-Path (Get-Location) 'models/torch-cache'
.\.venv\Scripts\python.exe -m mfi_cv.data.train_classifier --demo --output .\models\demo-v1 --epochs 1 --batch-size 2 --size 96 --device cpu
Get-ChildItem .\models\demo-v1
Get-Content .\models\demo-v1\metrics.jsonl
```

A demonstração usa figuras sintéticas para verificar a execução. Seus pesos e métricas servem apenas para esse teste. Para treinar com um dataset real exportado pela etapa anterior, use:

```powershell
.\.venv\Scripts\python.exe -m mfi_cv.data.train_classifier --dataset .\dataset\classification --output .\models\baseline-v1 --epochs 10 --batch-size 8 --size 224 --seed 42 --device auto
```

A pasta de saída deve ser nova. O comando exige pelo menos duas classes e cobertura de todas em treino e validação. As imagens de teste ficam reservadas para avaliação posterior. `auto` usa CUDA se o PyTorch estiver instalado com esse suporte e detectar uma GPU compatível. Caso contrário, usa CPU.

A MobileNetV3 Small usa pesos `IMAGENET1K_V1` e treina apenas a camada linear final. A receita da etapa anterior é seguida pela padronização ImageNet dos canais com média e desvio padrão da Torchvision. `run.json` registra os parâmetros, as classes em ordem de saída e a identificação do manifesto. `metrics.jsonl` registra perda e acurácia por época em treino e validação. `best.pt` guarda os pesos da época com menor perda de validação.

## Comparação com variações de treino

A opção `--augment` sorteia uma rotação entre −8° e +8°, um fator de brilho entre 0,85 e 1,15 e uma escala entre 0,85 e 1,00. A rotação expande a área da foto e a escala reduz a imagem no quadro, conservando a cena inteira. O espelhamento fica desativado para preservar as assimetrias e o texto das placas. As variações só ocorrem no treino, e seus parâmetros ficam registrados em `run.json`.

Na pasta `ComputerVisionPython`, compare duas execuções com o mesmo dataset, seed, dispositivo, tamanho, lote e número de épocas. O exemplo usa os dados sintéticos da demonstração e exige duas pastas de saída novas:

```powershell
$env:TORCH_HOME = Join-Path (Get-Location) 'models/torch-cache'
$parametros = @('--demo', '--epochs', '5', '--batch-size', '2', '--size', '96', '--seed', '42', '--device', 'cpu')
.\.venv\Scripts\python.exe -m mfi_cv.data.train_classifier @parametros --output .\models\comparacao-base
.\.venv\Scripts\python.exe -m mfi_cv.data.train_classifier @parametros --augment --output .\models\comparacao-augment
foreach ($pasta in 'comparacao-base', 'comparacao-augment') {
    $melhor = Get-Content ".\models\$pasta\metrics.jsonl" |
        ForEach-Object { ConvertFrom-Json -InputObject $_ } |
        Sort-Object val_loss | Select-Object -First 1
    [pscustomobject]@{ Execucao = $pasta; Epoca = $melhor.epoch; Perda = $melhor.val_loss; Acuracia = $melhor.val_accuracy }
}
```

Verifique se os dois arquivos `run.json` registram o mesmo `manifest_sha256` e se só o segundo tem `augmentation.enabled` igual a `true`. A comparação sintética verifica o fluxo. Para medir o efeito em motores, repita com `--dataset .\dataset\classification` no lugar de `--demo` e use a mesma partição de validação para as duas execuções.

## Identificar candidatos a partir de uma foto

Na pasta `ComputerVisionPython`, use o extra de treinamento já instalado e um `best.pt` gerado pelo MFI. Este exemplo usa o checkpoint e uma figura sintética da demonstração:

```powershell
$foto = Get-ChildItem .\dataset\raw -Recurse -Filter *.png -File | Select-Object -First 1 -ExpandProperty FullName
.\.venv\Scripts\python.exe -m mfi_cv.data.motor_classifier $foto --checkpoint .\models\demo-v1\best.pt --top-k 2
```

Em Python, carregue o checkpoint uma vez e reutilize o classificador:

```python
from mfi_cv.data.motor_classifier import MotorClassifier

classifier = MotorClassifier("models/baseline-v1/best.pt")
prediction = classifier.predict("motor.jpg", top_k=3)
```

A saída inclui `candidates`, em ordem decrescente de pontuação, e `status`. As pontuações vêm do softmax e ainda precisam de calibração para interpretação probabilística. Os limiares iniciais são provisórios:

- `unknown` quando a primeira pontuação fica abaixo de `--reject-below` (padrão 0,60).
- `accepted` quando a primeira pontuação alcança `--accept-at` (padrão 0,85) e a distância para a segunda alcança `--min-margin` (padrão 0,15).
- `needs_confirmation` nos demais casos. Confira os candidatos ou a placa do motor.

O status considera as duas primeiras pontuações mesmo com `--top-k 1`. Uma imagem ilegível gera `InvalidPhotoError`. Um checkpoint ausente ou incompatível gera `ModelUnavailableError`. No comando, esses erros retornam código 1, e checkpoints sintéticos exibem um aviso separado do JSON.

## Avaliação no conjunto de teste

Na pasta `ComputerVisionPython`, com o extra de treinamento instalado, avalie o checkpoint sintético da etapa anterior:

```powershell
.\.venv\Scripts\python.exe -m mfi_cv.data.evaluate_classifier --demo --checkpoint .\models\demo-v1\best.pt --output .\models\demo-v1\avaliacao.json
Get-Content .\models\demo-v1\avaliacao.json -Raw -Encoding UTF8
```

Para avaliar um checkpoint real, substitua `--demo` por `--dataset .\dataset\classification` e indique o checkpoint correspondente. O avaliador confere a identidade do manifesto usado no treino, a separação por exemplar, sessão, grupo e hash e o SHA-256 das fotos de teste. O arquivo de saída deve ser novo.

O relatório inclui acurácia Top-1 e Top-5 quando há pelo menos cinco classes, além de precisão, recall e F1 por modelo e suas médias macro quando todas as classes têm fotos de teste. As linhas da matriz de confusão representam classes reais e as colunas, classes preditas. As métricas de classificação usam a ordem das pontuações independentemente do status de confirmação. O tempo por foto inclui leitura, pré-processamento e previsão em CPU, incluindo a primeira chamada. Os resultados sintéticos verificam a execução e ficam identificados no relatório.

## Análise dos erros de classificação

Na pasta `ComputerVisionPython`, gere um relatório em um caminho novo:

```powershell
.\.venv\Scripts\python.exe -m mfi_cv.data.analyze_classifier_errors --demo --checkpoint .\models\demo-v1\best.pt --output .\models\demo-v1\analise-erros.json
$analise = Get-Content .\models\demo-v1\analise-erros.json -Raw -Encoding UTF8 | ConvertFrom-Json
$analise.totals
$analise.confusions
$analise.by_model | ConvertTo-Json -Depth 8
```

Para analisar fotos reais, use `--dataset .\dataset\classification` no lugar de `--demo`, com o checkpoint treinado no manifesto correspondente. Cada erro Top-1 ou pedido de revisão fica em `by_model`, com o caminho relativo ao dataset, os candidatos, o status e a condição registrada. Quando há um exemplo da classe predita na partição de teste, o relatório fornece seu caminho para comparação visual com a foto confundida. Ramos sem ocorrências podem ficar vazios.

`by_angle` agrupa ângulos em intervalos de 90° e usa `unknown` quando o manifesto não informa o ângulo. Novas exportações incluem o ângulo disponível no catálogo. Preserve o manifesto original ao analisar um checkpoint existente. `by_brightness` usa o brilho médio em tons de cinza, com as faixas abaixo de 64, de 64 até menos de 192 e a partir de 192. Compare os erros junto das contagens de imagens. O brilho médio também depende da cor do motor, do fundo e da exposição, e a análise de `unknown` nestes dados cobre fotos de classes conhecidas.

## API de inferência local

Na pasta `ComputerVisionPython`, instale os extras, aplique as migrações e inicie o servidor no PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api,training,test]'
.\.venv\Scripts\python.exe -m alembic upgrade head
$env:MFI_CHECKPOINT = (Resolve-Path .\models\demo-v1\best.pt).Path
.\.venv\Scripts\python.exe -m uvicorn mfi_cv.api:app --host 127.0.0.1 --port 8000
```

O exemplo usa os pesos sintéticos da etapa 4.1 e o catálogo definido por `MFI_DATABASE_URL`, ou o SQLite local quando a variável estiver ausente. Em outro PowerShell, na mesma pasta, consulte a API e envie uma imagem sintética:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/models
$foto = Get-ChildItem .\dataset\raw -Recurse -Filter *.png -File | Select-Object -First 1 -ExpandProperty FullName
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/predict -ContentType 'image/png' -InFile $foto |
    ConvertTo-Json -Depth 4
```

`GET /health` retorna 200 quando o classificador e o catálogo estão disponíveis, ou 503 com o estado de ambos. `GET /models` lista os IDs de classe do checkpoint e indica se ele é sintético. `GET /motors` retorna uma lista ordenada por `model_id`, com `model_id`, `manufacturer`, `product_line` e `commercial_model` para seleção manual. Um catálogo vazio retorna `[]` com HTTP 200. As consultas ao catálogo funcionam sem carregar um checkpoint e retornam HTTP 503 se o banco estiver indisponível.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/motors
```

`GET /motors/{motor_id}` consulta as especificações do modelo comercial cadastrado e retorna 404 para um ID ausente. Para montar a URL, codifique o ID com `[uri]::EscapeDataString($id)`.

`POST /predict` recebe os bytes da foto no corpo, com `Content-Type` igual a `image/jpeg`, `image/png` ou `image/webp`. O limite é 8 MiB e 24 megapixels. O JSON de sucesso contém `candidates` e `status`. Respostas de erro do endpoint usam `detail`, incluindo 400 para foto inválida, 413 para tamanho excessivo, 415 para tipo incompatível e 503 quando o classificador está indisponível.

Com o servidor ativo, a documentação interativa fica em `http://127.0.0.1:8000/docs` e o contrato OpenAPI em `http://127.0.0.1:8000/openapi.json`.

## Histórico da integração Unity

O teste abaixo documenta a antiga etapa 6.2 e o cliente C# registrado em `9783da8`. Para o desenvolvimento atual, siga o [roadmap da aplicação web](../docs/ROADMAP.md).

Inicie a API em `127.0.0.1:8000` conforme a seção anterior. Em outro PowerShell, na raiz do projeto Unity, copie um PNG sintético para um asset de teste com a extensão `.bytes`. O Unity importa esse arquivo como `TextAsset` e mantém os bytes originais.

```powershell
$foto = Get-ChildItem .\ComputerVisionPython\dataset\raw -Recurse -Filter *.png -File |
    Select-Object -First 1 -ExpandProperty FullName
Copy-Item -LiteralPath $foto -Destination .\Assets\MfiPredictionDemo.bytes
```

1. Abra uma cena de teste no Unity 6 e crie um GameObject vazio.
2. Adicione `MotorPredictionDemo`. No Inspector, atribua `MfiPredictionDemo.bytes` a **Test Photo**, mantenha **Content Type** como `image/png` e **Api Base Url** como `http://127.0.0.1:8000`.
3. Se o Editor bloquear HTTP local, permita HTTP para desenvolvimento em **Player Settings → Other Settings → Configuration → Allow downloads over HTTP** no projeto de teste.
4. Entre em Play Mode. O Console mostra o processamento, o estado retornado e a pontuação de cada candidato. Com o checkpoint sintético, os IDs começam com `demo-`.
5. Para verificar falhas, pare a API com Ctrl+C e use **Enviar foto de teste** no menu de contexto do componente, ainda em Play Mode. O Console deve informar falha de comunicação. Com a API ativa, enviar o PNG com **Content Type** igual a `image/jpeg` deve produzir HTTP 415.

O cliente usa `UnityWebRequest` com corpo binário e timeout padrão de 15 segundos. Outros componentes podem chamar `MotorPredictionClient.Predict` com os bytes de uma foto, seu tipo de conteúdo e callbacks de sucesso e erro.
