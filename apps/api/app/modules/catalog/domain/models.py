from enum import StrEnum


class CatalogKind(StrEnum):
    SPECIALTY = "specialties"
    UNIT = "units"
    INSURER = "insurers"
    EXAM = "exams"
