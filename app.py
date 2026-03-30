import sqlite3
import anthropic
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def get_db():
    conn = sqlite3.connect("flushfind.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS washrooms (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL,
            location TEXT NOT NULL,
            status   TEXT DEFAULT 'open',
            rating   REAL DEFAULT 0.0,
            lat      REAL DEFAULT 0.0,
            lng      REAL DEFAULT 0.0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user        TEXT DEFAULT 'Anonymous',
            stars       INTEGER NOT NULL,
            text        TEXT NOT NULL,
            washroom_id INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/add")
def add_page():
    return render_template("add.html")

@app.route("/review")
def review_page():
    return render_template("review.html")

@app.route("/map")
def map_page():
    return render_template("map.html")

@app.route("/api/washrooms", methods=["GET"])
def get_washrooms():
    conn = get_db()
    washrooms = conn.execute("SELECT * FROM washrooms").fetchall()
    result = []
    for w in washrooms:
        count = conn.execute(
            "SELECT COUNT(*) as c FROM reviews WHERE washroom_id=?", (w["id"],)
        ).fetchone()["c"]
        result.append({
            "id":           w["id"],
            "name":         w["name"],
            "location":     w["location"],
            "status":       w["status"],
            "rating":       w["rating"],
            "review_count": count,
            "lat":          w["lat"],
            "lng":          w["lng"]
        })
    conn.close()
    return jsonify(result)

@app.route("/api/washrooms", methods=["POST"])
def add_washroom():
    data = request.get_json()
    conn = get_db()
    conn.execute(
        "INSERT INTO washrooms (name, location, status, lat, lng) VALUES (?, ?, ?, ?, ?)",
        (data["name"], data["location"], data.get("status", "open"),
         data.get("lat", 0.0), data.get("lng", 0.0))
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Washroom added!"}), 201

@app.route("/api/washrooms/<int:id>/reviews", methods=["GET"])
def get_reviews(id):
    conn = get_db()
    reviews = conn.execute(
        "SELECT * FROM reviews WHERE washroom_id=?", (id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in reviews])

@app.route("/api/washrooms/<int:id>/reviews", methods=["POST"])
def add_review(id):
    data     = request.get_json()
    conn     = get_db()
    conn.execute(
        "INSERT INTO reviews (user, stars, text, washroom_id) VALUES (?, ?, ?, ?)",
        (data.get("user", "Anonymous"), data["stars"], data["text"], id)
    )
    reviews     = conn.execute(
        "SELECT stars FROM reviews WHERE washroom_id=?", (id,)
    ).fetchall()
    avg = round(sum(r["stars"] for r in reviews) / len(reviews), 1)
    conn.execute("UPDATE washrooms SET rating=? WHERE id=?", (avg, id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Review added!"}), 201

@app.route("/api/washrooms/<int:id>/ai-review", methods=["GET"])
def ai_review(id):
    conn     = get_db()
    washroom = conn.execute("SELECT * FROM washrooms WHERE id=?", (id,)).fetchone()
    reviews  = conn.execute("SELECT * FROM reviews WHERE washroom_id=?", (id,)).fetchall()
    conn.close()

    if not washroom:
        return jsonify({"error": "Washroom not found"}), 404

    if len(reviews) == 0:
        return jsonify({"score": None, "summary": "No reviews yet to analyze."})

    # Keyword analysis
    positive_words = ["clean", "great", "good", "nice", "fresh", "stocked",
                      "amazing", "excellent", "perfect", "spacious", "bright",
                      "sanitized", "tidy", "maintained", "convenient", "quick"]
    negative_words = ["dirty", "smelly", "bad", "terrible", "awful", "broken",
                      "disgusting", "messy", "wet", "empty", "crowded", "busy",
                      "long", "queue", "slow", "dark", "small", "poor"]
    amenity_words  = ["soap", "paper", "towel", "dryer", "accessible", "baby",
                      "changing", "toilet", "flush", "mirror", "lock", "door"]

    total_stars    = 0
    positive_count = 0
    negative_count = 0
    amenity_count  = 0
    review_count   = len(reviews)

    for r in reviews:
        total_stars += r["stars"]
        text = r["text"].lower()
        positive_count += sum(1 for w in positive_words if w in text)
        negative_count += sum(1 for w in negative_words if w in text)
        amenity_count  += sum(1 for w in amenity_words  if w in text)

    avg_stars  = total_stars / review_count
    base_score = avg_stars * 2

    # Adjust score based on keywords
    base_score += min(positive_count * 0.2, 1.5)
    base_score -= min(negative_count * 0.3, 2.0)
    base_score += min(amenity_count  * 0.1, 0.5)

    # Clamp between 1 and 10
    score = round(max(1.0, min(10.0, base_score)), 1)

    # Generate smart summary
    if score >= 8.5:
        tone = "Excellent"
        detail = "consistently praised for cleanliness and great amenities"
    elif score >= 7.0:
        tone = "Good"
        detail = "generally well maintained with positive visitor experiences"
    elif score >= 5.5:
        tone = "Average"
        detail = "decent but has some room for improvement"
    elif score >= 4.0:
        tone = "Below average"
        detail = "has received mixed reviews with cleanliness concerns"
    else:
        tone = "Poor"
        detail = "frequently reported as unclean or poorly maintained"

    if amenity_count > 2:
        amenity_note = " Well stocked with amenities."
    elif negative_count > positive_count:
        amenity_note = " Visitors report some maintenance issues."
    else:
        amenity_note = ""

    summary = f"{tone} washroom — {detail}.{amenity_note} Based on {review_count} review{'s' if review_count > 1 else ''}."

    return jsonify({"score": str(score), "summary": summary})

init_db()

if __name__ == "__main__":
    app.run(debug=True)