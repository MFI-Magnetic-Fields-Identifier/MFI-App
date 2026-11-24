# MFI — Roadmap da aplicação web

## 1. Ponto de partida

O último marco de produção de código antes da mudança de arquitetura foi a etapa 6.2 do plano anterior, registrada em `9783da8`. O cliente C# e sua demonstração ficam em `Assets/Scripts/ComputerVision/` no histórico. A etapa seguinte de câmera AR ficou sem implementação. A aplicação React já tem seleção manual em `apps/web/`. O simulador em TypeScript está planejado.

| Etapas concluídas | Funcionalidade preservada |
|---|---|
| 1.1–2.3 | Estrutura Python, modelos e exemplares físicos, catálogo, migrações, importação de fotos e detecção de duplicatas por hash. |
| 3.1–3.3 | Relatório de qualidade, dataset com separação por exemplar e sessão e pré-processamento de imagens. |
| 4.1–4.3 | MobileNetV3 Small por transferência de aprendizado, variações opcionais no treino e inferência Top-K com pedido de confirmação e estado `unknown`. |
| 5.1–5.2 | Avaliação em partição reservada e análise de erros por classe e condição de captura. |
| 6.1 | FastAPI com `GET /health`, `GET /models`, `GET /motors/{motor_id}` e `POST /predict`. |
| 6.2 Web | `GET /motors` lista os modelos comerciais cadastrados para seleção manual, sem exigir checkpoint. |
| 6.3 Web | Tela de seleção manual com perfis JSON de demonstração, disponível com o backend desligado. |
| 6.4 Web | Upload de foto para `POST /predict`, com estado de processamento, candidatos, pontuações e tratamento de erros. |

O módulo Python continua em `ComputerVisionPython/`. Seus comandos, testes, migrações e artefatos locais já usam esse caminho. Uma futura mudança para `services/computer-vision/` poderá ser avaliada quando houver necessidade concreta.

## 2. Arquitetura aprovada

| Área | Direção |
|---|---|
| Frontend | React, TypeScript e Vite, com foco inicial em desktop. Tailwind CSS pode ser adotado se encaixar na base do frontend. |
| Simulação | Funções matemáticas TypeScript independentes da interface, testadas com Vitest. Canvas 2D ou SVG na visualização inicial. Three.js, React Three Fiber e Drei quando úteis à visualização 3D, após validar o 2D. |
| Visão computacional | Python, PyTorch e pytest, com o classificador MobileNetV3 Small já implementado. OpenCV, NumPy, scikit-learn e YOLO ou outra alternativa entram conforme a necessidade técnica de cada etapa. |
| Backend | FastAPI, Pydantic e Uvicorn. O React usa HTTP e JSON para a integração. |
| Dados | Perfis JSON identificados como demonstração para seleção manual. O catálogo Python mantém SQLite para uso local e configuração para PostgreSQL quando houver necessidade de persistência estruturada. Fotos ficam em arquivos, com object storage como opção futura. |

O fluxo de identificação recebe uma foto selecionada no navegador, apresenta candidatos e pontuações e consulta os dados técnicos do modelo após confirmação. O simulador recebe um perfil selecionado manualmente ou um perfil confirmado pelo usuário. Seu cálculo e sua interface podem operar sem o classificador ou a API.

### Substituições no plano anterior

| Integração anterior | Integração web |
|---|---|
| Unity e cliente C# | React e serviços HTTP tipados em TypeScript |
| Captura AR sob demanda | Seleção e upload de um arquivo de imagem no navegador |
| Cenas, prefabs e sobreposição sobre motores físicos | Componentes React de visualização e representações Canvas, SVG ou WebGL |
| Execução de IA offline no Unity | Inferência no serviço Python e consumo pela API |

Saíram do roadmap Unity, Unity Hub, C#, AR Foundation, ARCore, AR, WebXR, marcadores, ancoragem, pose para sobreposição, exportação ONNX para Unity, APK, aplicativos mobile, PWA e funcionalidades nativas de smartphone. Os commits anteriores documentam as decisões e os testes daquela arquitetura.

## 3. Próximas microetapas

Cada linha é uma entrega independente. Verifique o estado do repositório antes de implementar, execute os testes disponíveis, documente a verificação manual e aguarde autorização para a etapa seguinte.

### Fase 6 — Integração web e catálogo

| Microetapa | Entrega e critério de conclusão |
|---|---|
| **6.5 Web — Confirmar identificação e carregar perfil** | Integrar a lista do catálogo por `GET /motors` e consultar `GET /motors/{id}` após seleção de um registro ou confirmação de um candidato. Tratar IDs ausentes e resultados desconhecidos. A seleção manual por JSON continua disponível sem a API. |

### Fase 7 — Simulação eletromagnética no navegador

| Microetapa | Entrega e critério de conclusão |
|---|---|
| 7.1 — Modelo de rotação em TypeScript | Calcular a velocidade síncrona a partir de frequência e número de polos, e a velocidade do rotor a partir do escorregamento. Verificar unidades, valores inválidos e casos de referência com Vitest. |
| 7.2 — Seção transversal 2D | Representar estator, rotor e enrolamentos com geometria simplificada e conferir a correspondência com o modelo adotado. |
| 7.3 — Modelo analítico trifásico | Calcular as contribuições das fases e o campo resultante. Testar a direção e a magnitude resultante em instantes de referência. |
| 7.4 — Vetores do campo em 2D | Integrar os vetores à seção transversal e permitir inspecionar a contribuição de cada fase. |
| 7.5 — Mapa de intensidade relativa | Exibir a intensidade em escala normalizada e conferir a correspondência entre mapa e campo calculado. |
| 7.6 — Animação do campo girante | Atualizar a visualização ao longo do tempo com velocidade de reprodução controlável. Conferir a direção e a periodicidade da rotação. |
| 7.7 — Campo monofásico 2D | Representar o campo pulsante do modelo monofásico e adicionar alternância com o trifásico. Verificar separadamente os dois comportamentos. |
| 7.8 — Controles do motor | Permitir ajustar frequência, polos e escorregamento. Mostrar rotação síncrona e do rotor com unidades explícitas. |
| 7.9 — Visualização 3D | Depois da validação em 2D, apresentar as mesmas grandezas com geometrias simplificadas em Three.js e React Three Fiber. |

A interface deve identificar o campo do modelo analítico e a escala relativa. Se forem adicionados resultados por estimação, medições operacionais ou elementos finitos, cada origem deve ser identificada. Reserve teslas para resultados que tenham fundamentação e unidade física correspondente.

### Fase 8 — Evolução da visão computacional

| Microetapa | Entrega e critério de conclusão |
|---|---|
| 8.1 — Avaliar reconhecimento com fotos reais | Ampliar o catálogo de imagens aprovadas, manter exemplares e sessões independentes entre conjuntos e repetir os fluxos de treinamento e avaliação já entregues. Medir confusões e rejeições com fotos de modelos conhecidos e fora do catálogo. |
| 8.2 — Detectar motores em fotografias | Preparar anotações com caixas delimitadoras, avaliar um detector leve e usar a região localizada para auxiliar a classificação de fotos enviadas pelo navegador. |
| 8.3 — Ler placas por OCR | Extrair e validar os campos da placa, registrar limitações e cruzar os valores com o catálogo, exigindo confirmação quando houver conflito. |

## 4. Próxima etapa autorizável

**6.5 Web — Confirmar identificação e carregar perfil.** Integrar o catálogo HTTP à seleção manual e permitir consultar o perfil de um candidato confirmado pelo usuário.
