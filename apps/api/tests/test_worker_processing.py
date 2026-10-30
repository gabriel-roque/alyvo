from types import SimpleNamespace

from worker import neo4j_projection, tasks


def test_structured_fields_parse_noisy_labelled_ocr(monkeypatch):
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: SimpleNamespace(llm_provider="ollama"),
    )

    fields = tasks._structured_fields(
        "NOME: Juliana Silva\nCONVENIO: Vida+\nNUMER0: VIDA-102938\nVALIDADE: 12/2027",
        "insurance_card",
        {"texto": "raw"},
    )

    assert fields == {
        "nome": "Juliana Silva",
        "convenio": "Vida+",
        "numero": "VIDA-102938",
        "validade": "12/2027",
    }


def test_knowledge_projection_stores_only_primitive_entity_properties(monkeypatch):
    calls = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def run(self, query, **parameters):
            calls.append((query, parameters))
            return self

        def consume(self):
            return None

    class Driver:
        def session(self):
            return Session()

    monkeypatch.setattr(
        neo4j_projection,
        "embedding_provider",
        lambda: SimpleNamespace(embed=lambda chunks: [[0.1, 0.2] for _ in chunks]),
    )
    projector = neo4j_projection.Neo4jProjector.__new__(
        neo4j_projection.Neo4jProjector
    )
    projector.driver = Driver()

    projector._knowledge(
        "clinic-alyvo",
        {
            "id": "document-1",
            "title": "Documento",
            "chunks": ["conteúdo"],
            "entities": [
                {"type": "Doctor", "name": "Dra. Marina", "id": "doctor-1"},
                "Cardiologia",
            ],
        },
    )

    assert calls[0][1]["entities"] == ["Dra. Marina", "Cardiologia"]
