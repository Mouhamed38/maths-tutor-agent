from src.graph import app
from src.state import TutorState
from dotenv import load_dotenv
import os

load_dotenv()
print(os.getenv("MISTRAL_API_KEY"))
state_ini={'card_question': 'Résous 3x + 5 = 11',
    'card_answer': 'x = 2',
    'message_eleve': 'Je ne sais plus comment commencer',
    'question_eleve':'Comment resoudre une equation du 1er degres','reponse_ia':""}


state_ini=app.invoke(state_ini)

print(state_ini['reponse_ia'])

