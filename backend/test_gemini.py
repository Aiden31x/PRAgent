"""Step 2 — Gemini API test.

Sends the real system prompt from prompts.py with a hardcoded fake diff
to Gemini and confirms it returns a properly structured THOUGHT / ACTION /
REVIEW_COMPLETE response.

Prerequisites:
  - GEMINI_API_KEY set in .env (free key from https://aistudio.google.com/apikey)

Usage:
  cd backend
  ../venv/bin/python test_gemini.py
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY", "")
if not api_key:
    print("ERROR: GEMINI_API_KEY not set in .env — get one at https://aistudio.google.com/apikey")
    sys.exit(1)

from google import genai
from google.genai import types

from app.agent.prompts import SYSTEM_PROMPT, build_first_user_message

client = genai.Client(api_key=api_key)

# ---------------------------------------------------------------------------
# Hardcoded fake PR context — SQL injection on purpose so the model has
# something meaningful to flag.
# ---------------------------------------------------------------------------
FAKE_DIFF = """\
diff --git a/auth/login.py b/auth/login.py
index abc123..def456 100644
--- a/auth/login.py
+++ b/auth/login.py
@@ -10,7 +10,10 @@ def login(request):
     username = request.form["username"]
     password = request.form["password"]
-    user = db.query(User).filter_by(username=username).first()
+    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
+    user = db.engine.execute(query).first()
     if user:
         session["user_id"] = user.id
         return redirect("/dashboard")
"""

first_user_msg = build_first_user_message(
    owner="acme",
    repo="api",
    pr_number=42,
    pr_title="Switch login to raw SQL for performance",
    pr_description="Replaces ORM query with raw SQL for faster login.",
    base_branch="main",
    head_branch="feature/raw-sql-login",
    changed_files=["auth/login.py"],
)

chat = client.chats.create(
    model="gemini-2.0-flash",
    config=types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
    ),
)

# ---------------------------------------------------------------------------
# Turn 1 — send PR context; expect THOUGHT or ACTION
# ---------------------------------------------------------------------------
print("=" * 60)
print("TURN 1  → sending PR context")
print("=" * 60)
resp1 = chat.send_message(first_user_msg)
print(resp1.text)

# ---------------------------------------------------------------------------
# Turn 2 — inject a fake OBSERVATION (the diff) as if the MCP tool responded
# ---------------------------------------------------------------------------
observation = f"OBSERVATION:\n{FAKE_DIFF}"
print("\n" + "=" * 60)
print("TURN 2  → injecting fake diff as OBSERVATION")
print("=" * 60)
resp2 = chat.send_message(observation)
print(resp2.text)

# ---------------------------------------------------------------------------
# Turn 3 — inject the file contents the model probably asked for
# ---------------------------------------------------------------------------
fake_file = """\
OBSERVATION:
# auth/login.py — full file
from flask import request, session, redirect
from app.models import User
from app import db

def login(request):
    if request.method != "POST":
        return render_template("login.html")
    username = request.form["username"]
    password = request.form["password"]
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    user = db.engine.execute(query).first()
    if user:
        session["user_id"] = user.id
        return redirect("/dashboard")
    return render_template("login.html", error="Invalid credentials")
"""

print("\n" + "=" * 60)
print("TURN 3  → injecting fake file contents")
print("=" * 60)
resp3 = chat.send_message(fake_file)
print(resp3.text)

# ---------------------------------------------------------------------------
# Turn 4+ — keep going until REVIEW_COMPLETE or 3 more turns
# ---------------------------------------------------------------------------
all_texts = [resp1.text or "", resp2.text or "", resp3.text or ""]

for i in range(4, 7):
    if "REVIEW_COMPLETE" in all_texts[-1]:
        break
    nudge = (
        "OBSERVATION: No additional files changed. "
        "You have reviewed all changed files. Please conclude your review."
    )
    print(f"\n{'=' * 60}")
    print(f"TURN {i}  → nudging toward conclusion")
    print("=" * 60)
    resp = chat.send_message(nudge)
    print(resp.text)
    all_texts.append(resp.text or "")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
combined = "\n".join(all_texts)
has_thought = "THOUGHT:" in combined
has_action = "ACTION:" in combined
has_complete = "REVIEW_COMPLETE" in combined

print("\n" + "=" * 60)
print("VALIDATION SUMMARY")
print("=" * 60)
print(f"  Saw THOUGHT?          {'yes' if has_thought else 'NO — check prompt'}")
print(f"  Saw ACTION?           {'yes' if has_action else 'NO — check prompt'}")
print(f"  Saw REVIEW_COMPLETE?  {'yes' if has_complete else 'NO — may need more turns'}")

if has_complete:
    print("\nGemini API test passed — prompt produces the expected ReAct format.")
else:
    print("\nREVIEW_COMPLETE not seen yet. The model may need more turns.")
    print("But if you saw THOUGHT and ACTION in the right format, the prompt works.")
