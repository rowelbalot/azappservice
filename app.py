import json
import os

import requests
from flask import Flask, jsonify, render_template, request

from tools import TOOLS, execute_tool

app = Flask(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = [
    {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
    {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku"},
    {"id": "openai/gpt-4o", "name": "GPT-4o"},
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini"},
    {"id": "google/gemini-flash-1.5", "name": "Gemini Flash 1.5"},
    {"id": "meta-llama/llama-3.1-8b-instruct", "name": "Llama 3.1 8B"},
    {"id": "mistralai/mistral-7b-instruct", "name": "Mistral 7B"},
]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/models")
def list_models():
    return jsonify({"models": MODELS})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    messages = data.get("messages", [])
    model = data.get("model", "anthropic/claude-3.5-sonnet")

    if not messages:
        return jsonify({"error": "messages is required"}), 400

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return jsonify({"error": "OPENROUTER_API_KEY environment variable is not set"}), 500

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": request.host_url,
        "X-Title": "AI Chat App",
    }

    tool_calls_made = []

    for _ in range(10):
        payload = {
            "model": model,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
        }

        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as exc:
            return jsonify({"error": f"OpenRouter API error: {exc}"}), 502

        result = resp.json()

        if "error" in result:
            msg = result["error"]
            err_text = msg.get("message", str(msg)) if isinstance(msg, dict) else str(msg)
            return jsonify({"error": err_text}), 502

        choice = result["choices"][0]
        assistant_msg = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")

        messages.append(assistant_msg)

        if finish_reason == "tool_calls":
            for call in assistant_msg.get("tool_calls", []):
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_result = execute_tool(name, args)
                tool_calls_made.append({"name": name, "args": args, "result": tool_result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": tool_result,
                })
        else:
            return jsonify({
                "content": assistant_msg.get("content", ""),
                "messages": messages,
                "tool_calls": tool_calls_made,
            })

    return jsonify({"error": "Max tool call iterations reached"}), 500
