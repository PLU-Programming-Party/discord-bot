"""
Webwritten API - Collaborative story writing backend
"""
import os
import json
import sqlite3
import hashlib
import asyncio
import logging
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=["https://plu-programming-party.github.io", "http://localhost:8080"])

# Database path
DB_PATH = os.getenv("WEBWRITTEN_DB_PATH", "./webwritten.db")

# Claude client
api_key = os.getenv("CLAUDE_API_KEY")
claude_client = Anthropic(api_key=api_key) if api_key else None

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database schema"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Story table - the actual story sentences
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS story (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sentence TEXT NOT NULL,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            position INTEGER NOT NULL,
            source TEXT DEFAULT 'llm'
        )
    ''')
    
    # Pending sentences - pool for voting
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            submitter_id TEXT,
            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'llm',
            total_rating INTEGER DEFAULT 0,
            vote_count INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
    # Votes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sentence_id INTEGER NOT NULL,
            voter_id TEXT NOT NULL,
            rating INTEGER NOT NULL,
            voted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sentence_id) REFERENCES pending_sentences(id),
            UNIQUE(sentence_id, voter_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def get_voter_id(request):
    """Generate anonymous voter ID from request"""
    ip = request.remote_addr or "unknown"
    ua = request.headers.get("User-Agent", "unknown")
    raw = f"{ip}:{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def get_current_story():
    """Get the full story text"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sentence FROM story ORDER BY position ASC")
    sentences = cursor.fetchall()
    conn.close()
    
    if not sentences:
        return ""
    return " ".join([s["sentence"] for s in sentences])

def get_random_active_sentence(exclude_ids=None):
    """Get a random active sentence that hasn't been voted on by this user"""
    conn = get_db()
    cursor = conn.cursor()
    
    if exclude_ids:
        placeholders = ",".join("?" * len(exclude_ids))
        cursor.execute(f'''
            SELECT id, text, vote_count, 
                   CASE WHEN vote_count > 0 THEN CAST(total_rating AS FLOAT) / vote_count ELSE 0 END as avg_rating
            FROM pending_sentences 
            WHERE is_active = 1 AND id NOT IN ({placeholders})
            ORDER BY RANDOM() 
            LIMIT 1
        ''', exclude_ids)
    else:
        cursor.execute('''
            SELECT id, text, vote_count,
                   CASE WHEN vote_count > 0 THEN CAST(total_rating AS FLOAT) / vote_count ELSE 0 END as avg_rating
            FROM pending_sentences 
            WHERE is_active = 1
            ORDER BY RANDOM() 
            LIMIT 1
        ''')
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "id": row["id"],
            "text": row["text"],
            "votes_count": row["vote_count"],
            "average_rating": round(row["avg_rating"], 1) if row["avg_rating"] else 0
        }
    return None

def generate_sentences_with_llm(count=20):
    """Generate new sentences using Claude"""
    if not claude_client:
        logger.error("Claude client not initialized")
        return []
    
    story = get_current_story()
    if not story:
        story = "(Story has not started yet)"
    
    prompt = f"""You are helping write a collaborative story. Here is the story so far:

"{story}"

Generate {count} unique, creative potential next sentences. 
Each sentence should:
- Be 10-30 words
- Continue the story naturally
- Vary in tone and direction (some dramatic, some calm, some mysterious)
- Be appropriate for all ages
- Be a complete thought that flows from the current story

Return ONLY a JSON array of strings, no other text:
["sentence1", "sentence2", ...]"""

    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",  # Use Sonnet for speed/cost
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )
        
        text = response.content[0].text.strip()
        # Try to extract JSON array
        if text.startswith("["):
            sentences = json.loads(text)
            logger.info(f"Generated {len(sentences)} sentences with LLM")
            return sentences
        else:
            # Try to find JSON in response
            import re
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                sentences = json.loads(match.group())
                return sentences
        return []
    except Exception as e:
        logger.error(f"Error generating sentences: {e}")
        return []

def seed_initial_content():
    """Seed the database with initial story and sentences"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if already seeded
    cursor.execute("SELECT COUNT(*) as count FROM story")
    if cursor.fetchone()["count"] > 0:
        conn.close()
        return
    
    logger.info("Seeding initial content...")
    
    # Generate opening sentence
    if claude_client:
        try:
            response = claude_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[{"role": "user", "content": "Write a single opening sentence for a collaborative mystery story. The sentence should be intriguing and set the scene. Just the sentence, no quotes or explanation."}]
            )
            opening = response.content[0].text.strip().strip('"')
        except:
            opening = "The old lighthouse had been dark for seventeen years, but tonight, a light flickered in its highest window."
    else:
        opening = "The old lighthouse had been dark for seventeen years, but tonight, a light flickered in its highest window."
    
    # Add opening sentence to story
    cursor.execute(
        "INSERT INTO story (sentence, position, source) VALUES (?, 1, 'seed')",
        (opening,)
    )
    
    # Generate initial pool of sentences
    sentences = generate_sentences_with_llm(50)
    if not sentences:
        # Fallback sentences
        sentences = [
            "A chill ran down my spine as I watched.",
            "The sound of footsteps echoed from somewhere above.",
            "I had to know who—or what—was inside.",
            "The villagers had warned me to stay away.",
            "My flashlight flickered, then died completely."
        ]
    
    for sentence in sentences:
        cursor.execute(
            "INSERT INTO pending_sentences (text, source) VALUES (?, 'llm')",
            (sentence,)
        )
    
    conn.commit()
    conn.close()
    logger.info(f"Seeded with opening: {opening[:50]}... and {len(sentences)} potential sentences")

# API Routes

@app.route("/api/webwritten/story", methods=["GET"])
def get_story():
    """Get current story and a sentence to vote on"""
    voter_id = get_voter_id(request)
    
    # Get sentences this voter has already voted on
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT sentence_id FROM votes WHERE voter_id = ?", (voter_id,))
    voted_ids = [row["sentence_id"] for row in cursor.fetchall()]
    
    # Get pending count
    cursor.execute("SELECT COUNT(*) as count FROM pending_sentences WHERE is_active = 1")
    pending_count = cursor.fetchone()["count"]
    conn.close()
    
    story = get_current_story()
    sentence = get_random_active_sentence(voted_ids if voted_ids else None)
    
    return jsonify({
        "story": story,
        "current_sentence": sentence,
        "total_pending_sentences": pending_count,
        "sentences_voted": len(voted_ids)
    })

@app.route("/api/webwritten/vote", methods=["POST"])
def submit_vote():
    """Submit a vote for a sentence"""
    data = request.get_json()
    sentence_id = data.get("sentence_id")
    rating = data.get("rating")
    voter_id = get_voter_id(request)
    
    if not sentence_id or not rating:
        return jsonify({"error": "Missing sentence_id or rating"}), 400
    
    if not (1 <= rating <= 5):
        return jsonify({"error": "Rating must be 1-5"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if already voted
        cursor.execute(
            "SELECT id FROM votes WHERE sentence_id = ? AND voter_id = ?",
            (sentence_id, voter_id)
        )
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "Already voted on this sentence"}), 400
        
        # Add vote
        cursor.execute(
            "INSERT INTO votes (sentence_id, voter_id, rating) VALUES (?, ?, ?)",
            (sentence_id, voter_id, rating)
        )
        
        # Update sentence totals
        cursor.execute(
            "UPDATE pending_sentences SET total_rating = total_rating + ?, vote_count = vote_count + 1 WHERE id = ?",
            (rating, sentence_id)
        )
        
        conn.commit()
        
        # Get voted sentence IDs for this user
        cursor.execute("SELECT sentence_id FROM votes WHERE voter_id = ?", (voter_id,))
        voted_ids = [row["sentence_id"] for row in cursor.fetchall()]
        conn.close()
        
        # Get next sentence to show
        next_sentence = get_random_active_sentence(voted_ids)
        
        return jsonify({
            "success": True,
            "next_sentence": next_sentence,
            "sentences_voted": len(voted_ids)
        })
        
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Already voted on this sentence"}), 400
    except Exception as e:
        conn.close()
        logger.error(f"Error submitting vote: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/webwritten/submit", methods=["POST"])
def submit_sentence():
    """Submit a user sentence to the pool"""
    data = request.get_json()
    text = data.get("text", "").strip()
    submitter_id = get_voter_id(request)
    
    if not text:
        return jsonify({"error": "Sentence text required"}), 400
    
    if len(text) > 500:
        return jsonify({"error": "Sentence too long (max 500 chars)"}), 400
    
    # Basic sanitization
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "INSERT INTO pending_sentences (text, submitter_id, source) VALUES (?, ?, 'user')",
            (text, submitter_id)
        )
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()
        
        logger.info(f"User submitted sentence: {text[:50]}...")
        
        return jsonify({
            "success": True,
            "sentence_id": new_id,
            "message": "Your sentence has been added to the pool!"
        })
        
    except Exception as e:
        conn.close()
        logger.error(f"Error submitting sentence: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/webwritten/stats", methods=["GET"])
def get_stats():
    """Get voting statistics"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM story")
    story_length = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM pending_sentences WHERE is_active = 1")
    pending = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM votes WHERE DATE(voted_at) = DATE('now')")
    votes_today = cursor.fetchone()["count"]
    
    conn.close()
    
    # Calculate next selection time (midnight UTC)
    now = datetime.now(timezone.utc)
    next_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if next_midnight <= now:
        from datetime import timedelta
        next_midnight += timedelta(days=1)
    
    return jsonify({
        "story_length": story_length,
        "pending_sentences": pending,
        "total_votes_today": votes_today,
        "next_selection": next_midnight.isoformat()
    })

def select_daily_winner():
    """Select the winning sentence and add to story"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Find highest rated sentence with at least 3 votes
    cursor.execute('''
        SELECT id, text, vote_count, total_rating,
               CAST(total_rating AS FLOAT) / vote_count as avg_rating
        FROM pending_sentences
        WHERE is_active = 1 AND vote_count >= 3
        ORDER BY avg_rating DESC, vote_count DESC
        LIMIT 1
    ''')
    
    winner = cursor.fetchone()
    
    if not winner:
        logger.info("No winner today - not enough votes")
        conn.close()
        return None
    
    # Get next position
    cursor.execute("SELECT MAX(position) as max_pos FROM story")
    row = cursor.fetchone()
    next_pos = (row["max_pos"] or 0) + 1
    
    # Add to story
    cursor.execute(
        "INSERT INTO story (sentence, position, source) VALUES (?, ?, 'voted')",
        (winner["text"], next_pos)
    )
    
    # Mark as inactive
    cursor.execute(
        "UPDATE pending_sentences SET is_active = 0 WHERE id = ?",
        (winner["id"],)
    )
    
    conn.commit()
    conn.close()
    
    logger.info(f"Daily winner: {winner['text'][:50]}... (rating: {winner['avg_rating']:.1f})")
    
    return {
        "sentence": winner["text"],
        "rating": winner["avg_rating"],
        "votes": winner["vote_count"]
    }

def maintain_sentence_pool():
    """Ensure there are enough sentences in the pool"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM pending_sentences WHERE is_active = 1")
    count = cursor.fetchone()["count"]
    conn.close()
    
    if count < 30:
        logger.info(f"Pool has {count} sentences, generating more...")
        new_sentences = generate_sentences_with_llm(20)
        
        conn = get_db()
        cursor = conn.cursor()
        for sentence in new_sentences:
            cursor.execute(
                "INSERT INTO pending_sentences (text, source) VALUES (?, 'llm')",
                (sentence,)
            )
        conn.commit()
        conn.close()
        logger.info(f"Added {len(new_sentences)} new sentences to pool")

# Initialize on import
init_db()

@app.route("/api/webwritten/admin/regenerate", methods=["POST"])
def regenerate_sentences():
    """Admin endpoint to regenerate sentences based on current story"""
    # Simple admin key check (should use proper auth in production)
    auth = request.headers.get("X-Admin-Key")
    expected = os.getenv("ADMIN_KEY", "regenerate-please")
    
    if auth != expected:
        return jsonify({"error": "Unauthorized"}), 401
    
    # Clear old unvoted sentences (keep voted ones)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pending_sentences WHERE is_active = 1 AND vote_count = 0")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    # Generate new sentences based on current story
    new_sentences = generate_sentences_with_llm(50)
    
    conn = get_db()
    cursor = conn.cursor()
    for sentence in new_sentences:
        cursor.execute(
            "INSERT INTO pending_sentences (text, source) VALUES (?, 'llm')",
            (sentence,)
        )
    conn.commit()
    conn.close()
    
    logger.info(f"Regenerated sentences: deleted {deleted} old, added {len(new_sentences)} new")
    
    return jsonify({
        "success": True,
        "deleted": deleted,
        "added": len(new_sentences),
        "story_context": get_current_story()[:100] + "..."
    })
