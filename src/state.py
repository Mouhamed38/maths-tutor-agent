# src/state.py
from typing import TypedDict

class ReportState(TypedDict):
    student_id: int
    student_name: str
    cards_stats: dict
    exercises_stats: dict
    rapport_final: str