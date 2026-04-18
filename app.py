import os
import json
import base64
import flask
from flask_cors import CORS
import google.generativeai as genai
import uuid

sessions = {}
import random


os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

from dotenv import load_dotenv
load_dotenv()

app = flask.Flask(__name__, template_folder="templates")
CORS(app)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
print("API KEY:", GOOGLE_API_KEY)
genai.configure(
    api_key=GOOGLE_API_KEY,
    transport="rest"
)

model = genai.GenerativeModel("gemini-2.5-flash")

@app.route("/")
def index():
    return flask.render_template("index.html")

@app.route('/start-session', methods=['GET'])
def start_session():
    session_id = str(uuid.uuid4())

    sessions[session_id] = {
        "eye": 0.0,
        "expression": 0.0,
        "gesture": 0.0,
        "frames": 0
    }

    return flask.jsonify({"session_id": session_id})

@app.route('/update-nonverbal', methods=['POST'])
def update_nonverbal():
    data = flask.request.get_json()
    session_id = data.get("session_id")

    if session_id not in sessions:
        return flask.jsonify({"error": "Invalid session"}), 400

    s = sessions[session_id]

    s["eye"] += float(data.get("eye_contact", 0))
    s["gesture"] += float(data.get("gesture", 0))
    s["expression"] += float(data.get("expression", 0))
    s["frames"] += 1

    return flask.jsonify({"status": "updated"})

@app.route("/generate", methods=["POST"])
def generate():
    print("🔥 /generate called")
    try:
        data = flask.request.get_json()
        job_description = data.get("job_description", "")

        prompt = f"""
        You are an expert HR interviewer.
        Generate exactly 4 interview questions:
        - 2 general HR questions
        - 2 job-specific questions based on the following job description.

        Job Description:
        {job_description}

        Return only the questions in a numbered list format:
        1. ...
        2. ...
        3. ...
        4. ...
        """

        print("⏳ Calling Gemini...")
        response = model.generate_content(prompt)
        print("RESPONSE:", response)

        raw_text = ""

        if hasattr(response, "text") and response.text:
            raw_text = response.text
        elif hasattr(response, "candidates") and response.candidates:
            parts = response.candidates[0].content.parts
            if parts and hasattr(parts[0], "text"):
                raw_text = parts[0].text

        questions_text = raw_text.strip()

        questions = []
        for line in questions_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line[0].isdigit() and ('.' in line[:4]):
                parts = line.split('.', 1)
                question = parts[1].strip() if len(parts) > 1 else line
            else:
                question = line
            questions.append(question)

        return flask.jsonify({"questions": questions})

    except Exception as e:
        print("❌ GENERATE ERROR:", e)
        return flask.jsonify({"error": str(e)}), 500



@app.route("/evaluate", methods=["POST"])
def evaluate():
    try:
        data = flask.request.get_json()
        question = data.get("question", "")
        answer = data.get("answer", "")
        session_id = data.get("session_id")

        if not question or not answer:
            return flask.jsonify({"error": "Missing question or answer"}), 400

        # -------- NON-VERBAL FROM SESSION --------
        
        s = sessions.get(session_id)

        if s and s["frames"] > 0:
            eye = s["eye"] / s["frames"]
            gesture = s["gesture"] / s["frames"]

            nonverbal_scores = {
                "Eye Contact": round(eye, 1),
                "Hand Movement": round(gesture, 1),
                "Facial Expression": 7  # temp for now
            }
        else:
            nonverbal_scores = {
                "Eye Contact": 5,
                "Hand Movement": 5,
                "Facial Expression": 5
            }

        eye_score = nonverbal_scores["Eye Contact"]
        gesture_score = nonverbal_scores["Hand Movement"]
        expression_score = nonverbal_scores["Facial Expression"]


        prompt = f"""
        You are an expert interview evaluator.

        Evaluate the candidate primarily based on VERBAL performance.

        Also consider NON-VERBAL behavior using the given scores.

        VERBAL PARAMETERS:
        - Clarity
        - Relevance
        - Structure
        - Confidence
        - Technical Depth
        - Example Quality
        - Conciseness

        NON-VERBAL SCORES:
        - Eye Contact: {eye_score}/10
        - Hand Movement: {gesture_score}/10
        - Facial Expression: {expression_score}/10

        INSTRUCTIONS:
        - Give MOST focus to verbal evaluation.
        - In the summary, include ONLY 1–2 short lines about non-verbal behavior.
        - Keep non-verbal feedback concise and natural.
        - In improvement tips, include at most 1 tip related to non-verbal behavior.

        Return ONLY valid JSON in this format:
        {{
        "verbal_scores": {{
            "Clarity": 0,
            "Relevance": 0,
            "Structure": 0,
            "Confidence": 0,
            "Technical Depth": 0,
            "Example Quality": 0,
            "Conciseness": 0
        }},
        "summary": "3-4 sentence summary including 1 short line on non-verbal behavior",
        "improvement_tips": [
            "tip 1",
            "tip 2",
            "tip 3"
        ]
        }}

        Question: {question}
        Answer: {answer}
        """

        response = model.generate_content(prompt)
        raw_text = getattr(response, "text", "")
        cleaned = raw_text.strip().replace("```json", "").replace("```", "")
        json_part = cleaned[cleaned.find("{"): cleaned.rfind("}") + 1]

        try:
            evaluation = json.loads(json_part)
        except Exception:
            evaluation = {"verbal_scores": {}, "summary": "", "improvement_tips": []}

        # ✅ Extract verbal scores
        verbal_scores = evaluation.get("verbal_scores", {})
        

        
        # ✅ Combine both
        all_scores = {**verbal_scores, **nonverbal_scores}

        # ✅ Calculate total
        total = sum(all_scores.values())

        # ✅ Final response
        return flask.jsonify({
            "evaluation": {
                "scores": all_scores,
                "total": total,
                "summary": evaluation.get("summary", ""),
                "improvement_tips": evaluation.get("improvement_tips", [])
            }
        })

    except Exception as e:
        return flask.jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
