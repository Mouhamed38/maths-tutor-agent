from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    full_name = db.Column(db.String(255))

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    chapter = db.Column(db.String(255))

class StudentCardState(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("card.id"), nullable=False)

    ease_factor = db.Column(db.Float, default=2.5)
    interval_days = db.Column(db.Integer, default=0)
    repetitions = db.Column(db.Integer, default=0)
    next_review_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_reviewed_at = db.Column(db.DateTime, default=datetime.utcnow)
class ReviewLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey("card.id"), nullable=False)
    quality = db.Column(db.String(10))
    reviewed_at = db.Column(db.DateTime, default=datetime.utcnow)
class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    chapter = db.Column(db.String(255))
    statement = db.Column(db.Text, nullable=False)
    reference_answer = db.Column(db.Text)  # note pour toi seulement, pas pour correction auto

class ExerciseSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exercise_id = db.Column(db.Integer, db.ForeignKey("exercise.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    photo_path = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / a_revoir / petite_erreur / reussi
    grade = db.Column(db.Integer)  # note sur 20, seulement si petite_erreur ou reussi
    feedback_text = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)