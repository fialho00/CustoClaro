# CustoClaro ⚡

Foto da etiqueta elétrica → potência revisada → estimativa de custo. Projeto de Alexandre Bezerra, Maria Eduarda e Gabriel Fialho.

## Usar no Windows

1. Instale Python 3.10+ e baixe/extraia este repositório.
2. Abra `Iniciar_CustoClaro.bat`. Na primeira execução, aguarde a instalação.
3. Escolha **1** para abrir ou **3** para escolher uma foto antes de abrir.
4. Se quiser leitura por IA, informe uma Gemini API Key na opção **2** antes de abrir, ou no campo **Chave da IA** dentro do app. Pode colar somente a chave ou `GEMINI_API_KEY=...`; não há exigência de prefixo `AIza`.
5. No navegador, envie/tire a foto da etiqueta. Clique **Ler etiqueta com IA**, confira os W e confirme. Sem chave ou sem foto, digite os W manualmente.
6. Informe **minutos de uso por dia**. O custo aparece logo abaixo. Tarifa e dias podem ser ajustados em **Ajustes**. A tarifa inicial R$ 0,90/kWh é apenas um exemplo.

O chat inferior responde perguntas sobre **esta simulação**. Cenários como “e se usar 5 minutos?” são calculados localmente. Com chave de API, perguntas abertas sobre a etiqueta ou a estimativa usam Gemma 4 com os números já calculados; não é um chat geral.

## Privacidade

O iniciador não cria `.env` e não salva chaves. A chave permanece na memória do processo/sessão durante o uso; fotos, mensagens e resultados não são gravados pelo código do app. Ao clicar em **Ler etiqueta com IA**, a imagem reduzida e sem EXIF é enviada à API do Google. Considere os termos e a política de dados do provedor antes de enviar imagens sensíveis. Uma foto previamente escolhida já existe no local original do usuário. Arquivos `.env` criados por versões antigas não são lidos pelo app atual: remova-os você mesmo se não precisar deles. O CSV só inclui os dados do cálculo, sem a chave ou a foto.

No chat com IA, cada pergunta aberta envia a pergunta e os números da simulação à API do Google. O histórico completo do chat não é enviado pelo código do app. Sem chave, o chat oferece respostas locais limitadas.

## Resultados e limites

`kWh/mês = (W / 1000) × (minutos/dia / 60) × dias/mês`

`custo/mês = kWh/mês × tarifa informada`

A IA lê uma indicação explícita de potência W/kW e mostra a evidência; o usuário revisa o valor antes do cálculo. **Código de barras sozinho não indica potência elétrica.** A estimativa assume consumo constante e não mede o aparelho. Termostatos, ciclos, potência variável, impostos e taxas podem alterar o custo real. O custo de 12 meses assume 12 meses iguais.

O CSV tem uma linha por simulação, delimitador `;`, marcador UTF-8 e cabeçalhos para Excel. O layout é responsivo para navegadores de celular; para abrir no celular, hospede o app com HTTPS. O `.bat` abre somente no PC local por segurança.

## Desenvolvimento

```bash
python -m venv .venv
# Ative o ambiente e instale as dependências
python -m pip install -r requirements.txt
python -m streamlit run app.py
python -m unittest discover -s tests -v
```

`vision.py` chama `gemma-4-26b-a4b-it` pela Gemini API; `core.py` realiza a matemática determinística. Testes automatizados simulam a resposta da IA. Uma leitura real depende de chave válida, disponibilidade do modelo e uma etiqueta legível.

Código original sob MIT; o modelo e dependências seguem seus próprios termos.
