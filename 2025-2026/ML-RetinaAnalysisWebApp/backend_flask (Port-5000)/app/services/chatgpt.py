# app/services/chat_service.py

import os, openai
from dotenv import load_dotenv
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"  
load_dotenv(dotenv_path=env_path)
openai.api_key = os.getenv("OPENAI_API_KEY")

SYSTEM_PROMPT = """
You are a medical advisor for RetinaAnalysis, a prototype platform that predicts retinopathy from an input image.
Your role is to provide accurate, informative explanations of the diagnosed pathology and to offer general advice.
Always include a clear disclaimer that this is a prototype for presentation only, that it is not providing true medical advice,
and that no prediction or diagnosis has been verified by a medical professional. Your tone is reassuring and friendly.
"""

def ask_chatgpt(user_message, history=None, diagnosed=None):
    if diagnosed == None :
        diagnosis = "User Diagnonsis can be found in most recent message from role Advisor in the history, there isn't any mentioned it's not yet diagnosed "
    else :
        diagnosis = diagnosed
    """
    user_message: string of the user’s latest query
    history: optional list of prior messages (each a dict with 'role' and 'content')
    Returns the assistant’s reply text.
    """
    #print("OPEN AI KEY :::::: ",env_path)
    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT.strip()}. {diagnosis}"}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=500
    )
    return resp.choices[0].message.content
