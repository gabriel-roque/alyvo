# Migrações

O MVP usa `Base.metadata.create_all()` no modo local/teste para reduzir atrito. Em
PostgreSQL, aplique `0001_initial.sql` depois da criação inicial para habilitar a
restrição GiST de não sobreposição e as políticas RLS. A API também valida tenant
e conflito antes da escrita; a restrição é a garantia final sob concorrência.

