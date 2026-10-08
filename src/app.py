from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
from src.models import db, Student, Card, StudentCardState,ReviewLog,Exercise, ExerciseSubmission
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy import func
from datetime import timedelta
import os
from werkzeug.utils import secure_filename
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.graph import report_app
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///tutor.db"
app.config["SECRET_KEY"] = "change-moi-plus-tard"

db.init_app(app)
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

with app.app_context():
    db.create_all()



correction_llm = ChatMistralAI(model="mistral-small-latest")

REFORMULATION_PROMPT = """Tu rédiges une correction d'exercice de maths, à partir de notes brutes
dictées par le professeur. Ce texte sera lu directement par l'élève.

Règles strictes :
- Tutoie l'élève ("tu"), jamais "vous".
- Écris UNIQUEMENT le texte de la correction, rien d'autre. Ne parle jamais au professeur,
  ne propose jamais d'affiner quoi que ce soit.
- Reste concis : reformule seulement ce que le professeur a dit. Pas d'intro, pas de conclusion générique.
- N'ajoute AUCUNE information mathématique que le professeur n'a pas mentionnée.
- Pas d'emoji, pas de "N'hésite pas à...", pas de formules de politesse artificielles.
- Si plusieurs erreurs distinctes sont mentionnées, une ligne par erreur. Sinon, un court paragraphe suffit."""

def structurer_correction(texte_brut):
    messages = [SystemMessage(content=REFORMULATION_PROMPT), HumanMessage(content=texte_brut)]
    reponse = correction_llm.invoke(messages)
    return reponse.content

def compute_student_stats(student_id):
    now = datetime.utcnow()
    today = now.date()

    today_count = ReviewLog.query.filter(
        ReviewLog.student_id == student_id,
        func.date(ReviewLog.reviewed_at) == today
    ).count()

    last_review = (
        ReviewLog.query.filter_by(student_id=student_id)
        .order_by(ReviewLog.reviewed_at.desc())
        .first()
    )
    days_since_last = (now - last_review.reviewed_at).days if last_review else None

    total_reviews = ReviewLog.query.filter_by(student_id=student_id).count()
    success_reviews = ReviewLog.query.filter(
        ReviewLog.student_id == student_id,
        ReviewLog.quality.in_(["good", "easy"])
    ).count()
    success_rate = round(success_reviews / total_reviews * 100) if total_reviews else None

    # Heatmap : 30 derniers jours
    start_date = datetime.combine(today - timedelta(days=29), datetime.min.time())
    daily = (
        db.session.query(
            func.date(ReviewLog.reviewed_at).label("day"),
            func.count(ReviewLog.id).label("count")
        )
        .filter(ReviewLog.student_id == student_id, ReviewLog.reviewed_at >= start_date)
        .group_by("day")
        .all()
    )
    counts_by_day = {str(d.day): d.count for d in daily}
    heatmap = []
    for i in range(29, -1, -1):
        day = today - timedelta(days=i)
        heatmap.append({"date": day, "count": counts_by_day.get(str(day), 0)})

    # Taux de réussite par chapitre
    logs = (
        db.session.query(ReviewLog.quality, Card.chapter)
        .join(Card, Card.id == ReviewLog.card_id)
        .filter(ReviewLog.student_id == student_id)
        .all()
    )
    totals, successes = {}, {}
    for quality, chapter in logs:
        totals[chapter] = totals.get(chapter, 0) + 1
        if quality in ("good", "easy"):
            successes[chapter] = successes.get(chapter, 0) + 1
    chapters = [
        {"chapter": ch, "total": t, "rate": round(successes.get(ch, 0) / t * 100)}
        for ch, t in totals.items()
    ]

    return {
        "today_count": today_count,
        "days_since_last": days_since_last,
        "success_rate": success_rate,
        "total_reviews": total_reviews,
        "heatmap": heatmap,
        "chapters": chapters,
    }
def format_interval(delta):
    minutes = delta.total_seconds() / 60
    if minutes < 60:
        return f"{int(minutes)} min"
    if minutes < 24 * 60:
        return f"{int(minutes // 60)} h"
    days = delta.days
    if days < 30:
        return f"{days} j"
    return f"{round(days / 30)} mois"


def preview_intervals(state):
    ease = state.ease_factor if state else 2.5
    interval = state.interval_days if state else 0

    good_interval = 1 if interval == 0 else round(interval * ease)
    easy_interval = 4 if interval == 0 else round(interval * (ease + 0.15) * 1.3)

    return {
        "again": format_interval(timedelta(minutes=1)),
        "hard": format_interval(timedelta(minutes=10)),
        "good": format_interval(timedelta(days=good_interval)),
        "easy": format_interval(timedelta(days=easy_interval)),
    }
def apply_sm2(state, quality):
    now = datetime.utcnow()

    if quality == "again":
        state.repetitions = 0
        state.interval_days = 0
        state.ease_factor = max(1.3, state.ease_factor - 0.2)
        next_review = now + timedelta(minutes=1)

    elif quality == "hard":
        state.repetitions += 1
        state.ease_factor = max(1.3, state.ease_factor - 0.15)
        next_review = now + timedelta(minutes=10)

    elif quality == "good":
        state.repetitions += 1
        state.interval_days = 1 if state.interval_days == 0 else round(state.interval_days * state.ease_factor)
        next_review = now + timedelta(days=state.interval_days)

    elif quality == "easy":
        state.repetitions += 1
        state.ease_factor += 0.15
        state.interval_days = 4 if state.interval_days == 0 else round(state.interval_days * state.ease_factor * 1.3)
        next_review = now + timedelta(days=state.interval_days)

    state.next_review_date = next_review
    state.last_reviewed_at = now
@app.route("/")
def home():
    
        if "student_id" in session:
            return redirect(url_for("dashboard"))
        return render_template("home.html")


@app.route("/login", methods=["POST"])
def login():
    name = request.form["full_name"]
    student = Student.query.filter_by(full_name=name).first()
    if student is None:
        student = Student(full_name=name, email=f"{name.lower()}@exemple.com")
        db.session.add(student)
        db.session.commit()
    session["student_id"] = student.id
    session["student_name"] = student.full_name
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    if "student_id" not in session:
        return redirect(url_for("home"))
    sid = session["student_id"]
    now = datetime.utcnow()

    cards_due = 0
    for card in Card.query.filter_by(student_id=sid).all():
        state = StudentCardState.query.filter_by(student_id=sid, card_id=card.id).first()
        if state is None or state.next_review_date <= now:
            cards_due += 1

    exercises_todo = 0
    for exo in Exercise.query.filter_by(student_id=sid).all():
        last_sub = (ExerciseSubmission.query.filter_by(exercise_id=exo.id, student_id=sid)
                    .order_by(ExerciseSubmission.submitted_at.desc()).first())
        if last_sub is None or last_sub.status in ("a_revoir", "petite_erreur"):
            exercises_todo += 1

    return render_template("dashboard.html", cards_due=cards_due, exercises_todo=exercises_todo)
    return render_template("dashboard.html", cards_due=cards_due, exercises_todo=exercises_todo)
@app.route("/review")
def review_cards():
    if "student_id" not in session:
        return redirect(url_for("home"))
    sid = session["student_id"]
    now = datetime.utcnow()

    due_card, due_state = None, None
    for card in Card.query.filter_by(student_id=sid).all():
        state = StudentCardState.query.filter_by(student_id=sid, card_id=card.id).first()
        if state is None or state.next_review_date <= now:
            due_card, due_state = card, state
            break

    if due_card is None:
        return render_template("review_done.html")

    intervals = preview_intervals(due_state)
    return render_template("review_card.html", card=due_card, intervals=intervals)

@app.route("/teacher")
def teacher_dashboard():
    students = Student.query.all()
    summary, inactive = [], []

    for student in students:
        stats = compute_student_stats(student.id)
        summary.append({"student": student, **stats})
        if stats["today_count"] == 0:
            inactive.append(student.full_name)

    return render_template("teacher_dashboard.html", summary=summary, inactive_students=inactive)


@app.route("/teacher/student/<int:student_id>")
def teacher_student_detail(student_id):
    student = Student.query.get_or_404(student_id)
    stats = compute_student_stats(student_id)

    now = datetime.utcnow()
    late_cards = []
    for card in Card.query.filter_by(student_id=student_id).all():
        state = StudentCardState.query.filter_by(student_id=student_id, card_id=card.id).first()
        if state is None or state.next_review_date <= now:
            late_cards.append(card)

    return render_template("teacher_student_detail.html", student=student, stats=stats, late_cards=late_cards)
@app.route("/teacher/student/<int:student_id>/report")
def generate_report(student_id):
    student = Student.query.get_or_404(student_id)

    state_ini = {
        "student_id": student.id,
        "student_name": student.full_name,
        "cards_stats": {},
        "exercises_stats": {},
        "rapport_final": "",
    }

    result = report_app.invoke(state_ini)

    return render_template("student_report.html", student=student, rapport=result["rapport_final"])

@app.route("/teacher/submissions")
def teacher_submissions():
    pending = (ExerciseSubmission.query.filter_by(status="pending")
               .order_by(ExerciseSubmission.submitted_at.asc()).all())
    rows = []
    for s in pending:
        rows.append({
            "submission": s,
            "student": Student.query.get(s.student_id),
            "exercise": Exercise.query.get(s.exercise_id),
        })
    return render_template("teacher_submissions.html", rows=rows)


@app.route("/teacher/submissions/<int:submission_id>", methods=["GET", "POST"])
def teacher_submission_detail(submission_id):
    submission = ExerciseSubmission.query.get_or_404(submission_id)
    exercise = Exercise.query.get(submission.exercise_id)
    student = Student.query.get(submission.student_id)

    if request.method == "POST":
        action = request.form["action"]

        if action == "a_revoir":
            submission.status = "a_revoir"
            submission.feedback_text = structurer_correction(request.form["feedback_raw"])
            submission.grade = None

        elif action == "petite_erreur":
            submission.status = "petite_erreur"
            submission.feedback_text = structurer_correction(request.form["feedback_raw"])
            submission.grade = int(request.form["grade"])

        elif action == "reussi":
            submission.status = "reussi"
            submission.grade = int(request.form["grade"])
            submission.feedback_text = None

        db.session.commit()
        return redirect(url_for("teacher_submissions"))

    return render_template("teacher_submission_detail.html",
                            submission=submission, exercise=exercise, student=student)
@app.route("/cards")
def cards_list():
    if "student_id" not in session:
        return redirect(url_for("home"))
    sid = session["student_id"]
    all_cards = Card.query.filter_by(student_id=sid).all()

    grouped = {}
    for card in all_cards:
        grouped.setdefault(card.chapter, []).append(card)

    return render_template("cards.html", grouped=grouped)

@app.route("/cards/<int:card_id>/delete", methods=["POST"])
def delete_card(card_id):
    if "student_id" not in session:
        return redirect(url_for("home"))
    card = Card.query.get_or_404(card_id)
    if card.student_id != session["student_id"]:
        return redirect(url_for("cards_list"))

    StudentCardState.query.filter_by(card_id=card_id).delete()
    ReviewLog.query.filter_by(card_id=card_id).delete()
    db.session.delete(card)
    db.session.commit()
    return redirect(url_for("cards_list"))
@app.route("/cards/new", methods=["GET", "POST"])
def add_card():
    if "student_id" not in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        card = Card(
            student_id=session["student_id"],
            question=request.form["question"],
            answer=request.form["answer"],
            chapter=request.form.get("chapter"),
        )
        db.session.add(card)
        db.session.commit()
        return redirect(url_for("cards_list"))

    chapters = [c[0] for c in db.session.query(Card.chapter)
                .filter_by(student_id=session["student_id"]).distinct().all()]
    return render_template("add_card.html", chapters=chapters)


@app.route("/cards/<int:card_id>/edit", methods=["GET", "POST"])
def edit_card(card_id):
    card = Card.query.get_or_404(card_id)
    if card.student_id != session.get("student_id"):
        return redirect(url_for("cards_list"))

    if request.method == "POST":
        card.question = request.form["question"]
        card.answer = request.form["answer"]
        card.chapter = request.form.get("chapter")
        db.session.commit()
        return redirect(url_for("cards_list"))

    chapters = [c[0] for c in db.session.query(Card.chapter)
                .filter_by(student_id=session["student_id"]).distinct().all()]
    return render_template("edit_card.html", card=card, chapters=chapters)


@app.route("/cards/<int:card_id>/review", methods=["POST"])
def review_card(card_id):
    quality = request.form["quality"]
    card = Card.query.get_or_404(card_id)
    if card.student_id != session.get("student_id"):
        return redirect(url_for("dashboard"))

    state = StudentCardState.query.filter_by(
        student_id=session["student_id"], card_id=card_id
    ).first()
    if state is None:
        state = StudentCardState(
            student_id=session["student_id"], card_id=card_id,
            ease_factor=2.5, interval_days=0, repetitions=0,
        )
        db.session.add(state)

    apply_sm2(state, quality)
    db.session.add(ReviewLog(student_id=session["student_id"], card_id=card_id, quality=quality))
    db.session.commit()
    return redirect(url_for("review_cards"))
@app.route("/exercises/new", methods=["GET", "POST"])
def add_exercise():
    if "student_id" not in session:
        return redirect(url_for("home"))
    if request.method == "POST":
        exo = Exercise(
            student_id=session["student_id"],
            statement=request.form["statement"],
            chapter=request.form.get("chapter"),
            reference_answer=request.form.get("reference_answer"),
        )
        db.session.add(exo)
        db.session.commit()
        return redirect(url_for("dashboard"))
    return render_template("add_exercise.html")


@app.route("/exercises")
def review_exercises():
    if "student_id" not in session:
        return redirect(url_for("home"))
    sid = session["student_id"]

    next_exo = None
    last_submission = None
    for exo in Exercise.query.filter_by(student_id=sid).all():
        sub = (ExerciseSubmission.query.filter_by(exercise_id=exo.id, student_id=sid)
               .order_by(ExerciseSubmission.submitted_at.desc()).first())
        if sub is None or sub.status in ("a_revoir", "petite_erreur"):
            next_exo = exo
            last_submission = sub if sub and sub.status in ("a_revoir", "petite_erreur") else None
            break

    if next_exo is None:
        return render_template("exercises_done.html")
    return render_template("exercise_page.html", exercise=next_exo, last_submission=last_submission)

@app.route("/exercises/<int:exercise_id>/submit", methods=["POST"])
def submit_exercise(exercise_id):
    if "student_id" not in session:
        return redirect(url_for("home"))

    exercise = Exercise.query.get_or_404(exercise_id)
    if exercise.student_id != session["student_id"]:
        return redirect(url_for("review_exercises"))

    photo = request.files["photo"]
    filename = secure_filename(f"{session['student_id']}_{exercise_id}_{int(datetime.utcnow().timestamp())}.jpg")
    photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    db.session.add(ExerciseSubmission(
        exercise_id=exercise_id, student_id=session["student_id"],
        photo_path=filename, status="pending",
    ))
    db.session.commit()
    return redirect(url_for("review_exercises"))

    db.session.commit()
    return redirect(url_for("review_chapter", chapter=chapter))
@app.route("/chapters")
def chapters_list():
    if "student_id" not in session:
        return redirect(url_for("home"))

    chapters = [c[0] for c in db.session.query(Card.chapter)
                .filter_by(student_id=session["student_id"]).distinct().all()]
    now = datetime.utcnow()

    due_counts = {}
    for chapter in chapters:
        cards = Card.query.filter_by(chapter=chapter, student_id=session["student_id"]).all()
        due = 0
        for card in cards:
            state = StudentCardState.query.filter_by(
                student_id=session["student_id"], card_id=card.id
            ).first()
            if state is None or state.next_review_date <= now:
                due += 1
        due_counts[chapter] = due

    return render_template("chapters.html", due_counts=due_counts)


@app.route("/chapters/<chapter>/review")
def review_chapter(chapter):
    if "student_id" not in session:
        return redirect(url_for("home"))

    now = datetime.utcnow()
    cards = Card.query.filter_by(chapter=chapter, student_id=session["student_id"]).all()

    due_card = None
    due_state = None
    for card in cards:
        state = StudentCardState.query.filter_by(
            student_id=session["student_id"], card_id=card.id
        ).first()
        if state is None or state.next_review_date <= now:
            due_card = card
            due_state = state
            break

    if due_card is None:
        return render_template("review_done.html", chapter=chapter)

    intervals = preview_intervals(due_state)
    return render_template("review_card.html", card=due_card, chapter=chapter, intervals=intervals)
@app.route("/logout")
def logout():
    session.pop("student_id", None)
    return redirect(url_for("home"))
if __name__ == "__main__":
    app.run(debug=True)