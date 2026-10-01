# Prompt: áudio de WhatsApp que chega mas não toca

Cole o bloco abaixo em outra IA/agente quando o envio de áudio pela Cloud API da
Meta estiver "funcionando" (200 OK em tudo) mas o destinatário real não
conseguir ouvir.

---

Estou enviando áudio como nota de voz pelo WhatsApp Cloud API (Meta Graph API).
Todas as chamadas voltam 200 OK, o `media_id` é criado, a mensagem é entregue e
o áudio toca normalmente quando eu baixo o arquivo e abro no navegador. Mesmo
assim, no celular do destinatário a mensagem aparece como
**"este áudio não está mais disponível"** e não toca.

Já descobri que esse problema tem três causas que precisam ser corrigidas
juntas — valide as três no meu código e corrija o que estiver faltando:

**1. O mime type precisa ser a string completa, com o codec.**
Use `audio/ogg; codecs=opus` — não `audio/ogg` puro. Ele tem que aparecer nos
dois lugares da chamada de upload para `POST /{phone_number_id}/media`: no campo
de formulário `type` e no Content-Type da parte do arquivo.

**2. A mensagem precisa declarar que é nota de voz.**
No `POST /{phone_number_id}/messages`, o objeto `audio` tem que ter
`"voice": true`. Sem isso vira anexo de áudio genérico, não nota de voz.

**3. (a causa principal) O perfil de encoding do ffmpeg.**
Essa é a parte que a documentação da Meta não diz. Um Opus genérico
(`-ar 48000 -c:a libopus`) passa na validação da API sem reclamar, mas o pipeline
interno de entrega de mídia do WhatsApp é muito mais rigoroso e simplesmente
deixa de servir o arquivo — falha invisível, só aparece quando alguém de verdade
tenta ouvir. Reencode sempre (independente do formato de entrada: webm/opus do
navegador, mp3, wav, m4a) com o perfil VOIP mono, que é o que os clientes reais
do WhatsApp usam:

```
ffmpeg -y -loglevel warning \
  -err_detect ignore_err -fflags +discardcorrupt \
  -i <entrada> \
  -vn -ar 16000 -ac 1 \
  -c:a libopus -b:a 32k -compression_level 10 \
  -frame_duration 60 -application voip -packet_loss 0 \
  -avoid_negative_ts make_zero -map_metadata -1 \
  -f ogg <saida.ogg>
```

O que cada parte resolve:
- `-ar 16000 -ac 1` — mono, 16 kHz: é a taxa que o WhatsApp usa em nota de voz.
- `-application voip` e `-frame_duration 60` — o perfil VOIP do Opus. **É o que
  destrava a reprodução no celular**; com o perfil padrão (`audio`) o arquivo é
  aceito e nunca toca.
- `-map_metadata -1` — tira metadados do arquivo de origem, que às vezes vêm com
  duração ou timestamps que o WhatsApp rejeita.
- `-avoid_negative_ts make_zero` — áudio gravado no navegador costuma começar com
  timestamp negativo.
- `-err_detect ignore_err -fflags +discardcorrupt` — grava de navegador vem com
  quadros truncados no fim; sem isso o ffmpeg aborta em vez de converter.
- `-f ogg` explícito e extensão `.ogg` no nome do arquivo enviado.

Reencode **sempre**, mesmo quando o mime type que chegou já diz ogg/opus: não dá
pra confiar que o que o navegador gravou está no perfil certo.

Depois de corrigir, teste mandando para um celular de verdade e ouvindo — teste
em navegador não serve, porque o áudio errado toca normalmente ali.

---

## Referência da implementação que funciona

Neste projeto está em [backend/app/servicos/whatsapp.py](backend/app/servicos/whatsapp.py),
função `_normalizar_audio`, com a constante
`_MIME_AUDIO_WHATSAPP = "audio/ogg; codecs=opus"` e o `corpo_midia["voice"] = True`
em `enviar_arquivo`.
