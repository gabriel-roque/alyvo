# Dados sintéticos

Todos os nomes, CPFs, documentos, clínicas e agendas deste diretório são
fictícios. O seed cria duas clínicas: `clinic-alyvo` para a demonstração e
`clinic-isolation` exclusivamente para validar isolamento multi-tenant.

`synthetic-documents/` contém identidades, carteirinhas e pedidos limpos,
rotacionados, desfocados e com ruído, além de um PDF institucional. Todos são
gerados por `generate_assets.py` e trazem marcação explícita de documento sem
validade.

Credenciais da demo:

- paciente: CPF `123.456.789-09`, OTP `123456`;
- administração: `admin@alyvo.local` / `alyvo-demo`;
- recepção: `recepcao@alyvo.local` / `alyvo-demo`.

