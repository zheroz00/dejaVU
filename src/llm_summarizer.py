import google.generativeai as genai
import json
import os
from .paths import get_config_path, get_api_key, LOG_FILE

# --- API Configuration ---
# API key is stored in ~/.dejavu/settings.json as gemini_api_key
# Falls back to GEMINI_API_KEY environment variable for backward compatibility
API_KEY = get_api_key()
# -------------------------

LOG_FILE_PATH = get_config_path(LOG_FILE)
# We'll look at the last 15 entries for context
# We'll look at the last 50 entries for context (approx 1-2 minutes of active switching)
ENTRIES_TO_SUMMARIZE = 50

# Configure the API client
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash') # Good and fast model

def get_summary():
    """
    Reads the log, formats a prompt, and asks the LLM to summarize.
    """
    # 1. Read the activity log
    try:
        with open(LOG_FILE_PATH, 'r') as f:
            log_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return "Error: Could not read log file."

    if not log_data:
        return "Log file is empty. No activity to summarize."

    # 2. Get the most recent entries
    recent_entries = log_data[:ENTRIES_TO_SUMMARIZE]
    recent_entries.reverse() # Reverse to be in chronological order

    # 3. Format the entries into a simple list for the prompt
    activity_list_str = ""
    for entry in recent_entries:
        # e.g., "[14:25:30] chrome.exe: Google Search"
        # We assume timestamp is in 'YYYY-MM-DD HH:MM:SS' format, we just want time for context
        ts = entry.get('timestamp', '')
        time_str = ts.split(' ')[-1] if ' ' in ts else ts
        activity_list_str += f"- [{time_str}] {entry['process']}: {entry['title']}\n"
    
    # 4. Create the prompt
    prompt = f"""
    You are a smart activity summarizer.
    A user's recent computer activity is listed below (chronological).
    
    Goal: Summarize what the user was working on.
    
    Instructions:
    1.  **Main Task**: In one clear sentence, verify what the primary goal appears to be.
    2.  **Breakdown**: details of what they did, using the timestamps to estimate duration if possible.
    
    Output Format:
    **Current Focus**: [Short description of the main task]
    
    **Details**:
    - [Activity 1]
    - [Activity 2]
    
    Recent Activity Log:
    {activity_list_str}
    
    Summary:
    """

    # 5. Call the LLM and return the response
    try:
        print("Sending prompt to LLM...") # Feedback for your terminal
        response = model.generate_content(prompt)
        print("...Got summary.")
        return response.text.strip()
        
    except Exception as e:
        print(f"Error calling LLM: {e}")
        # This will show API key errors, etc.
        return f"Error: Could not connect to LLM. {e}"

if __name__ == "__main__":
    # Lets you test this file directly
    # Run: python llm_summarizer.py
    print(get_summary())