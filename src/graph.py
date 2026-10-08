# src/graph.py
from langgraph.graph import StateGraph, END
from src.state import ReportState
from src.nodes import noeud_cartes, noeud_exercices, noeud_redacteur

graph = StateGraph(ReportState)

graph.add_node("cartes", noeud_cartes)
graph.add_node("exercices", noeud_exercices)
graph.add_node("redacteur", noeud_redacteur)

graph.set_entry_point("cartes")
graph.add_edge("cartes", "exercices")
graph.add_edge("exercices", "redacteur")
graph.add_edge("redacteur", END)

report_app = graph.compile()