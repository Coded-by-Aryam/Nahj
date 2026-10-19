"""
NAHJ AI Service — 8 AI Functions powered by OpenAI LLM + JSON Knowledge Base
"""

import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
MODEL = "gpt-4o-mini"

# ============================================================
# LOAD KNOWLEDGE BASES
# ============================================================

KB_DIR = os.path.join(os.path.dirname(__file__), 'knowledge_base')

def load_kb(filename):
    path = os.path.join(KB_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

BEHAVIOR_KB = load_kb('behavior_kb.json')
STUDY_PATTERNS_KB = load_kb('study_patterns_kb.json')
RESOURCES_KB = load_kb('resources_kb.json')
RECOMMENDATIONS_KB = load_kb('recommendations_kb.json')
GROUPS_KB = load_kb('groups_kb.json')
PERFORMANCE_KB = load_kb('performance_kb.json')
REPORTS_KB = load_kb('reports_kb.json')

# ============================================================
# HELPER: Call OpenAI
# ============================================================

def detect_language(text):
    """Detect if the text is primarily Arabic or English by counting Arabic characters."""
    if not text:
        return 'en'
    arabic_chars = sum(1 for c in text if '؀' <= c <= 'ۿ' or 'ݐ' <= c <= 'ݿ')
    latin_chars = sum(1 for c in text if ('a' <= c.lower() <= 'z'))
    if arabic_chars == 0 and latin_chars == 0:
        return 'en'
    return 'ar' if arabic_chars >= latin_chars else 'en'


def language_instruction(lang):
    """Build a system instruction telling the model which language to respond in."""
    if lang == 'ar':
        return (
            "\n\nIMPORTANT: The user wrote in Arabic. Respond ENTIRELY in Modern Standard Arabic. "
            "All headings, lists, and explanations must be in Arabic. Do not mix English."
        )
    return (
        "\n\nIMPORTANT: The user wrote in English. Respond ENTIRELY in English. "
        "All headings, lists, and explanations must be in English. Do not mix Arabic."
    )

def call_llm(system_prompt, user_prompt, temperature=0.7, lang='ar'):
    """Call OpenAI LLM with system and user prompts, responding in the given language."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": language_instruction(lang) + "\n\n" + system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {str(e)}"

# ============================================================
# FUNCTION 1: Analyze Behavior
# ============================================================

def analyze_behavior(student_data, lang='ar'):
    """
    Analyzes student study behavior and classifies their learning pattern.
    student_data: dict with keys like study_hours, completion_rate, consistency, total_tasks, etc.
    """
    system_prompt = f"""You are Nahj AI, an academic behavior analyst for university students.
Use this knowledge base to classify the student's behavior type and provide analysis:

{json.dumps(BEHAVIOR_KB, indent=2)}

Based on the student's data, you must:
1. Classify their behavior type (choose from the types in the knowledge base)
2. Explain why this classification fits
3. List their strengths
4. Identify risks
5. Provide specific, actionable advice

Format your response as:
**Behavior Type:** [type]
**Analysis:** [explanation]
**Strengths:** [list]
**Risks:** [list]  
**Advice:** [actionable recommendations]

Be encouraging but honest. Use a supportive tone."""

    user_prompt = f"""Analyze this student's behavior:
- Total Study Hours (this period): {student_data.get('total_hours', 0)}
- Average Daily Hours: {student_data.get('avg_daily_hours', 0)}
- Task Completion Rate: {student_data.get('completion_rate', 0)}%
- Total Tasks: {student_data.get('total_tasks', 0)}
- Completed Tasks: {student_data.get('completed_tasks', 0)}
- Pending Tasks: {student_data.get('pending_tasks', 0)}
- Consistency Score: {student_data.get('consistency_score', 0)}%
- Groups Joined: {student_data.get('groups_joined', 0)}
- Learning Style: {student_data.get('learning_style', 'not set')}
- Department: {student_data.get('department', 'not set')}
- Level: {student_data.get('level', 1)}"""

    return call_llm(system_prompt, user_prompt, lang=lang)

# ============================================================
# FUNCTION 2: Recommend Study Pattern
# ============================================================

def recommend_study_pattern(student_data, lang='ar'):
    """
    Recommends best study patterns based on student's learning style and schedule.
    """
    system_prompt = f"""You are Nahj AI, a study pattern advisor for university students.
Use this knowledge base of study techniques and patterns:

{json.dumps(STUDY_PATTERNS_KB, indent=2)}

Recommend 2-3 study patterns that best fit the student's profile.
For each recommendation, explain:
1. The technique name and how it works
2. Why it suits this specific student
3. A step-by-step guide to start using it
4. When to use it (which courses or situations)

Format your response clearly with each recommendation as a numbered section.
Be practical and specific. Include timing suggestions."""

    user_prompt = f"""Recommend study patterns for this student:
- Learning Style: {student_data.get('learning_style', 'not set')}
- Behavior Type: {student_data.get('behavior_type', 'unknown')}
- Available Study Hours/Day: {student_data.get('available_hours', 4)}
- Number of Enrolled Courses: {student_data.get('enrolled_courses', 0)}
- Courses: {student_data.get('course_names', 'not specified')}
- Current Completion Rate: {student_data.get('completion_rate', 0)}%
- Main Challenge: {student_data.get('challenge', 'general improvement')}"""

    return call_llm(system_prompt, user_prompt, lang=lang)

# ============================================================
# FUNCTION 3: Recommend Resources
# ============================================================

def recommend_resources(student_data, lang='ar'):
    """
    Suggests learning resources based on courses and learning style.
    """
    system_prompt = f"""You are Nahj AI, a learning resource advisor for university students.
Use this comprehensive resource database:

{json.dumps(RESOURCES_KB, indent=2)}

Based on the student's enrolled courses and learning style, recommend the most relevant resources.
For each course, suggest 2-3 resources that match their learning style.

Format your response with course headers and resource details including:
- Resource name and type
- Why it's recommended for this student
- How to use it effectively
- URL/link

Also suggest 1-2 general resources that benefit all their courses."""

    user_prompt = f"""Recommend resources for this student:
- Learning Style: {student_data.get('learning_style', 'not set')}
- Enrolled Courses: {student_data.get('course_names', 'not specified')}
- Level: {student_data.get('level', 1)}
- Current Performance: {student_data.get('completion_rate', 0)}% completion rate
- Specific Need: {student_data.get('specific_need', 'general improvement')}"""

    return call_llm(system_prompt, user_prompt, lang=lang)

# ============================================================
# FUNCTION 4: Generate Recommendations (Hybrid)
# ============================================================

def generate_recommendations(student_data, lang='ar'):
    """
    Generates hybrid personalized recommendations combining behavior + resources + performance.
    """
    system_prompt = f"""You are Nahj AI, a comprehensive academic advisor for university students.
Use this knowledge base of recommendation rules and strategies:

{json.dumps(RECOMMENDATIONS_KB, indent=2)}

Generate a personalized recommendation report that combines:
1. Analysis of their current situation
2. Priority level (critical/high/moderate/low)
3. Top 5 specific action items
4. Relevant success strategies
5. A motivational message

Match the student to the most relevant recommendation rule from the knowledge base.
Be specific, actionable, and encouraging."""

    user_prompt = f"""Generate recommendations for this student:
- Study Hours/Week: {student_data.get('study_hours_weekly', 0)}
- Completion Rate: {student_data.get('completion_rate', 0)}%
- Consistency Score: {student_data.get('consistency_score', 0)}%
- Pending Tasks: {student_data.get('pending_tasks', 0)}
- Upcoming Deadlines: {student_data.get('upcoming_deadlines', 0)}
- Behavior Type: {student_data.get('behavior_type', 'unknown')}
- Learning Style: {student_data.get('learning_style', 'not set')}
- Courses: {student_data.get('course_names', 'not specified')}
- Recent Trend: {student_data.get('trend', 'stable')}"""

    return call_llm(system_prompt, user_prompt, lang=lang)

# ============================================================
# FUNCTION 5: Suggest Groups
# ============================================================

def suggest_groups(student_data, existing_groups, lang='ar'):
    """
    Suggests study groups the student should join based on compatibility.
    """
    system_prompt = f"""You are Nahj AI, a study group advisor for university students.
Use this knowledge base for group matching and suggestions:

{json.dumps(GROUPS_KB, indent=2)}

Based on the student's profile and available groups, suggest which groups they should join.
For each suggestion, explain:
1. Why this group is a good match
2. What the student will gain from joining
3. How to contribute to the group

If no existing groups are a good match, suggest creating a new group and recommend what type.
Also provide general group study tips."""

    groups_info = json.dumps(existing_groups, indent=2) if existing_groups else "No existing groups available"

    user_prompt = f"""Suggest study groups for this student:
- Department: {student_data.get('department', 'not set')}
- Level: {student_data.get('level', 1)}
- Learning Style: {student_data.get('learning_style', 'not set')}
- Enrolled Courses: {student_data.get('course_names', 'not specified')}
- Behavior Type: {student_data.get('behavior_type', 'unknown')}
- Current Groups Joined: {student_data.get('groups_joined', 0)}

Available Groups:
{groups_info}"""

    return call_llm(system_prompt, user_prompt, lang=lang)

# ============================================================
# FUNCTION 6: Match Group
# ============================================================

def match_group(student_data, existing_groups, lang='ar'):
    """
    Matches student to the best existing group using compatibility scoring.
    """
    system_prompt = f"""You are Nahj AI, a smart group matching system for university students.
Use this knowledge base for matching criteria:

{json.dumps(GROUPS_KB, indent=2)}

Match the student to the BEST group from the available groups.
Score each group on compatibility (out of 100) based on:
- Department match (30%)
- Level match (25%)
- Course overlap (25%)
- Learning style compatibility (20%)

Return results as a ranked list with:
1. Group name and compatibility score
2. Why this is a good/poor match
3. Your top recommendation with explanation

If no groups score above 40, recommend the student create their own group."""

    groups_info = json.dumps(existing_groups, indent=2) if existing_groups else "No groups available"

    user_prompt = f"""Match this student to the best group:
- Department: {student_data.get('department', 'not set')}
- Level: {student_data.get('level', 1)}
- Learning Style: {student_data.get('learning_style', 'not set')}
- Enrolled Courses: {student_data.get('course_names', 'not specified')}
- Study Hours/Day: {student_data.get('avg_daily_hours', 0)}

Available Groups:
{groups_info}"""

    return call_llm(system_prompt, user_prompt, lang=lang)

# ============================================================
# FUNCTION 7: Analyze Performance
# ============================================================

def analyze_performance(student_data, lang='ar'):
    """
    Analyzes academic performance and provides a score with detailed breakdown.
    """
    system_prompt = f"""You are Nahj AI, an academic performance analyst for university students.
Use this performance analysis knowledge base:

{json.dumps(PERFORMANCE_KB, indent=2)}

Calculate a performance score (0-100) based on the metrics and provide:
1. **Overall Score:** X/100 with performance level
2. **Metric Breakdown:** Score for each metric (study hours, completion rate, consistency, priority management)
3. **Trend:** Whether performance is improving, stable, or declining
4. **Key Insights:** 3 specific observations about their performance
5. **Recommendations:** Top 3 actions to improve

Be data-driven and specific. Reference actual numbers from the student's data."""

    user_prompt = f"""Analyze this student's performance:
- Study Hours This Week: {student_data.get('study_hours_weekly', 0)}
- Total Study Hours: {student_data.get('total_hours', 0)}
- Task Completion Rate: {student_data.get('completion_rate', 0)}%
- Total Tasks: {student_data.get('total_tasks', 0)}
- Completed Tasks: {student_data.get('completed_tasks', 0)}
- High Priority Completed: {student_data.get('high_priority_done', 0)}
- Overdue Tasks: {student_data.get('overdue_tasks', 0)}
- Consistency Score: {student_data.get('consistency_score', 0)}%
- Study Sessions This Week: {student_data.get('sessions_this_week', 0)}
- Enrolled Courses: {student_data.get('enrolled_courses', 0)}"""

    return call_llm(system_prompt, user_prompt, lang=lang)

# ============================================================
# FUNCTION 8: Generate Report
# ============================================================

def generate_report(student_data, report_type="weekly", lang='ar'):
    """
    Generates a comprehensive academic performance report.
    """
    system_prompt = f"""You are Nahj AI, generating a {report_type} academic performance report for a university student.
Use this report generation knowledge base:

{json.dumps(REPORTS_KB, indent=2)}

Generate a structured {report_type} report with the following sections:
1. **Executive Summary** — Brief overview (2-3 sentences)
2. **Study Habits Analysis** — Detailed study pattern review
3. **Task Management Review** — Task completion analysis
4. **Strengths & Achievements** — Positive highlights
5. **Areas for Improvement** — Specific weak points
6. **Action Plan** — Top 3 concrete next steps
7. **Goals for Next Period** — SMART goals

Use the insight patterns from the knowledge base to provide relevant commentary.
Be comprehensive but concise. Use encouraging language while being honest about areas needing improvement.
Include specific numbers and percentages from the student's data."""

    user_prompt = f"""Generate a {report_type} report for this student:
- Username: {student_data.get('username', 'Student')}
- Department: {student_data.get('department', 'not set')}
- Level: {student_data.get('level', 1)}
- Learning Style: {student_data.get('learning_style', 'not set')}
- Total Study Hours: {student_data.get('total_hours', 0)}
- Average Daily Hours: {student_data.get('avg_daily_hours', 0)}
- Task Completion Rate: {student_data.get('completion_rate', 0)}%
- Total Tasks: {student_data.get('total_tasks', 0)}
- Completed Tasks: {student_data.get('completed_tasks', 0)}
- Pending Tasks: {student_data.get('pending_tasks', 0)}
- Overdue Tasks: {student_data.get('overdue_tasks', 0)}
- Consistency Score: {student_data.get('consistency_score', 0)}%
- Enrolled Courses: {student_data.get('course_names', 'not specified')}
- Groups Joined: {student_data.get('groups_joined', 0)}
- Community Posts: {student_data.get('posts_count', 0)}"""

    return call_llm(system_prompt, user_prompt, temperature=0.6, lang=lang)

# ============================================================
# FUNCTION: AI Chat (General assistant combining all functions)
# ============================================================

def ai_chat(message, student_data, history=None, lang=None):
    """
    General AI chat that can route to specific functions or provide general advice.
    Supports multi-turn conversation via history parameter.
    lang: session language ('ar'/'en'); if provided it takes priority over message detection.
    """
    all_kb = {
        "behavior": BEHAVIOR_KB,
        "study_patterns": STUDY_PATTERNS_KB,
        "resources": RESOURCES_KB,
        "recommendations": RECOMMENDATIONS_KB,
        "groups": GROUPS_KB,
        "performance": PERFORMANCE_KB,
        "reports": REPORTS_KB
    }

    system_prompt = f"""You are Nahj AI, a friendly and knowledgeable academic assistant for university students at Umm Al-Qura University, College of Computing.

You have access to comprehensive knowledge bases covering:
- Student behavior analysis and classification
- Study patterns and techniques (Pomodoro, Spaced Repetition, Active Recall, etc.)
- Learning resources for various CS courses
- Performance analysis and scoring
- Study group matching and suggestions
- Academic report generation

Here is a summary of the student's current data for personalization:
{json.dumps(student_data, indent=2)}

Here are the knowledge bases for reference:
{json.dumps(all_kb, indent=2)}

Guidelines:
- Be friendly, supportive, and encouraging
- Give specific, actionable advice based on the student's data
- Reference their actual performance numbers when relevant
- Suggest specific study techniques from the knowledge base
- Keep responses focused and not too long
- If the student asks about something unrelated to academics, gently redirect
- You have conversation history, so remember what was discussed earlier in this chat"""

    # Use session language if provided, otherwise detect from message content.
    user_lang = lang if lang else detect_language(message)
    # Put language instruction first so the model treats it as the highest-priority directive.
    messages = [{"role": "system", "content": language_instruction(user_lang) + "\n\n" + system_prompt}]

    if history:
        for h in history[:-1]:  # Add previous history (last message will be the current one)
            role = h.get('role', 'user')
            content = h.get('content', '')
            if role in ('user', 'assistant') and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {str(e)}"

# ============================================================
# FUNCTION: Generate Study Plan
# ============================================================

def generate_study_plan(student_data, plan_type="daily", study_hours=4, focus="balanced", lang='ar'):
    """
    Generates an AI-powered study plan.
    """
    system_prompt = f"""You are Nahj AI, creating a personalized {plan_type} study plan for a university student.

Use this study patterns knowledge base:
{json.dumps(STUDY_PATTERNS_KB, indent=2)}

Create a detailed {plan_type} study plan that:
1. Allocates time across their enrolled courses
2. Includes specific study techniques for each session
3. Incorporates breaks and rest
4. Prioritizes based on upcoming deadlines
5. Matches their learning style

Format the plan as a clear schedule with time slots.
For daily plans, use hourly slots.
For weekly plans, organize by day with 2-3 study blocks per day.

Focus priority: {focus}
Available study hours per day: {study_hours}

Return the plan in a structured format with:
- Time slot
- Course/Subject
- Study technique to use
- Duration
- Notes/tips"""

    user_prompt = f"""Create a {plan_type} study plan:
- Available Hours/Day: {study_hours}
- Focus: {focus}
- Learning Style: {student_data.get('learning_style', 'not set')}
- Enrolled Courses: {student_data.get('course_names', 'not specified')}
- Pending Tasks: {student_data.get('pending_tasks', 0)}
- Upcoming Deadlines: {student_data.get('upcoming_deadlines', 'none specified')}
- Behavior Type: {student_data.get('behavior_type', 'unknown')}"""

    return call_llm(system_prompt, user_prompt, lang=lang)
