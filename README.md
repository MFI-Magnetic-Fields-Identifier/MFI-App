# MFI — Magnetic Fields Identifier

O MFI é uma aplicação web para identificar motores elétricos por fotografia, consultar suas características técnicas e explorar seus campos eletromagnéticos no navegador. O foco inicial é desktop.

O simulador pode ser usado por seleção manual de um perfil, inclusive quando a identificação por foto estiver indisponível. Quando o usuário envia uma foto, o classificador sugere modelos e sinaliza casos que exigem confirmação antes de associar dados técnicos à imagem.

## Estado do projeto

- **Visão computacional e API.** O módulo em `ComputerVisionPython/` reúne cadastro de motores, importação e revisão das fotos, exportação do dataset, treinamento, avaliação e inferência. A API FastAPI expõe saúde, classes do checkpoint, previsão, listagem do catálogo e consulta de motor por ID. As verificações de reconhecimento até aqui usaram dados sintéticos. [Guia do módulo](ComputerVisionPython/README.md)
- **Frontend e simulação.** A tela em `apps/web/` permite selecionar perfis JSON de demonstração ou enviar uma foto para visualizar os candidatos da API. O simulador está planejado, com foco inicial em uma representação 2D de motores de indução monofásicos e trifásicos. [Guia do frontend](apps/web/README.md)
- **Histórico.** A integração anterior com Unity está registrada no Git. A interface ativa do projeto seguirá a arquitetura web.

## Desenvolvimento

O trabalho continua em microetapas. O roadmap registra o que já foi entregue, os marcos da arquitetura web e os critérios de validação. [Roadmap](docs/ROADMAP.md)
