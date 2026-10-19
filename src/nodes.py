# src/nodes.py
from datetime import datetime, timedelta
from src.models import db, Card, StudentCardState, ReviewLog,ExerciseSubmission,Exercise
from dotenv import load_dotenv
import os
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.state import ReportState
from sqlalchemy import func
load_dotenv()




llm = ChatMistralAI(model="mistral-small-latest", api_key=os.getenv("MISTRAL_API_KEY"))

def compute_cards_stats(student_id):
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)

    cards_reviewed_7j = ReviewLog.query.filter(
        ReviewLog.student_id == student_id,
        ReviewLog.reviewed_at >= seven_days_ago
    ).count()

    cards_never_done = 0
    for card in Card.query.filter_by(student_id=student_id).all():
        state = StudentCardState.query.filter_by(
            student_id=student_id, card_id=card.id
        ).first()
        if state is None:
            cards_never_done += 1

    reviews_7j = ReviewLog.query.filter(
        ReviewLog.student_id == student_id,
        ReviewLog.reviewed_at >= seven_days_ago
    ).all()

    stats_par_carte = {}
    for review in reviews_7j:
        if review.card_id not in stats_par_carte:
            stats_par_carte[review.card_id] = {"echecs": 0, "reussites": 0}

        if review.quality in ("again", "hard"):
            stats_par_carte[review.card_id]["echecs"] += 1
        else:
            stats_par_carte[review.card_id]["reussites"] += 1

    hardest_card_id = None
    worst_ratio = None
    for card_id, stats in stats_par_carte.items():
        total = stats["echecs"] + stats["reussites"]
        ratio = stats["echecs"] / total
        if worst_ratio is None or ratio > worst_ratio:
            worst_ratio = ratio
            hardest_card_id = card_id

    if hardest_card_id is None:
        hardest_card = None
    else:
        card = Card.query.get(hardest_card_id)
        hardest_card = {
            "question": card.question,
            "chapter": card.chapter,
            "echecs": stats_par_carte[hardest_card_id]["echecs"],
            "reussites": stats_par_carte[hardest_card_id]["reussites"],
        }

    return {
        "cards_reviewed_7j": cards_reviewed_7j,
        "cards_never_done": cards_never_done,
        "hardest_card": hardest_card,
    }

def noeud_cartes(state: ReportState) -> ReportState:
    state["cards_stats"] = compute_cards_stats(state['student_id'])
    return state
def compute_exercises_stats(student_id):
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)

    submissions_7j = ExerciseSubmission.query.filter(
        ExerciseSubmission.student_id == student_id,
        ExerciseSubmission.submitted_at >= seven_days_ago
    ).count()

    avg_result = db.session.query(func.avg(ExerciseSubmission.grade)).filter(
        ExerciseSubmission.student_id == student_id,
        ExerciseSubmission.submitted_at >= seven_days_ago,
        ExerciseSubmission.grade.isnot(None)
    ).scalar()
    average_grade_7j = round(avg_result, 1) if avg_result is not None else None

    reussi_7j = ExerciseSubmission.query.filter(
        ExerciseSubmission.student_id == student_id,
        ExerciseSubmission.submitted_at >= seven_days_ago,
        ExerciseSubmission.status == "reussi"
    ).count()

    a_revoir_7j = ExerciseSubmission.query.filter(
        ExerciseSubmission.student_id == student_id,
        ExerciseSubmission.submitted_at >= seven_days_ago,
        ExerciseSubmission.status.in_(["a_revoir", "petite_erreur"])
    ).count()

    exercises_never_started = 0
    for exo in Exercise.query.filter_by(student_id=student_id).all():
        submission = ExerciseSubmission.query.filter_by(exercise_id=exo.id).first()
        if submission is None:
            exercises_never_started += 1

    return {
        "submissions_7j": submissions_7j,
        "average_grade_7j": average_grade_7j,
        "reussi_7j": reussi_7j,
        "a_revoir_7j": a_revoir_7j,
        "exercises_never_started": exercises_never_started,
    }
def noeud_exercices(state: ReportState) -> ReportState:
    state["exercises_stats"] = compute_exercises_stats(state["student_id"])
    return state

REPORT_PROMPT = """Tu rédiges un rapport hebdomadaire pour un professeur de mathématiques,
qui doit préparer sa prochaine séance avec un élève. Le rapport est pour LE PROF, pas pour l'élève —
tu peux parler de l'élève à la troisième personne, de façon factuelle et directe.

Voici les données de la semaine (aucune interprétation n'est faite dessus, à toi de les analyser) :

{donnees}

Rédige un rapport court et structuré avec :
- Un résumé en 1-2 phrases de l'activité de la semaine
- Ce qui semble acquis / bien maîtrisé
- Ce qui semble fragile ou à surveiller (notamment la carte la plus difficile si elle existe)
- Une recommandation concrète pour la prochaine séance

Règles strictes :
- N'invente AUCUNE donnée. Utilise uniquement ce qui est fourni ci-dessus.
- Si une donnée est à 0 ou None, dis-le clairement (ex : "aucun exercice soumis cette semaine"),
  ne fais pas comme si elle n'existait pas.
- Reste concis, pas plus de 150 mots.
- Pas d'emoji, pas de formules de politesse artificielles."""


def formater_donnees(cards_stats, exercises_stats):
    lignes = [
        f"Cartes révisées cette semaine : {cards_stats['cards_reviewed_7j']}",
        f"Cartes jamais commencées : {cards_stats['cards_never_done']}",
    ]

    if cards_stats["hardest_card"]:
        hc = cards_stats["hardest_card"]
        lignes.append(
            f"Carte la plus difficile : \"{hc['question']}\" (chapitre {hc['chapter']}) "
            f"— {hc['echecs']} échec(s) contre {hc['reussites']} réussite(s)"
        )
    else:
        lignes.append("Aucune carte révisée cette semaine")

    lignes.append(f"Exercices soumis cette semaine : {exercises_stats['submissions_7j']}")
    lignes.append(f"Exercices réussis : {exercises_stats['reussi_7j']}")
    lignes.append(f"Exercices à revoir : {exercises_stats['a_revoir_7j']}")
    lignes.append(f"Exercices jamais commencés : {exercises_stats['exercises_never_started']}")

    if exercises_stats["average_grade_7j"] is not None:
        lignes.append(f"Note moyenne sur les exercices notés : {exercises_stats['average_grade_7j']}/20")
    else:
        lignes.append("Aucune note disponible cette semaine")

    return "\n".join(lignes)


def noeud_redacteur(state: ReportState) -> ReportState:
    donnees = formater_donnees(state["cards_stats"], state["exercises_stats"])
    prompt = REPORT_PROMPT.format(donnees=donnees)

    messages = [SystemMessage(content=prompt), HumanMessage(content="Rédige le rapport.")]
    reponse = llm.invoke(messages)
    state["rapport_final"] = reponse.content
    return state