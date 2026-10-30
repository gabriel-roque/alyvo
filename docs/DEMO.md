# Roteiro de demonstração

1. No chat, pergunte quais cardiologistas aceitam Vida+ na Unidade Centro e abra as fontes.
2. Peça um agendamento, autentique o paciente com CPF `123.456.789-09` e código `123456`, escolha um horário e confirme.
3. Anexe uma carteirinha no próprio chat, revise os campos do OCR e confirme.
4. Entre no backoffice como `admin@alyvo.local` / `alyvo-demo`; confira agenda, documento e auditoria.
5. Publique uma ingestão ou cadastre um profissional e aguarde o estado `synced`.
6. Faça uma pergunta sem cobertura e confirme a criação do ticket; trate-o no backoffice.

O widget também pode ser incluído em outra página:

```html
<script src="http://localhost:3000/alyvo-widget.js" data-origin="http://localhost:3000" defer></script>
```
