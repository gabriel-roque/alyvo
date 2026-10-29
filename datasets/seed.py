from app.db import SessionLocal, create_schema
from app.seed import seed_demo

if __name__ == "__main__":
    create_schema()
    with SessionLocal() as session:
        seed_demo(session)
    print("Dados sintéticos carregados para clinic-alyvo e clinic-isolation.")

